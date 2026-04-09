from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Optional
from app.models import (
    PaymentCreate, PaymentResponse, PaymentConfirmationRequest, PaymentConfirmationResponse,
    AppointmentSummary, PaymentMethodRequest, CardPaymentRequest, EasyPaisaPaymentRequest,
    NotificationPreference, NotificationPreferenceUpdate, NotificationPreferenceResponse,
    PaymentStatus, PaymentMethod, PaymentType, NotificationType, TokenStatus
)
from app.database import get_db
from sqlalchemy.orm import Session
from app.db_models import User, Doctor, Hospital, Token, Payment, ActivityLog, Queue as DBQueue
from app.config import TOKEN_FEE
from app.security import get_current_active_user
from datetime import datetime, timedelta, timezone
import uuid
import re
from app.services.notification_service import NotificationService
from app.services.token_service import SmartTokenService
from app.utils.idempotency import Idempotency
from app.utils.audit import log_action, get_user_role

router = APIRouter(prefix="/payments", tags=["Payments"])

# ---------------- Queue calc helpers (match tokens router logic) ----------------

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

def _queue_for_message(db: Session, doctor_id: str, hospital_id: str, appointment_dt) -> tuple[int, int]:
    """Return (now_serving, per_patient_minutes) using DBQueue, default per_patient_minutes=5.
    """
    # Fetch doctor/hospital for tz
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
    hospital_data = {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {}
    
    # In PostgreSQL, we use the Queue table directly for live status
    q = db.query(DBQueue).filter(DBQueue.doctor_id == doctor_id).first()
    
    now_serving = int(getattr(q, "current_token", 1) or 1)
    per_min = 5 # Default per patient minutes
    
    return now_serving, per_min

def _format_appt_local(db: Session, doctor_id: str, hospital_id: str, appointment_dt) -> str:
    try:
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
        hospital_data = {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {}
        
        tz_minutes = _tz_offset_for(doctor_data, hospital_data)
        tz = timezone(timedelta(minutes=tz_minutes))
        dt = appointment_dt
        if getattr(dt, 'tzinfo', None) is None:
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
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get appointment summary for payment confirmation"""
    
    # Get token details
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    
    # Verify token belongs to current user
    if token.patient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Get doctor details
    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    
    # Get hospital details
    hospital = db.query(Hospital).filter(Hospital.id == token.hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")
    hospital_data = {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')}
    
    return AppointmentSummary(
        doctor=doctor_data,
        hospital=hospital_data,
        consultation_fee=TOKEN_FEE,
        total_amount=TOKEN_FEE,
        appointment_date=token.appointment_date
    )

@router.post("/confirm", response_model=PaymentConfirmationResponse)
@router.post("/process", response_model=PaymentConfirmationResponse)
async def confirm_payment(
    payment_request: PaymentConfirmationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Confirm payment for appointment with optional Idempotency-Key support"""

    async def _runner(db_session: Session) -> dict:
        # Get token details
        token = db_session.query(Token).filter(Token.id == payment_request.token_id).first()
        if not token:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
        
        # Verify token belongs to current user
        if token.patient_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
            
        # Check if payment already exists
        existing_payment = db_session.query(Payment).filter(
            Payment.token_id == payment_request.token_id,
            Payment.status.in_([PaymentStatus.PAID, PaymentStatus.PENDING])
        ).first()
        
        if existing_payment:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment already exists for this token")
            
        consultation_fee = TOKEN_FEE
        
        # Validate payment details based on method
        if payment_request.payment_method == PaymentMethod.ONLINE:
            if not payment_request.payment_type:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment type is required for online payment")
            if payment_request.payment_type == PaymentType.CREDIT_DEBIT_CARD:
                if not payment_request.card_details or not validate_card_details(payment_request.card_details):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid card details")
            elif payment_request.payment_type == PaymentType.EASYPAISA:
                if not payment_request.easypaisa_details or not validate_phone_number(payment_request.easypaisa_details.phone_number):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")
        
        # Process payment (mock)
        payment_status = PaymentStatus.PAID
        transaction_id = f"TXN_{uuid.uuid4().hex[:8].upper()}"
        
        # Create payment record
        payment_id = str(uuid.uuid4())
        new_payment = Payment(
            id=payment_id,
            token_id=payment_request.token_id,
            amount=consultation_fee,
            method=payment_request.payment_method,
            status=payment_status,
            transaction_id=transaction_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(new_payment)
        
        # Update token
        token.payment_status = payment_status
        token.payment_method = payment_request.payment_method
        token.status = TokenStatus.CONFIRMED
        token.updated_at = datetime.utcnow()
        
        db_session.commit()
        db_session.refresh(new_payment)
        db_session.refresh(token)
        
        # Build appointment summary
        summary = await get_appointment_summary(payment_request.token_id, db=db_session, current_user=current_user)
        
        # Notifications logic
        phone_number = current_user.phone or ""
        notif_types = [NotificationType.SMS]
        if payment_request.notification_types:
            notif_types = list(set(payment_request.notification_types + [NotificationType.SMS]))
            
        if phone_number:
            now_serving, per_min = _queue_for_message(db_session, token.doctor_id, token.hospital_id, token.appointment_date)
            try:
                people_ahead = max(0, int(token.token_number) - int(now_serving))
            except Exception:
                people_ahead = 0
            est_wait = int(people_ahead) * int(per_min)
            
            doctor_name = summary.doctor.get("name") if isinstance(summary.doctor, dict) else summary.doctor.name
            appointment_time_str = _format_appt_local(db_session, token.doctor_id, token.hospital_id, token.appointment_date)
            
            sms_message = (
                f"Payment successful. Token: {token.token_number}. "
                f"Doctor: {doctor_name}. Time: {appointment_time_str}. "
                f"People ahead: {people_ahead}. Estimated wait: {est_wait} minutes."
            )
            
            if NotificationType.SMS in notif_types:
                await NotificationService.send_sms_message(phone_number, sms_message)
            if NotificationType.WHATSAPP in notif_types:
                await NotificationService.send_whatsapp_message(phone_number, sms_message)
                
        return {
            "token_id": payment_request.token_id,
            "payment_id": payment_id,
            "status": payment_status.value,
            "transaction_id": transaction_id,
            "message": "Payment successful! Your appointment is confirmed.",
            "appointment_summary": summary.model_dump() if hasattr(summary, 'model_dump') else summary.dict(),
        }

    # If Idempotency-Key is provided, use it
    key = request.headers.get(Idempotency.HEADER_NAME)
    if key:
        valid_key = Idempotency.validate_key(key)
        # Idempotency service needs to be updated for SQL, adding TODO
        # For now, we run it normally
        result = await _runner(db)
    else:
        result = await _runner(db)
        
    # Audit log
    try:
        role = get_user_role(current_user.id)
        # Update log_action to accept db session if needed
        log_action(current_user.id, role, action="MARK_PAID", token_id=result.get("token_id"))
    except Exception:
        pass
        
    return PaymentConfirmationResponse(**result)

@router.get("/history", response_model=List[PaymentResponse])
async def get_payment_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    limit: int = 20
):
    """Get user's payment history"""
    payments = db.query(Payment).join(Token).filter(Token.patient_id == current_user.id).order_by(Payment.created_at.desc()).limit(limit).all()
    return [PaymentResponse(**{k: v for k, v in p.__dict__.items() if not k.startswith('_')}) for p in payments]

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment_details(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get specific payment details"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        
    token = db.query(Token).filter(Token.id == payment.token_id).first()
    if token.patient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    return PaymentResponse(**{k: v for k, v in payment.__dict__.items() if not k.startswith('_')})

# Helper functions
def validate_card_details(card_details: CardPaymentRequest) -> bool:
    """Validate credit/debit card details"""
    if not re.match(r'^\d{13,19}$', card_details.card_number):
        return False
    if not re.match(r'^\d{2}$', card_details.expiry_month):
        return False
    if not re.match(r'^\d{2}$', card_details.expiry_year):
        return False
    if not re.match(r'^\d{3,4}$', card_details.cvv):
        return False
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
    clean_phone = re.sub(r'\D', '', phone)
    if len(clean_phone) == 11 and clean_phone.startswith('03'):
        return True
    if len(clean_phone) == 12 and clean_phone.startswith('923'):
        return True
    return False
