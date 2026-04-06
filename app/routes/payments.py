from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Optional
from app.models import (
    PaymentCreate, PaymentResponse, PaymentConfirmationRequest, PaymentConfirmationResponse,
    AppointmentSummary, PaymentMethodRequest, CardPaymentRequest, EasyPaisaPaymentRequest,
    NotificationPreference, NotificationPreferenceUpdate, NotificationPreferenceResponse,
    PaymentStatus, PaymentMethod, PaymentType, NotificationType, TokenStatus
)
from app.database import get_db
from app.config import COLLECTIONS, TOKEN_FEE
from app.security import get_current_active_user
from datetime import datetime
import uuid
import re
from app.services.notification_service import NotificationService
from app.services.token_service import SmartTokenService
from app.utils.idempotency import Idempotency
from app.utils.audit import log_action, get_user_role

router = APIRouter(prefix="/payments", tags=["Payments"])

# ---------------- Queue calc helpers (match tokens router logic) ----------------
from datetime import timedelta, timezone

def _tz_offset_for(doctor_data: dict, hospital_data: dict | None = None) -> int:
    try:
        tz_doc = doctor_data.get("tz_offset_minutes")
        tz_h = (hospital_data or {}).get("tz_offset_minutes") if hospital_data else None
        if tz_doc is not None:
            return int(tz_doc)
        if tz_h is not None:
            return int(tz_h)
    except Exception:
        pass
    # Default Pakistan Standard Time if unspecified (UTC+5 = 300 minutes)
    return 300

def _local_day_for(dt_utc, tz_minutes: int):
    try:
        tz = timezone(timedelta(minutes=tz_minutes))
        return dt_utc.astimezone(tz).date()
    except Exception:
        return dt_utc.date()

def _capacity_doc_id(doctor_id: str, hospital_id: str, day) -> str:
    return f"{doctor_id}_{hospital_id}_{day.strftime('%Y%m%d')}"

def _queue_for_message(db, doctor_id: str, hospital_id: str, appointment_dt) -> tuple[int, int]:
    """Return (people_ahead, estimated_wait_minutes) using capacity doc, default per_patient_minutes=5.
    Mirrors tokens._queue_object_for behavior.
    """
    # Fetch doctor/hospital for tz
    dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).get()
    href = db.collection(COLLECTIONS["HOSPITALS"]).document(hospital_id).get()
    doctor_data = dref.to_dict() if getattr(dref, "exists", False) else {}
    hospital_data = href.to_dict() if getattr(href, "exists", False) else {}
    tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
    # Resolve day
    if hasattr(appointment_dt, "tzinfo"):
        day_local = _local_day_for(appointment_dt, tz_minutes)
    else:
        day_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)
    cap_ref = db.collection(COLLECTIONS["CAPACITY"]).document(_capacity_doc_id(doctor_id, hospital_id, day_local))
    snap = cap_ref.get()
    data = snap.to_dict() if getattr(snap, "exists", False) else {}
    now_serving = int(data.get("now_serving_number") or 1)
    per_min = int(data.get("per_patient_minutes") or 5)
    return now_serving, per_min

def _format_appt_local(db, doctor_id: str, hospital_id: str, appointment_dt) -> str:
    try:
        dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).get()
        href = db.collection(COLLECTIONS["HOSPITALS"]).document(hospital_id).get()
        doctor_data = dref.to_dict() if getattr(dref, "exists", False) else {}
        hospital_data = href.to_dict() if getattr(href, "exists", False) else {}
        tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
        tz = timezone(timedelta(minutes=tz_minutes))
        dt = appointment_dt
        to_dt = getattr(dt, 'to_datetime', None)
        if callable(to_dt):
            dt = to_dt()
        if getattr(dt, 'tzinfo', None) is None:
            # treat as UTC if naive
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(tz)
        return local_dt.strftime("%I:%M %p")
    except Exception:
        try:
            return appointment_dt.strftime("%I:%M %p")
        except Exception:
            return ""

@router.get("/methods", response_model=List[dict])
async def get_payment_methods():
    """Get available payment methods"""
    return [
        {
            "method": PaymentMethod.ONLINE,
            "title": "Pay Online",
            "description": "Instant confirmation",
            "secure": True,
            "payment_types": [
                {
                    "type": PaymentType.CREDIT_DEBIT_CARD,
                    "title": "Credit/Debit Card",
                    "description": "Visa, Mastercard accepted",
                    "icon": "card",
                    # Frontend hint: call /payments/banks to load bank list
                    "banks_available": True
                },
                {
                    "type": PaymentType.EASYPAISA,
                    "title": "EasyPaisa",
                    "description": "Mobile wallet payment",
                    "icon": "easypaisa"
                }
            ]
        },
        {
            "method": PaymentMethod.RECEPTION,
            "title": "Pay at Reception",
            "description": "Pay when you arrive",
            "secure": False,
            "payment_types": []
        }
    ]

@router.get("/token/{token_id}/summary", response_model=AppointmentSummary)
async def get_appointment_summary(
    token_id: str,
    current_user = Depends(get_current_active_user)
):
    """Get appointment summary for payment confirmation"""
    db = get_db()
    
    # Get token details
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Verify token belongs to current user
    if token_data["patient_id"] != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Get doctor details
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(token_data["doctor_id"])
    doctor_doc = doctor_ref.get()
    
    if not doctor_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    doctor_data = doctor_doc.to_dict()
    
    # Get hospital details
    hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(token_data["hospital_id"])
    hospital_doc = hospital_ref.get()
    
    if not hospital_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )
    
    hospital_data = hospital_doc.to_dict()
    
    return AppointmentSummary(
        doctor=doctor_data,
        hospital=hospital_data,
        consultation_fee=TOKEN_FEE,
        total_amount=TOKEN_FEE,
        appointment_date=token_data["appointment_date"]
    )

@router.post("/confirm", response_model=PaymentConfirmationResponse)
async def confirm_payment(
    payment_request: PaymentConfirmationRequest,
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """Confirm payment for appointment with optional Idempotency-Key support"""
    db = get_db()

    async def _runner() -> dict:
        # Original implementation wrapped for idempotency
        # Get token details
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document(payment_request.token_id)
        token_doc = token_ref.get()
        if not token_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found"
            )
        token_data = token_doc.to_dict()
        # Verify token belongs to current user
        if token_data["patient_id"] != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        # Check if payment already exists
        existing_payment = db.collection(COLLECTIONS["PAYMENTS"])\
                             .where("token_id", "==", payment_request.token_id)\
                             .where("status", "in", [PaymentStatus.PAID, PaymentStatus.PENDING])\
                             .limit(1).stream()
        if list(existing_payment):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment already exists for this token"
            )
        consultation_fee = TOKEN_FEE
        # Validate payment details based on method
        if payment_request.payment_method == PaymentMethod.ONLINE:
            if not payment_request.payment_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payment type is required for online payment"
                )
            if payment_request.payment_type == PaymentType.CREDIT_DEBIT_CARD:
                if not payment_request.card_details:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Card details are required"
                    )
                if not validate_card_details(payment_request.card_details):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid card details"
                    )
            elif payment_request.payment_type == PaymentType.EASYPAISA:
                if not payment_request.easypaisa_details:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="EasyPaisa details are required"
                    )
                if not validate_phone_number(payment_request.easypaisa_details.phone_number):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid phone number"
                    )
        # Process payment (mock)
        payment_status = PaymentStatus.PAID
        transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        # Create payment record
        payment_ref = db.collection(COLLECTIONS["PAYMENTS"]).document()
        payment_data = {
            "id": payment_ref.id,
            "token_id": payment_request.token_id,
            "patient_id": current_user.user_id,
            "amount": consultation_fee,
            "method": payment_request.payment_method,
            "payment_type": payment_request.payment_type,
            "status": getattr(payment_status, 'value', payment_status),
            "transaction_id": transaction_id,
            "card_details": payment_request.card_details.dict() if payment_request.card_details else None,
            "easypaisa_details": payment_request.easypaisa_details.dict() if payment_request.easypaisa_details else None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        if payment_request.card_details and (payment_request.card_details.bank_code or payment_request.card_details.bank_name):
            payment_data["issuing_bank_code"] = payment_request.card_details.bank_code
            payment_data["issuing_bank_name"] = payment_request.card_details.bank_name
        payment_ref.set(payment_data)
        # Update token payment status and overall status
        token_ref.update({
            "payment_status": getattr(payment_status, 'value', payment_status),
            "payment_method": payment_request.payment_method,
            "status": TokenStatus.CONFIRMED,
            "updated_at": datetime.utcnow()
        })
        # Build appointment summary and notifications (reuse existing helpers)
        appointment_summary = await get_appointment_summary(payment_request.token_id, current_user)
        notif_types: List[NotificationType] = []
        if payment_request.notification_types:
            notif_types = list(set(payment_request.notification_types + [NotificationType.SMS]))
        else:
            prefs_q = db.collection("notification_preferences").where("user_id", "==", current_user.user_id).limit(1).stream()
            prefs_list = list(prefs_q)
            if prefs_list:
                prefs = prefs_list[0].to_dict()
                if prefs.get("whatsapp_enabled", True):
                    notif_types.append(NotificationType.WHATSAPP)
                phone_number = prefs.get("phone_number") or getattr(current_user, 'phone', '') or ''
            else:
                phone_number = getattr(current_user, 'phone', '') or ''
        if NotificationType.SMS not in notif_types:
            notif_types.append(NotificationType.SMS)
        if 'phone_number' not in locals() or not phone_number:
            user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
            user_doc = user_ref.get()
            phone_number = (user_doc.to_dict() or {}).get("phone", "") if user_doc.exists else ""
        if notif_types and phone_number:
            tnum = token_data.get("token_number")
            display_label = str(tnum) if tnum is not None else ""
            now_serving, per_min = _queue_for_message(db, token_data["doctor_id"], token_data["hospital_id"], token_data.get("appointment_date"))
            try:
                people_ahead = max(0, int(tnum) - int(now_serving))
            except Exception:
                people_ahead = 0
            est_wait = int(people_ahead) * int(per_min)
            doctor_name = appointment_summary.doctor.get("name") if isinstance(appointment_summary.doctor, dict) else appointment_summary.doctor.name
            appointment_time_str = _format_appt_local(db, token_data["doctor_id"], token_data["hospital_id"], token_data.get("appointment_date"))
            sms_message = (
                f"Payment successful. Token: {display_label}. "
                f"Doctor: {doctor_name}. Time: {appointment_time_str}. "
                f"People ahead: {people_ahead}. Estimated wait: {est_wait} minutes."
            )
            if NotificationType.SMS in notif_types:
                await NotificationService.send_sms_message(phone_number, sms_message)
            if NotificationType.WHATSAPP in notif_types:
                await NotificationService.send_whatsapp_message(phone_number, sms_message)
        # Return serializable dict for idempotency store
        return {
            "token_id": payment_request.token_id,
            "payment_id": payment_ref.id,
            "status": getattr(payment_status, 'value', payment_status),
            "transaction_id": transaction_id,
            "message": "Payment successful! Your appointment is confirmed.",
            "appointment_summary": appointment_summary.model_dump() if hasattr(appointment_summary, 'model_dump') else appointment_summary.dict() if hasattr(appointment_summary, 'dict') else appointment_summary,
        }

    # If Idempotency-Key is provided, use it
    key = request.headers.get(Idempotency.HEADER_NAME)
    if key:
        valid_key = Idempotency.validate_key(key)
        result = await Idempotency.get_or_run_async(current_user.user_id, valid_key, action="payments_confirm", ttl_minutes=60, runner_async=_runner)
        # Map back to response model
        resp = PaymentConfirmationResponse(
            token_id=result.get("token_id"),
            payment_id=result.get("payment_id"),
            status=result.get("status"),
            transaction_id=result.get("transaction_id"),
            message=result.get("message"),
            appointment_summary=result.get("appointment_summary"),
        )
        try:
            # Audit: MARK_PAID
            role = get_user_role(current_user.user_id)
            log_action(current_user.user_id, role, action="MARK_PAID", token_id=result.get("token_id"))
        except Exception:
            pass
        return resp

    # No idempotency key -> run once
    data = await _runner()
    # Audit: MARK_PAID
    try:
        role = get_user_role(current_user.user_id)
        log_action(current_user.user_id, role, action="MARK_PAID", token_id=data.get("token_id"))
    except Exception:
        pass
    return PaymentConfirmationResponse(
        token_id=data.get("token_id"),
        payment_id=data.get("payment_id"),
        status=data.get("status"),
        transaction_id=data.get("transaction_id"),
        message=data.get("message"),
        appointment_summary=data.get("appointment_summary"),
    )
    
    # Get token details
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(payment_request.token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Verify token belongs to current user
    if token_data["patient_id"] != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Check if payment already exists
    existing_payment = db.collection(COLLECTIONS["PAYMENTS"])\
                         .where("token_id", "==", payment_request.token_id)\
                         .where("status", "in", [PaymentStatus.PAID, PaymentStatus.PENDING])\
                         .limit(1).stream()
    
    if list(existing_payment):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment already exists for this token"
        )
    
    # Token-based billing: fixed per-token fee
    consultation_fee = TOKEN_FEE
    
    # Validate payment details based on method
    if payment_request.payment_method == PaymentMethod.ONLINE:
        if not payment_request.payment_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment type is required for online payment"
            )
        
        if payment_request.payment_type == PaymentType.CREDIT_DEBIT_CARD:
            if not payment_request.card_details:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Card details are required"
                )
            
            # Validate card details
            if not validate_card_details(payment_request.card_details):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid card details"
                )
        
        elif payment_request.payment_type == PaymentType.EASYPAISA:
            if not payment_request.easypaisa_details:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="EasyPaisa details are required"
                )
            
            # Validate phone number
            if not validate_phone_number(payment_request.easypaisa_details.phone_number):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid phone number"
                )
    
    # Process payment (mock implementation)
    payment_status = PaymentStatus.PAID
    transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
    
    # Create payment record
    payment_ref = db.collection(COLLECTIONS["PAYMENTS"]).document()
    payment_data = {
        "id": payment_ref.id,
        "token_id": payment_request.token_id,
        "patient_id": current_user.user_id,
        "amount": consultation_fee,
        "method": payment_request.payment_method,
        "payment_type": payment_request.payment_type,
        # Store as string for Firestore compatibility
        "status": getattr(payment_status, 'value', payment_status),
        "transaction_id": transaction_id,
        "card_details": payment_request.card_details.dict() if payment_request.card_details else None,
        "easypaisa_details": payment_request.easypaisa_details.dict() if payment_request.easypaisa_details else None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    # Also expose bank info at top level for analytics/filtering
    if payment_request.card_details and (payment_request.card_details.bank_code or payment_request.card_details.bank_name):
        payment_data["issuing_bank_code"] = payment_request.card_details.bank_code
        payment_data["issuing_bank_name"] = payment_request.card_details.bank_name
    
    payment_ref.set(payment_data)
    
    # Update token payment status and overall status
    token_ref.update({
        # Store as string for Firestore compatibility
        "payment_status": getattr(payment_status, 'value', payment_status),
        "payment_method": payment_request.payment_method,
        "status": TokenStatus.CONFIRMED,
        "updated_at": datetime.utcnow()
    })
    
    # Get appointment summary (also provides doctor & hospital info)
    appointment_summary = await get_appointment_summary(payment_request.token_id, current_user)

    # Determine notification types (force SMS always; WhatsApp optional)
    notif_types: List[NotificationType] = []
    if payment_request.notification_types:
        # Respect request but ensure SMS is present
        notif_types = list(set(payment_request.notification_types + [NotificationType.SMS]))
    else:
        # Load prefs to optionally include WhatsApp; SMS will be added regardless below
        prefs_q = db.collection("notification_preferences").where("user_id", "==", current_user.user_id).limit(1).stream()
        prefs_list = list(prefs_q)
        if prefs_list:
            prefs = prefs_list[0].to_dict()
            if prefs.get("whatsapp_enabled", True):
                notif_types.append(NotificationType.WHATSAPP)
            phone_number = prefs.get("phone_number") or getattr(current_user, 'phone', '') or ''
        else:
            # Default fallback phone
            phone_number = getattr(current_user, 'phone', '') or ''
    # Force SMS to be included regardless of prefs/toggles
    if NotificationType.SMS not in notif_types:
        notif_types.append(NotificationType.SMS)

    # Fallback phone_number if not resolved above
    if 'phone_number' not in locals() or not phone_number:
        # Try fetching from user profile
        user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
        user_doc = user_ref.get()
        phone_number = (user_doc.to_dict() or {}).get("phone", "") if user_doc.exists else ""

    # After successful payment, send queue-aware SMS/WhatsApp if requested
    if notif_types and phone_number:
        # Token number as plain integer (match app)
        tnum = token_data.get("token_number")
        display_label = str(tnum) if tnum is not None else ""

        # Compute queue using capacity doc to match app
        now_serving, per_min = _queue_for_message(db, token_data["doctor_id"], token_data["hospital_id"], token_data.get("appointment_date"))
        try:
            people_ahead = max(0, int(tnum) - int(now_serving))
        except Exception:
            people_ahead = 0
        est_wait = int(people_ahead) * int(per_min)

        # Doctor and clinic-local appointment time
        doctor_name = appointment_summary.doctor.get("name") if isinstance(appointment_summary.doctor, dict) else appointment_summary.doctor.name
        appt_dt = token_data.get("appointment_date")
        appointment_time_str = _format_appt_local(db, token_data["doctor_id"], token_data["hospital_id"], appt_dt)

        # Compose concise confirmation text for SMS (align with app)
        sms_message = (
            f"Payment successful. Token: {display_label}. "
            f"Doctor: {doctor_name}. Time: {appointment_time_str}. "
            f"People ahead: {people_ahead}. Estimated wait: {est_wait} minutes."
        )

        # Send SMS if selected
        if NotificationType.SMS in notif_types:
            await NotificationService.send_sms_message(phone_number, sms_message)

        # Optionally mirror to WhatsApp if selected
        if NotificationType.WHATSAPP in notif_types:
            await NotificationService.send_whatsapp_message(phone_number, sms_message)
    
    return PaymentConfirmationResponse(
        token_id=payment_request.token_id,
        payment_id=payment_ref.id,
        status=payment_status,
        transaction_id=transaction_id,
        message="Payment successful! Your appointment is confirmed.",
        appointment_summary=appointment_summary
    )

# -------------------- Confirm & Book (atomic today) --------------------
from pydantic import BaseModel

class ConfirmAndBookRequest(BaseModel):
    doctor_id: str
    hospital_id: str
    payment_method: PaymentMethod
    payment_type: Optional[PaymentType] = None
    card_details: Optional[CardPaymentRequest] = None
    easypaisa_details: Optional[EasyPaisaPaymentRequest] = None
    notification_types: Optional[List[NotificationType]] = None

@router.post("/confirm-and-book", response_model=PaymentConfirmationResponse)
async def confirm_and_book(req: ConfirmAndBookRequest, current_user = Depends(get_current_active_user)):
    """Create today's token atomically and confirm payment in one call.

    This mirrors the UX where the user taps Confirm & Pay without pre-creating a token.
    """
    db = get_db()

    # 1) Create token atomically for TODAY using a local allocator (no circular imports)
    # ---- Helpers ----
    from datetime import timedelta, timezone

    def _default_tz_offset_minutes() -> int:
        import os
        try:
            return int(os.getenv("DEFAULT_TZ_OFFSET_MINUTES", "300"))
        except Exception:
            return 300

    def _tz_offset_for(doctor_data: dict, hospital_data: dict | None = None) -> int:
        try:
            tz_doc = doctor_data.get("tz_offset_minutes")
            tz_h = (hospital_data or {}).get("tz_offset_minutes") if hospital_data else None
            if tz_doc is not None:
                return int(tz_doc)
            if tz_h is not None:
                return int(tz_h)
        except Exception:
            pass
        return _default_tz_offset_minutes()

    def _local_day_for(dt_utc, tz_minutes: int):
        try:
            tz = timezone(timedelta(minutes=tz_minutes))
            return dt_utc.astimezone(tz).date()
        except Exception:
            return dt_utc.date()

    def _capacity_doc_id(doctor_id: str, hospital_id: str, day) -> str:
        return f"{doctor_id}_{hospital_id}_{day.strftime('%Y%m%d')}"

    def _get_today_capacity(doctor_data: dict) -> int:
        try:
            return max(0, int(doctor_data.get("patients_per_day") or 20))
        except Exception:
            return 20

    def _minute_for_token_number(start_hhmm: str, end_hhmm: str, token_number: int, tz_minutes: int, base_utc=None):
        try:
            now_utc = base_utc or datetime.utcnow().replace(tzinfo=timezone.utc)
            tz = timezone(timedelta(minutes=tz_minutes))
            today_local = now_utc.astimezone(tz).date()
            def _hm(s: str):
                parts = (s or "00:00").split(":")
                h = int(parts[0] or 0)
                m = int(parts[1] or 0)
                return h, m
            sh, sm = _hm(start_hhmm or "09:00")
            eh, em = _hm(end_hhmm or "17:00")
            start_local = datetime(today_local.year, today_local.month, today_local.day, sh, sm, tzinfo=tz)
            end_local = datetime(today_local.year, today_local.month, today_local.day, eh, em, tzinfo=tz)
            if end_local <= start_local:
                end_local = start_local + timedelta(hours=8)
            window_minutes = int((end_local - start_local).total_seconds() // 60)
            if window_minutes <= 0:
                raise ValueError("bad window")
            # Simple sequential minute mapping (first token -> start, next -> +1 minute, etc.)
            offset = max(0, token_number - 1)
            appt_local = start_local + timedelta(minutes=offset)
            if appt_local > end_local:
                appt_local = end_local
            return appt_local.astimezone(timezone.utc)
        except Exception:
            return (datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(minutes=max(0, token_number)))

    # ---- Perform allocation ----
    # Validate doctor and hospital
    doc_ref = db.collection(COLLECTIONS["DOCTORS"]).document(req.doctor_id)
    doc_snap = doc_ref.get()
    if not doc_snap.exists:
        raise HTTPException(status_code=400, detail="Doctor not found")
    doctor_data = doc_snap.to_dict() or {}

    hosp_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(req.hospital_id)
    hosp_snap = hosp_ref.get()
    if not hosp_snap.exists:
        raise HTTPException(status_code=400, detail="Hospital not found")
    hospital_data = hosp_snap.to_dict() or {}

    tz_minutes = _tz_offset_for(doctor_data, hospital_data)
    today_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)
    cap_ref = db.collection(COLLECTIONS["CAPACITY"]).document(_capacity_doc_id(req.doctor_id, req.hospital_id, today_local))

    # Transactional increment
    token_number = None
    try:
        from google.cloud import firestore
        transaction = db.transaction()
        @firestore.transactional
        def allocate(tx):
            snap = cap_ref.get(transaction=tx)
            data = snap.to_dict() if getattr(snap, "exists", False) else None
            cap_val = _get_today_capacity(doctor_data)
            if not data:
                data = {
                    "doctor_id": req.doctor_id,
                    "hospital_id": req.hospital_id,
                    "date": str(today_local),
                    "capacity": int(cap_val),
                    "booked_count": 0,
                    "last_token_number": 0,
                    "tz_offset_minutes": tz_minutes,
                    "updated_at": datetime.utcnow(),
                }
            booked = int(data.get("booked_count", 0))
            cap = int(data.get("capacity", cap_val))
            if booked >= cap:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor's daily capacity reached for today.")
            booked += 1
            last = int(data.get("last_token_number", 0)) + 1
            data.update({"booked_count": booked, "last_token_number": last, "updated_at": datetime.utcnow()})
            tx.set(cap_ref, data, merge=True)
            return last
        token_number = allocate(transaction)
    except HTTPException:
        raise
    except Exception:
        # Fallback non-transactional
        snap = cap_ref.get()
        data = snap.to_dict() if getattr(snap, "exists", False) else {}
        if not data:
            data = {"booked_count": 0, "last_token_number": 0, "capacity": _get_today_capacity(doctor_data)}
        if int(data.get("booked_count", 0)) >= int(data.get("capacity", 0)):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor's daily capacity reached for today.")
        data["booked_count"] = int(data.get("booked_count", 0)) + 1
        data["last_token_number"] = int(data.get("last_token_number", 0)) + 1
        data.update({"doctor_id": req.doctor_id, "hospital_id": req.hospital_id, "date": str(today_local), "updated_at": datetime.utcnow()})
        cap_ref.set(data, merge=True)
        token_number = data["last_token_number"]

    # Persist token
    appt_utc = _minute_for_token_number(
        doctor_data.get("start_time") or "09:00",
        doctor_data.get("end_time") or "17:00",
        token_number,
        tz_minutes,
    )
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]) 
    token_ref = tokens_ref.document()
    token_id = token_ref.id
    token_payload = {
        "id": token_id,
        "patient_id": current_user.user_id,
        "doctor_id": req.doctor_id,
        "hospital_id": req.hospital_id,
        "token_number": token_number,
        "hex_code": f"{token_id[:8]}{token_number:03d}",
        "appointment_date": appt_utc,
        "status": TokenStatus.PENDING,
        "payment_status": PaymentStatus.PAID if req.payment_method == PaymentMethod.RECEPTION else PaymentStatus.PENDING,
        "doctor_name": doctor_data.get("name"),
        "doctor_specialization": doctor_data.get("specialization"),
        "hospital_name": hospital_data.get("name"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    token_ref.set(token_payload)

    # 2) Validate payment method details similar to /confirm
    if req.payment_method == PaymentMethod.ONLINE:
        if not req.payment_type:
            raise HTTPException(status_code=400, detail="Payment type is required for online payment")
        if req.payment_type == PaymentType.CREDIT_DEBIT_CARD:
            if not req.card_details or not validate_card_details(req.card_details):
                raise HTTPException(status_code=400, detail="Invalid card details")
        elif req.payment_type == PaymentType.EASYPAISA:
            if not req.easypaisa_details or not validate_phone_number(req.easypaisa_details.phone_number):
                raise HTTPException(status_code=400, detail="Invalid phone number")

    # 3) Create payment
    payment_status = PaymentStatus.PAID
    transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"

    payment_ref = db.collection(COLLECTIONS["PAYMENTS"]).document()
    payment_data = {
        "id": payment_ref.id,
        "token_id": token_id,
        "patient_id": current_user.user_id,
        "amount": TOKEN_FEE,
        "method": req.payment_method,
        "payment_type": req.payment_type,
        # Store as string for Firestore compatibility
        "status": getattr(payment_status, 'value', payment_status),
        "transaction_id": transaction_id,
        "card_details": req.card_details.dict() if req.card_details else None,
        "easypaisa_details": req.easypaisa_details.dict() if req.easypaisa_details else None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    if req.card_details and (req.card_details.bank_code or req.card_details.bank_name):
        payment_data["issuing_bank_code"] = req.card_details.bank_code
        payment_data["issuing_bank_name"] = req.card_details.bank_name
    payment_ref.set(payment_data)

    # 4) Mark token confirmed and attach payment info
    db.collection(COLLECTIONS["TOKENS"]).document(token_id).update({
        # Store as string for Firestore compatibility
        "payment_status": getattr(payment_status, 'value', payment_status),
        "payment_method": req.payment_method,
        "status": TokenStatus.CONFIRMED,
        "updated_at": datetime.utcnow(),
    })

    # 5) Build appointment summary (doctor, hospital, time)
    appointment_summary = await get_appointment_summary(token_id, current_user)

    # 6) Send notifications (similar to /confirm) – force SMS always; WhatsApp optional
    notif_types: List[NotificationType] = []
    if req.notification_types:
        notif_types = list(set(req.notification_types + [NotificationType.SMS]))
    else:
        prefs_q = db.collection("notification_preferences").where("user_id", "==", current_user.user_id).limit(1).stream()
        prefs_list = list(prefs_q)
        if prefs_list:
            prefs = prefs_list[0].to_dict()
            if prefs.get("whatsapp_enabled", True):
                notif_types.append(NotificationType.WHATSAPP)
            phone_number = prefs.get("phone_number") or getattr(current_user, 'phone', '') or ''
        else:
            phone_number = getattr(current_user, 'phone', '') or ''
    if NotificationType.SMS not in notif_types:
        notif_types.append(NotificationType.SMS)

    if 'phone_number' not in locals() or not phone_number:
        user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
        user_doc = user_ref.get()
        phone_number = (user_doc.to_dict() or {}).get("phone", "") if user_doc.exists else ""

    if notif_types and phone_number:
        # Compose message aligned with app numbers/time
        tnum = token_payload.get("token_number")
        display_label = str(tnum) if tnum is not None else ""

        now_serving, per_min = _queue_for_message(db, token_payload["doctor_id"], token_payload["hospital_id"], token_payload["appointment_date"])
        try:
            people_ahead = max(0, int(tnum) - int(now_serving))
        except Exception:
            people_ahead = 0
        est_wait = int(people_ahead) * int(per_min)

        doctor_name = appointment_summary.doctor.get("name") if isinstance(appointment_summary.doctor, dict) else appointment_summary.doctor.name
        appt_dt = token_payload["appointment_date"]
        appointment_time_str = _format_appt_local(db, token_payload["doctor_id"], token_payload["hospital_id"], appt_dt)

        sms_message = (
            f"Payment successful. Token: {display_label}. "
            f"Doctor: {doctor_name}. Time: {appointment_time_str}. "
            f"People ahead: {people_ahead}. Estimated wait: {est_wait} minutes."
        )
        try:
            if NotificationType.SMS in notif_types:
                await NotificationService.send_sms_message(phone_number, sms_message)
        except Exception:
            pass
        try:
            if NotificationType.WHATSAPP in notif_types:
                await NotificationService.send_whatsapp_message(phone_number, sms_message)
        except Exception:
            pass

    return PaymentConfirmationResponse(
        token_id=token_id,
        payment_id=payment_ref.id,
        status=payment_status,
        transaction_id=transaction_id,
        message="Payment successful! Your appointment is confirmed.",
        appointment_summary=appointment_summary,
    )

@router.get("/token/{token_id}/message-preview")
async def preview_confirmation_message(
    token_id: str,
    current_user = Depends(get_current_active_user)
):
    """Preview the SMS/WhatsApp message that would be sent after payment confirmation.
    Returns the composed message with token number, doctor name, appointment time,
    people ahead, and estimated wait. Does not send anything."""
    db = get_db()

    # Fetch token (and verify owner)
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    if not token_doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    token_data = token_doc.to_dict()
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Appointment summary for doctor/hospital and time
    appointment_summary = await get_appointment_summary(token_id, current_user)

    # Build display token label
    display_label = token_data.get("display_code")
    if not display_label:
        display_label = SmartTokenService.format_token(token_data["token_number"]) if token_data.get("token_number") is not None else ""

    # Queue status
    q = SmartTokenService.get_queue_status(
        doctor_id=token_data["doctor_id"],
        token_number=token_data.get("token_number"),
        appointment_date=token_data.get("appointment_date")
    ) or {}
    people_ahead = int(q.get("people_ahead", 0))
    est_wait = int(q.get("estimated_wait_time", 0))

    # Doctor and appointment time
    doctor_name = appointment_summary.doctor.get("name") if isinstance(appointment_summary.doctor, dict) else appointment_summary.doctor.name
    appt_dt = token_data.get("appointment_date")
    try:
        appointment_time_str = appt_dt.strftime("%I:%M %p") if hasattr(appt_dt, 'strftime') else str(appt_dt)
    except Exception:
        appointment_time_str = ""

    message = (
        f"Payment successful. Token: {display_label}. "
        f"Doctor: {doctor_name}. Time: {appointment_time_str}. "
        f"People ahead: {people_ahead}. Estimated wait: {est_wait} minutes."
    )

    return {
        "token_id": token_id,
        "message": message,
        "token_number": display_label,
        "doctor_name": doctor_name,
        "appointment_time": appointment_time_str,
        "people_ahead": people_ahead,
        "estimated_wait_time": est_wait
    }

@router.get("/history", response_model=List[PaymentResponse])
async def get_payment_history(
    current_user = Depends(get_current_active_user),
    limit: int = 20
):
    """Get user's payment history"""
    db = get_db()
    
    payments_ref = db.collection(COLLECTIONS["PAYMENTS"])
    payments = payments_ref.where("patient_id", "==", current_user.user_id)\
                          .order_by("created_at", direction="DESCENDING")\
                          .limit(limit).stream()
    
    payment_list = []
    for payment in payments:
        payment_list.append(PaymentResponse(**payment.to_dict()))
    
    return payment_list

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment_details(
    payment_id: str,
    current_user = Depends(get_current_active_user)
):
    """Get specific payment details"""
    db = get_db()
    
    payment_ref = db.collection(COLLECTIONS["PAYMENTS"]).document(payment_id)
    payment_doc = payment_ref.get()
    
    if not payment_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    payment_data = payment_doc.to_dict()
    
    # Verify payment belongs to current user
    if payment_data["patient_id"] != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return PaymentResponse(**payment_data)

# Notification Preferences
@router.get("/notifications/preferences", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    current_user = Depends(get_current_active_user)
):
    """Get user's notification preferences"""
    db = get_db()
    
    # Try to get existing preferences
    prefs_ref = db.collection("notification_preferences").where("user_id", "==", current_user.user_id).limit(1).stream()
    prefs_list = list(prefs_ref)
    
    if prefs_list:
        return NotificationPreferenceResponse(**prefs_list[0].to_dict())
    
    # Create default preferences
    default_prefs = {
        "id": f"pref_{current_user.user_id}",
        "user_id": current_user.user_id,
        "whatsapp_enabled": True,
        "sms_enabled": True,
        "phone_number": getattr(current_user, 'phone', '') or "",
        "settings": {
            "queue_updates": True,
            "appointment_reminders": True,
            "emergency_alerts": True
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    prefs_ref = db.collection("notification_preferences").document(default_prefs["id"])
    prefs_ref.set(default_prefs)
    
    return NotificationPreferenceResponse(**default_prefs)

@router.put("/notifications/preferences", response_model=NotificationPreferenceResponse)
async def update_notification_preferences(
    preferences: NotificationPreferenceUpdate,
    current_user = Depends(get_current_active_user)
):
    """Update user's notification preferences"""
    db = get_db()
    
    # Get existing preferences
    prefs_ref = db.collection("notification_preferences").where("user_id", "==", current_user.user_id).limit(1).stream()
    prefs_list = list(prefs_ref)
    
    if prefs_list:
        prefs_doc = prefs_list[0]
        prefs_data = prefs_doc.to_dict()
        prefs_data.update({
            "whatsapp_enabled": preferences.whatsapp_enabled,
            "sms_enabled": preferences.sms_enabled,
            "updated_at": datetime.utcnow()
        })
        
        db.collection("notification_preferences").document(prefs_doc.id).update(prefs_data)
        return NotificationPreferenceResponse(**prefs_data)
    
    # Create new preferences
    new_prefs = {
        "id": f"pref_{current_user.user_id}",
        "user_id": current_user.user_id,
        "whatsapp_enabled": preferences.whatsapp_enabled,
        "sms_enabled": preferences.sms_enabled,
        "phone_number": getattr(current_user, 'phone', '') or "",
        "settings": {
            "queue_updates": True,
            "appointment_reminders": True,
            "emergency_alerts": True
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    prefs_ref = db.collection("notification_preferences").document(new_prefs["id"])
    prefs_ref.set(new_prefs)
    
    return NotificationPreferenceResponse(**new_prefs)

# Helper functions
def validate_card_details(card_details: CardPaymentRequest) -> bool:
    """Validate credit/debit card details"""
    # Basic validation - in production, use proper card validation library
    if not re.match(r'^\d{13,19}$', card_details.card_number):
        return False
    
    if not re.match(r'^\d{2}$', card_details.expiry_month):
        return False
    
    if not re.match(r'^\d{2}$', card_details.expiry_year):
        return False
    
    if not re.match(r'^\d{3,4}$', card_details.cvv):
        return False
    
    # Check expiry date
    try:
        month = int(card_details.expiry_month)
        year = int(card_details.expiry_year)
        
        if month < 1 or month > 12:
            return False
        
        current_year = datetime.now().year % 100
        if year < current_year:
            return False
        
    except ValueError:
        return False
    
    return True

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    # Remove any non-digit characters
    clean_phone = re.sub(r'\D', '', phone)
    
    # Check if it's a valid Pakistani phone number
    if len(clean_phone) == 11 and clean_phone.startswith('03'):
        return True
    
    if len(clean_phone) == 12 and clean_phone.startswith('923'):
        return True
    
    return False
