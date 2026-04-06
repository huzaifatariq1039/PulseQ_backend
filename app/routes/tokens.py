from fastapi import APIRouter, HTTPException, status, Depends, Query, Response, Body, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import logging

from app.models import (
    SmartTokenCreate, SmartTokenResponse, PaymentCreate, PaymentResponse, 
    ActivityType, TokenCancellationRequest, QueueResponse, NotificationRequest,
    TokenStatus, NotificationType, CancellationResponse, RefundCalculation,
    CancellationReason, RefundMethod, RefundStatus, SmartTokenGenerateRequest,
    PaymentStatus
)
from app.database import get_db
from app.config import COLLECTIONS, TOKEN_FEE
from app.security import get_current_active_user
from app.security import require_roles
from app.services.token_service import SmartTokenService
from app.services.notification_scheduler_client import schedule_token_messages, send_queue_alert
from app.services.message_scheduler import schedule_messages
from app.services.confirmation_scheduler import schedule_confirmation_checks
from app.utils.mrn import get_or_create_patient_mrn
from app.utils.state import is_transition_allowed
from app.utils.responses import ok
from app.services.slot_booking_service import reserve_slot_transactionally, finalize_slot_booking

from datetime import datetime
from datetime import timedelta, timezone
import os
import asyncio
try:
    # Atomic increments for Firestore counters
    from google.cloud.firestore_v1 import Increment
except Exception:
    Increment = None

router = APIRouter(prefix="/tokens", tags=["SmartTokens"])

logger = logging.getLogger(__name__)

# ... (rest of the code remains the same)

@router.post("/generate/details")
async def generate_smart_token_with_details(
    payload: SmartTokenGenerateRequest,
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
):
    """Generate a token and return enriched doctor/hospital details in one call.

    Response shape matches appointment-details for immediate UI rendering.
    """
    # Decide atomic vs legacy based on date (today or unspecified -> atomic FCFS)
    use_atomic = False
    try:
        if payload.appointment_date is None:
            use_atomic = True
        else:
            now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
            # Fetch doctor to compute local day
            db = get_db()
            d_snap = db.collection(COLLECTIONS["DOCTORS"]).document(payload.doctor_id).get()
            doctor_data = d_snap.to_dict() if getattr(d_snap, "exists", False) else {}
            h_snap = db.collection(COLLECTIONS["HOSPITALS"]).document(payload.hospital_id).get()
            hospital_data = h_snap.to_dict() if getattr(h_snap, "exists", False) else {}
            tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
            today_local = _local_day_for(now_utc, tz_minutes)
            # Normalize given date to local day too
            appt_local = _to_local_clock(payload.appointment_date)
            use_atomic = (appt_local.date() == today_local)
    except Exception:
        use_atomic = True

    if use_atomic:
        # Use the race-safe allocator for today's booking
        token_resp: SmartTokenResponse = await generate_smart_token(
            doctor_id=payload.doctor_id,
            hospital_id=payload.hospital_id,
            appointment_date=None,
            current_user=current_user,
            fingerprint_name=fingerprint_name,
            fingerprint_phone=fingerprint_phone,
        )
        appointment_date = token_resp.appointment_date
    else:
        # Future-date flow uses legacy generator
        token_resp: SmartTokenResponse = await generate_smart_token(
            doctor_id=payload.doctor_id,
            hospital_id=payload.hospital_id,
            appointment_date=payload.appointment_date,
            current_user=current_user,
            fingerprint_name=fingerprint_name,
            fingerprint_phone=fingerprint_phone,
        )

    # Load doctor/hospital for enriched response
    db = get_db()
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(token_resp.doctor_id)
    hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(token_resp.hospital_id)
    doctor_data = doctor_ref.get().to_dict()
    hospital_data = hospital_ref.get().to_dict()

    # Queue status for this token (include appointment_date for correct same-day vs future logic)
    queue_status = SmartTokenService.get_queue_status(
        token_resp.doctor_id,
        token_resp.token_number,
        appointment_date=token_resp.appointment_date,
    )

    # Appointment time formatting (hidden for same-day)
    appt_dt = token_resp.appointment_date
    try:
        from datetime import datetime as _dt
        if hasattr(appt_dt, 'strftime') and appt_dt.date() != _dt.utcnow().date():
            appointment_time_str = appt_dt.strftime("%I:%M %p")
        else:
            appointment_time_str = ""
    except Exception:
        appointment_time_str = ""

    # Prefer embedded snapshot if present on token
    token_dict = token_resp.model_dump()
    safe_doctor = {
        "id": token_resp.doctor_id,
        "name": token_dict.get("doctor_name") or (doctor_data or {}).get("name") or "Dr. Doctor",
        "specialization": token_dict.get("doctor_specialization")
        or (doctor_data or {}).get("specialization")
        or (doctor_data or {}).get("department")
        or (doctor_data or {}).get("subcategory")
        or "General",
        "avatar_initials": token_dict.get("doctor_avatar_initials") or (doctor_data or {}).get("avatar_initials") or ((doctor_data or {}).get("name", "DR")[:3].upper())
    }
    safe_hospital = {
        "id": token_resp.hospital_id,
        "name": token_dict.get("hospital_name") or (hospital_data or {}).get("name") or "Hospital"
    }

    return {
        "token": token_resp,
        "doctor": safe_doctor,
        "hospital": safe_hospital,
        "queue": queue_status,
        "appointment_date": token_resp.appointment_date,
        "appointment_time": appointment_time_str
    }

@router.post("/generate", response_model=SmartTokenResponse)
async def generate_smart_token(
    doctor_id: str,
    hospital_id: str,
    appointment_date: Optional[datetime] = None,
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
):
    """Test endpoint for token generation without authentication (for development only)"""
    db = get_db()
    
    # Use a test user ID
    test_user_id = "test_patient_123"
    
    # Verify doctor exists and fetch snapshot
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    doctor_doc = doctor_ref.get()
    
    if not doctor_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor not found"
        )

    # Verify hospital exists and fetch snapshot
    hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(hospital_id)
    hospital_doc = hospital_ref.get()
    if not hospital_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hospital not found"
        )
    
    # Determine appointment behavior (with same-day FCFS minute allocation)
    # Use client-local notion of 'now' for same-day logic
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    now = _to_local_clock(now_utc)
    doctor_data = doctor_doc.to_dict() or {}
    prelocked = False
    slot_ref = None
    if appointment_date is None:
        # Same-day booking without explicit time: allocate earliest free minute within doctor's window
        appointment_minute = _allocate_same_day_slot(get_db(), doctor_id, hospital_id, now, doctor_data)
        appointment_date = appointment_minute
        # Pre-locked inside allocator; capture ref and set locked_by_user
        slot_id = _slot_id_for(doctor_id, appointment_minute)
        slot_ref = get_db().collection(COLLECTIONS["APPOINTMENTS"]).document(slot_id)
        try:
            slot_ref.set({"locked_by_user": current_user.user_id, "updated_at": datetime.utcnow()}, merge=True)
        except Exception:
            pass
        prelocked = True
    else:
        # If future date without time (00:00), require time selection
        if _to_local_clock(appointment_date).date() > now.date() and appointment_date.hour == 0 and appointment_date.minute == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For future appointments, please provide both date and time."
            )
        # If it's today but time not provided (00:00), auto-allocate like above
        if _to_local_clock(appointment_date).date() == now.date() and appointment_date.hour == 0 and appointment_date.minute == 0:
            appointment_minute = _allocate_same_day_slot(get_db(), doctor_id, hospital_id, now, doctor_data)
            appointment_date = appointment_minute
            slot_id = _slot_id_for(doctor_id, appointment_minute)
            slot_ref = get_db().collection(COLLECTIONS["APPOINTMENTS"]).document(slot_id)
            try:
                slot_ref.set({"locked_by_user": current_user.user_id, "updated_at": datetime.utcnow()}, merge=True)
            except Exception:
                pass
            prelocked = True

    # Generate token number, hex code, and formatted token
    token_number, hex_code, formatted_token = SmartTokenService.create_smart_token(
        patient_id=test_user_id,
        doctor_id=doctor_id,
        hospital_id=hospital_id,
        appointment_date=appointment_date
    )
    
    # Get queue status for this token
    queue_status = SmartTokenService.get_queue_status(
        doctor_id,
        token_number,
        appointment_date=appointment_date,
    )
    
    # Create token data (pricing depends on doctor type)
    try:
        consultation_fee = float((doctor_data or {}).get("consultation_fee") or 0)
    except Exception:
        consultation_fee = 0.0
    if consultation_fee is None or consultation_fee <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor consultation_fee is required")

    dept_text = (
        f"{(doctor_data or {}).get('specialization') or ''} "
        f"{(doctor_data or {}).get('subcategory') or ''} "
        f"{(doctor_data or {}).get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text
        for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )

    session_fee = None
    if inferred_has_session:
        try:
            session_fee = float((doctor_data or {}).get("session_fee") or 0)
        except Exception:
            session_fee = None
        if session_fee is None or session_fee <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_fee is required for session-based departments")

    total_fee = consultation_fee + (session_fee or 0)
    requires_payment = total_fee > 0
    token_data = {
        "token_number": token_number,
        "hex_code": hex_code,
        "formatted_token": formatted_token,
        "patient_id": test_user_id,
        "doctor_id": doctor_id,
        "hospital_id": hospital_id,
        "appointment_date": appointment_date,
        # WhatsApp confirmation tracking
        "confirmed": False,
        "confirmation_status": "pending_confirmation",
        "confirmation_requested_at": datetime.utcnow(),
        # Patient must opt-in via WhatsApp YES before being counted in the live queue.
        "queue_opt_in": False,
        "queue_opted_in_at": None,
        # If payment is required, keep token in PENDING state until /payments/confirm
        "status": TokenStatus.PENDING if requires_payment else TokenStatus.CONFIRMED,
        "payment_status": "pending" if requires_payment else "not_required",
        "payment_method": None,
        # 1-based position for UI; for future appointments keep 0
        # Not in queue until opted-in.
        "queue_position": 0,
        "total_queue": 0,
        "estimated_wait_time": 0,
        # Fee breakdown (doctor pricing)
        "consultation_fee": consultation_fee,
        "session_fee": session_fee,
        "total_fee": total_fee,
    }
    
    # Save token to database
    try:
        token_id = SmartTokenService.save_smart_token(token_data)
    except Exception as e:
        # Release the slot lock on failure to save token
        try:
            slot_ref.set({"status": "cancelled", "error": str(e), "updated_at": datetime.utcnow()}, merge=True)
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create token.")
    token_data["id"] = token_id
    token_data["created_at"] = datetime.utcnow()
    token_data["updated_at"] = datetime.utcnow()

    # ---------------- WhatsApp notification scheduling (Node service) ----------------
    try:
        # Enrich with patient phone for scheduler convenience
        user_ref = get_db().collection(COLLECTIONS["USERS"]).document(test_user_id)
        user_data = user_ref.get().to_dict() or {}
        token_data["patient_phone"] = user_data.get("phone")
        token_data["patient_name"] = token_data.get("patient_name") or user_data.get("name")
    except Exception:
        token_data["patient_phone"] = None
        token_data["patient_name"] = token_data.get("patient_name")

    # Send the initial booking template immediately (token_number)
    try:
        phone = (token_data.get("patient_phone") or "").strip()
        if phone:
            from app.templates import TEMPLATES
            from app.services.whatsapp_service import send_template_message

            tpl = str(TEMPLATES.get("CONFIRMATION") or "").strip()
            if tpl:
                params = [
                    str(token_data.get("patient_name") or "Patient"),
                    str(token_data.get("formatted_token") or token_data.get("token_number") or ""),
                ]
                await send_template_message(phone, tpl, params)
    except Exception:
        pass

    # Schedule confirmation checks (reminder after 5 mins, then final mark after 5 mins)
    try:
        schedule_confirmation_checks(token_id, first_delay_minutes=5, second_delay_minutes=5)
    except Exception:
        pass

    # Do not start live updates until the patient opts in (YES)

    # Queue alerts also wait for opt-in

    return {
        "message": "Token generated successfully",
        "token": token_data,
        "queue_info": queue_status
    }

async def cancel_token(
    token_id: str,
    cancellation: TokenCancellationRequest,
    current_user = Depends(get_current_active_user)
):
    """Core cancel logic: verifies ownership, records refund, marks token cancelled, and decrements capacity."""
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    if not getattr(token_doc, "exists", False):
        raise HTTPException(status_code=404, detail="Token not found")
    token = token_doc.to_dict() or {}
    if token.get("patient_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Normalize enums
    try:
        reason_enum = cancellation.reason if isinstance(cancellation.reason, CancellationReason) else CancellationReason(str(cancellation.reason or "other").lower())
    except Exception:
        reason_enum = CancellationReason.OTHER
    try:
        rm_enum = cancellation.refund_method if isinstance(cancellation.refund_method, RefundMethod) else RefundMethod(str(cancellation.refund_method or "smarttoken_wallet").lower())
    except Exception:
        rm_enum = RefundMethod.SMARTTOKEN_WALLET

    # Calculate refund (token-fee based)
    try:
        refund_calc = RefundService.calculate_refund(TOKEN_FEE, reason_enum)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate refund: {e}")
    try:
        refund_id = RefundService.create_refund_record(
            token_id=token_id,
            user_id=token.get("patient_id"),
            refund_calculation=refund_calc,
            refund_method=rm_enum,
            cancellation_reason=reason_enum,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create refund record: {e}")

    # Mark token cancelled (store status as string for Firestore compatibility)
    try:
        token_ref.update({
            "status": getattr(TokenStatus.CANCELLED, 'value', TokenStatus.CANCELLED),
            "updated_at": datetime.utcnow(),
        })
    except Exception:
        # If update fails, still return refund info but indicate failure via 500
        raise HTTPException(status_code=500, detail="Failed to update token status during cancellation")

    # Atomically adjust capacity: decrement booked_count and skip if cancelling the next-to-serve token
    try:
        from google.cloud import firestore
        # Determine clinic-local day for the token's appointment
        dref = db.collection(COLLECTIONS["DOCTORS"]).document(token["doctor_id"]).get()
        href = db.collection(COLLECTIONS["HOSPITALS"]).document(token["hospital_id"]).get()
        doctor_data = dref.to_dict() if getattr(dref, "exists", False) else {}
        hospital_data = href.to_dict() if getattr(href, "exists", False) else {}
        tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
        appt = token.get("appointment_date")
        if hasattr(appt, "tzinfo"):
            day_local = _local_day_for(appt, tz_minutes)
        else:
            day_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)

        cap_ref = db.collection(COLLECTIONS["CAPACITY"]).document(_capacity_doc_id(token["doctor_id"], token["hospital_id"], day_local))
        transaction = db.transaction()

        @firestore.transactional
        def adjust(tx):
            snap = cap_ref.get(transaction=tx)
            data = snap.to_dict() if getattr(snap, "exists", False) else {}
            booked = int(data.get("booked_count", 0))
            if booked > 0:
                data["booked_count"] = booked - 1
            # If the cancelled token is the one currently about to be served, skip to the next number
            try:
                now_serving = int(data.get("now_serving_number") or 1)
                cancelled_num = int(token.get("token_number") or 0)
                if cancelled_num and cancelled_num == now_serving:
                    data["now_serving_number"] = now_serving + 1
            except Exception:
                pass
            data["updated_at"] = datetime.utcnow()
            tx.set(cap_ref, data, merge=True)

        adjust(transaction)
    except Exception:
        # Fall back to best-effort decrement only
        try:
            _decrement_capacity_for_token(db, token)
        except Exception:
            pass

    # Log activity (best-effort)
    try:
        await create_activity_log(
            token.get("patient_id"),
            ActivityType.TOKEN_CANCELLED,
            f"Cancelled SmartToken #{token.get('token_number')}",
            {"token_id": token_id, "refund_id": refund_id, "reason": getattr(reason_enum, 'value', str(reason_enum))},
        )
    except Exception:
        pass

    # Build updated queue object for this doctor/day so clients can refresh immediately
    try:
        q = _queue_object_for(db, token["doctor_id"], token["hospital_id"], day_local, None)
    except Exception:
        q = {}

    # Recalculate wait-time for remaining tokens so each following token drops by ~5 minutes.
    try:
        per_min = int(doctor_data.get("per_patient_minutes") or 5)
    except Exception:
        per_min = 5
    try:
        _recalculate_token_wait_times(db, token["doctor_id"], token["hospital_id"], day_local, per_patient_minutes=per_min)
    except Exception:
        pass

    return {
        "message": "Token cancelled successfully",
        "token_id": token_id,
        "cancellation_reason": reason_enum,
        "refund_info": refund_calc,
        "refund_id": refund_id,
        "queue": q,
    }

@router.post("/{token_id}/cancel", response_model=CancellationResponse)
async def cancel_token_post(
    token_id: str,
    payload: dict,
    current_user = Depends(get_current_active_user)
):
    """POST alias for cancelling a token that accepts plain strings for reason/refund_method.
    Frontends can send: {"reason": "Schedule Conflict", "refund_method": "smarttoken_wallet", "custom_reason": "..."}
    """
    req = TokenCancellationRequest(
        reason=payload.get("reason"),
        custom_reason=payload.get("custom_reason"),
        refund_method=payload.get("refund_method"),
    )
    return await cancel_token(token_id, req, current_user)

@router.delete("/{token_id}/cancel", response_model=CancellationResponse)
async def cancel_token_delete(
    token_id: str,
    payload: dict | None = None,
    reason: Optional[str] = Query(None),
    refund_method: Optional[str] = Query(None),
    current_user = Depends(get_current_active_user)
):
    """DELETE alias for clients that issue DELETE. Accepts JSON body or query params for reason and refund_method."""
    body = payload or {}
    req = TokenCancellationRequest(
        reason=body.get("reason") or reason,
        custom_reason=body.get("custom_reason"),
        refund_method=body.get("refund_method") or refund_method,
    )
    return await cancel_token(token_id, req, current_user)

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs"""
    db = get_db()
    activities_ref = db.collection("activities")
    
    activity_ref = activities_ref.document()
    activity_data = {
        "id": activity_ref.id,
        "user_id": user_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.utcnow()
    }
    
    activity_ref.set(activity_data)

@router.post("/generate", response_model=SmartTokenResponse)
async def generate_smart_token(
    doctor_id: str,
    hospital_id: str,
    appointment_date: Optional[datetime] = None,
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
    include_consultation_fee: Optional[bool] = None,
    include_session_fee: Optional[bool] = None,
):
    """Generate a new SmartToken for a patient"""
    db = get_db()
    
    # Verify doctor exists
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    doctor_doc = doctor_ref.get()
    
    if not doctor_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor not found"
        )
    
    # Verify hospital exists
    hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(hospital_id)
    hospital_doc = hospital_ref.get()
    if not hospital_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hospital not found"
        )
    
    # Initialize commonly used variables
    doctor_data = doctor_doc.to_dict() or {}
    hospital_data = hospital_doc.to_dict() or {}
    prelocked = False
    slot_ref = None
    
    # Permanent MRN for this patient in this hospital
    try:
        patient_mrn = get_or_create_patient_mrn(db, hospital_id=hospital_id, patient_id=current_user.user_id)
    except Exception:
        patient_mrn = None
    
    # Determine appointment behavior (same-day uses earliest available minute within window)
    now_local = _to_local_clock(datetime.utcnow().replace(tzinfo=timezone.utc))
    # Resolve capacity (per-day limit, FCFS)
    try:
        daily_capacity = int(doctor_data.get("patients_per_day") or 10)
    except Exception:
        daily_capacity = 10

    if appointment_date is None:
        # Same-day booking without explicit time: enforce daily capacity for today
        todays_count = _count_doctor_bookings_for_date(db, doctor_id, now_local.date())
        if todays_count >= daily_capacity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Doctor's daily capacity reached for today. Max: {daily_capacity}. Please choose another day."
                )
            )
        # Allocate earliest free minute within doctor's window
        try:
            appointment_date = _allocate_same_day_slot(db, doctor_id, hospital_id, now_local, doctor_data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("That slot was just taken. Queue is first-come, first-served for today.")
            )
        # Mark allocator-created lock as owned by current user
        try:
            _sid = _slot_id_for(doctor_id, appointment_date)
            _sref = db.collection(COLLECTIONS["APPOINTMENTS"]).document(_sid)
            _sref.set({"locked_by_user": current_user.user_id, "updated_at": datetime.utcnow()}, merge=True)
            prelocked = True
            slot_ref = _sref
        except Exception:
            prelocked = False
        # Atomic capacity reservation for today
        try:
            issued = _increment_daily_issued(db, doctor_id, now_local.date())
            today_capacity = _get_today_capacity(doctor_data)
            if issued > today_capacity:
                _rollback_daily_issued(db, doctor_id, now_local.date())
                if prelocked:
                    _release_slot_lock(db, doctor_id, appointment_date)
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="All tokens for today are booked. Please choose another day.")
        except HTTPException:
            raise
        except Exception:
            # Best effort: if capacity check fails, allow booking to continue
            pass
    else:
        local_appt = _to_local_clock(appointment_date)
        # If future date without time (00:00), require time selection
        if local_appt.date() > now_local.date() and local_appt.hour == 0 and local_appt.minute == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For future appointments, please provide both date and time."
            )
        # If it's today but time not provided (00:00), auto-allocate earliest minute today
        if local_appt.date() == now_local.date() and local_appt.hour == 0 and local_appt.minute == 0:
            # Enforce daily capacity for today before allocating
            todays_count = _count_doctor_bookings_for_date(db, doctor_id, now_local.date())
            if todays_count >= daily_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Doctor's daily capacity reached for today. Max: {daily_capacity}. Please choose another day."
                    )
                )
            try:
                appointment_date = _allocate_same_day_slot(db, doctor_id, hospital_id, now_local, doctor_data)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=("That slot was just taken. Queue is first-come, first-served for today.")
                )
            # Mark allocator-created lock as owned by current user
            try:
                _sid2 = _slot_id_for(doctor_id, appointment_date)
                _sref2 = db.collection(COLLECTIONS["APPOINTMENTS"]).document(_sid2)
                _sref2.set({"locked_by_user": current_user.user_id, "updated_at": datetime.utcnow()}, merge=True)
                prelocked = True
                slot_ref = _sref2
            except Exception:
                prelocked = False
            # Atomic capacity reservation for today
            try:
                issued = _increment_daily_issued(db, doctor_id, now_local.date())
                today_capacity = _get_today_capacity(doctor_data)
                if issued > today_capacity:
                    _rollback_daily_issued(db, doctor_id, now_local.date())
                    if prelocked:
                        _release_slot_lock(db, doctor_id, appointment_date)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="All tokens for today are booked. Please choose another day.")
            except HTTPException:
                raise
            except Exception:
                pass
        elif local_appt.date() == now_local.date():
            # If a time is provided for today but is before start_time, snap to start_time; if after end_time, reject
            # Also enforce daily capacity for today
            todays_count = _count_doctor_bookings_for_date(db, doctor_id, now_local.date())
            if todays_count >= daily_capacity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Doctor's daily capacity reached for today. Max: {daily_capacity}. Please choose another day."
                    )
                )
            start_min = _parse_hhmm_to_minutes(doctor_data.get("start_time") or "")
            end_min = _parse_hhmm_to_minutes(doctor_data.get("end_time") or "")
            if start_min is not None and end_min is not None:
                appt_min = local_appt.hour * 60 + local_appt.minute
                if appt_min < start_min:
                    appointment_date = local_appt.replace(hour=start_min // 60, minute=start_min % 60, second=0, microsecond=0)
                elif appt_min > end_min:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Doctor not available at {local_appt.strftime('%I:%M %p')} local. Available window: "
                            f"{doctor_data.get('start_time')}-{doctor_data.get('end_time')}; Days: "
                            f"{', '.join([str(d).title() for d in (doctor_data.get('available_days') or [])]) or 'N/A'}."
                        )
                    )
            # Atomic capacity reservation for today (explicit time path)
            try:
                issued = _increment_daily_issued(db, doctor_id, now_local.date())
                today_capacity = _get_today_capacity(doctor_data)
                if issued > today_capacity:
                    _rollback_daily_issued(db, doctor_id, now_local.date())
                    if prelocked:
                        _release_slot_lock(db, doctor_id, appointment_date)
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="All tokens for today are booked. Please choose another day.")
            except HTTPException:
                raise
            except Exception:
                pass

    # -------------------- Enforce Doctor Schedule --------------------
    # doctor_data already loaded above
    # Treat explicit OFFLINE as unavailable
    try:
        status_val = str(doctor_data.get("status") or "").lower()
        queue_paused = bool(doctor_data.get("queue_paused")) or bool(doctor_data.get("paused"))
        if status_val in {"offline", "on_leave"} or queue_paused:
            avail_days = [str(d).title() for d in (doctor_data.get("available_days") or [])]
            start_hhmm = doctor_data.get("start_time") or ""
            end_hhmm = doctor_data.get("end_time") or ""
            window_txt = f"{start_hhmm}-{end_hhmm}" if start_hhmm and end_hhmm else "Unavailable"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Doctor unavailable due to emergency/unavailability. Available days: {', '.join(avail_days) or 'N/A'}; Time: {window_txt}."
            )
    except Exception:
        pass

    # Validate available days (use client local clock)
    try:
        local_dt = _to_local_clock(appointment_date)
        appt_day = local_dt.strftime("%A").lower()
        days_raw = _normalize_available_days(doctor_data.get("available_days"))
        if not _day_in_list(days_raw, appt_day):
            avail_days = [str(d).title() for d in days_raw]
            start_hhmm = doctor_data.get("start_time") or ""
            end_hhmm = doctor_data.get("end_time") or ""
            window_txt = f"{start_hhmm}-{end_hhmm}" if start_hhmm and end_hhmm else "Unavailable"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Doctor not available on {appt_day.title()} at {local_dt.strftime('%a %I:%M %p')} local. "
                    f"Available days: {', '.join(avail_days) or 'N/A'}; Time: {window_txt}."
                )
            )
    except Exception:
        # If we cannot determine, fail safe by allowing
        pass

    # Validate time window (use client local clock)
    local_dt = _to_local_clock(appointment_date)
    start_hhmm = doctor_data.get("start_time") or ""
    end_hhmm = doctor_data.get("end_time") or ""
    if start_hhmm and end_hhmm:
        if not _is_within_time_window(local_dt, start_hhmm, end_hhmm):
            avail_days = [str(d).title() for d in (doctor_data.get("available_days") or [])]
            appt_str = local_dt.strftime('%I:%M %p')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Doctor not available at {appt_str} local. Available window: {start_hhmm}-{end_hhmm}; "
                    f"Days: {', '.join(avail_days) or 'N/A'}."
                )
            )
    else:
        # If schedule times are missing, disallow booking to prevent 24/7 by accident
        avail_days = [str(d).title() for d in (doctor_data.get("available_days") or [])]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Doctor schedule not configured. Please book during available timings. Days: {', '.join(avail_days) or 'N/A'}."
        )

    # -------------------- Atomic Per-Day Allocation (no minute-level create) --------------------
    # Use capacity doc keyed by (doctor_id, hospital_id, local_day) to allocate a sequential token number
    # and write the token document within the same Firestore transaction. This avoids 500s on contention.
    tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
    if hasattr(appointment_date, "tzinfo"):
        day_local = _local_day_for(appointment_date, tz_minutes)
    else:
        day_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)

    # Compute XOR fingerprint key for hour-slot conflict prevention.
    fp_name = str(fingerprint_name or "").strip()
    fp_phone = str(fingerprint_phone or "").strip()
    if not fp_name or not fp_phone:
        try:
            udoc = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id).get()
            u = udoc.to_dict() if getattr(udoc, "exists", False) else {}
            fp_name = fp_name or str(u.get("name") or u.get("full_name") or "").strip()
            fp_phone = fp_phone or str(u.get("phone") or u.get("mobile") or "").strip()
        except Exception:
            pass
    if not fp_name:
        fp_name = str(current_user.user_id)
    if not fp_phone:
        fp_phone = str(current_user.user_id)
    fingerprint_key = _xor_key(fp_name, fp_phone)

    cap_ref = db.collection(COLLECTIONS["CAPACITY"]).document(_capacity_doc_id(doctor_id, hospital_id, day_local))

    # Precompute mapping inputs
    start_hhmm = (doctor_data or {}).get("start_time") or "09:00"
    end_hhmm = (doctor_data or {}).get("end_time") or "17:00"

    # Build a base_utc pinned to the local day midnight to ensure deterministic mapping for any date
    base_local_midnight = datetime(
        day_local.year,
        day_local.month,
        day_local.day,
        0,
        0,
        tzinfo=timezone(timedelta(minutes=tz_minutes)),
    )
    base_utc = base_local_midnight.astimezone(timezone.utc)

    try:
        from google.cloud import firestore
        transaction = db.transaction()

        @firestore.transactional
        def allocate_and_create(tx):
            snap = cap_ref.get(transaction=tx)
            data = snap.to_dict() if getattr(snap, "exists", False) else {}
            capacity_val = int(data.get("capacity") or _get_today_capacity(doctor_data))
            booked = int(data.get("booked_count", 0))
            last_num = int(data.get("last_token_number", 0))
            if booked >= capacity_val:
                raise HTTPException(status_code=409, detail="Doctor's daily capacity reached for that date.")

            token_no = last_num + 1
            # Update capacity state
            if not data.get("now_serving_number"):
                data["now_serving_number"] = 1
            if not data.get("per_patient_minutes"):
                data["per_patient_minutes"] = int((doctor_data or {}).get("per_patient_minutes") or 5)
            data.update({
                "doctor_id": doctor_id,
                "hospital_id": hospital_id,
                "date": str(day_local),
                "tz_offset_minutes": tz_minutes,
                "capacity": capacity_val,
                "booked_count": booked + 1,
                "last_token_number": token_no,
                "updated_at": datetime.utcnow(),
            })
            tx.set(cap_ref, data, merge=True)

            # Compute appointment time from token number deterministically and map to UTC
            appt_dt_utc = _minute_for_token_number(start_hhmm, end_hhmm, token_no, tz_minutes, base_utc=base_utc)

            # Hour-slot lock for this fingerprint in clinic-local hour
            slot_hour = _slot_hour_key(appt_dt_utc, tz_minutes)
            lock_id = f"{fingerprint_key}_{slot_hour}"
            lock_ref = db.collection("token_hour_locks").document(lock_id)
            lock_snap = lock_ref.get(transaction=tx)
            if getattr(lock_snap, "exists", False):
                lock = lock_snap.to_dict() or {}
                existing_token_id = str(lock.get("token_id") or "").strip()
                if existing_token_id:
                    existing_ref = db.collection(COLLECTIONS["TOKENS"]).document(existing_token_id)
                    existing_snap = existing_ref.get(transaction=tx)
                    existing = existing_snap.to_dict() if getattr(existing_snap, "exists", False) else {}
                    existing_status = str(getattr(existing.get("status"), "value", existing.get("status")) or "").lower()
                    if existing_status not in ("cancelled", "completed"):
                        return {"conflict": True, "existing_token_id": existing_token_id}

            # Prepare token doc and write inside the same transaction
            tokens_ref = db.collection(COLLECTIONS["TOKENS"])
            token_ref = tokens_ref.document()
            token_doc = {
                "id": token_ref.id,
                "token_number": token_no,
                "patient_id": current_user.user_id,
                "mrn": patient_mrn,
                "doctor_id": doctor_id,
                "hospital_id": hospital_id,
                "appointment_date": appt_dt_utc,
                "fingerprint_key": fingerprint_key,
                "slot_hour": slot_hour,
                "status": TokenStatus.PENDING,
                "payment_status": PaymentStatus.PENDING,
                "doctor_name": (doctor_data or {}).get("name"),
                "doctor_room": (doctor_data or {}).get("room") or (doctor_data or {}).get("room_number"),
                "doctor_room_number": (doctor_data or {}).get("room_number") or (doctor_data or {}).get("room"),
                "hospital_name": (hospital_data or {}).get("name"),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            tx.set(token_ref, token_doc)
            tx.set(
                lock_ref,
                {
                    "fingerprint_key": fingerprint_key,
                    "slot_hour": slot_hour,
                    "token_id": token_ref.id,
                    "patient_id": current_user.user_id,
                    "doctor_id": doctor_id,
                    "hospital_id": hospital_id,
                    "updated_at": datetime.utcnow(),
                },
                merge=True,
            )
            return {"conflict": False, "token_no": token_no, "appt_dt_utc": appt_dt_utc, "token_id": token_ref.id, "slot_hour": slot_hour}

        alloc = allocate_and_create(transaction)
    except Exception as e:
        # Map Firestore transaction contention/exists to 409 with a clear, user-facing message
        try:
            from google.api_core.exceptions import AlreadyExists, Aborted
            if isinstance(e, (AlreadyExists, Aborted)):
                raise HTTPException(status_code=409, detail="This slot was just taken. Please try again.")
        except Exception:
            pass
        # Fallback: treat as high-activity conflict instead of 500
        raise HTTPException(status_code=409, detail="Unable to reserve at this moment due to high activity. Please try again.")

    # Conflict path: return the existing token (200 OK, no new booking)
    if isinstance(alloc, dict) and alloc.get("conflict"):
        existing_token_id = str(alloc.get("existing_token_id") or "").strip()
        if existing_token_id:
            snap = db.collection(COLLECTIONS["TOKENS"]).document(existing_token_id).get()
            existing = snap.to_dict() if getattr(snap, "exists", False) else None
            if existing:
                if not existing.get("id"):
                    existing["id"] = existing_token_id
                return SmartTokenResponse(**existing)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already booked in this hour")

    token_number = int(alloc.get("token_no") or 0)
    appointment_date = alloc.get("appt_dt_utc")
    token_id = str(alloc.get("token_id") or "").strip()
    if not token_number or not token_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to allocate token")

    # Derive a stable hex-like code (legacy compatibility)
    hex_code = f"{token_id[:8]}{token_number:03d}"

    # Human-friendly code
    try:
        display_code = SmartTokenService.generate_display_code()
    except Exception:
        display_code = None

    # Get queue status for this token (include appointment_date for correct same-day handling)
    queue_status = SmartTokenService.get_queue_status(
        doctor_id,
        token_number,
        appointment_date=appointment_date,
    )

    # Create token data (doctor pricing + token fee)
    requires_payment = True

    dept_text = (
        f"{(doctor_data or {}).get('specialization') or ''} "
        f"{(doctor_data or {}).get('subcategory') or ''} "
        f"{(doctor_data or {}).get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text
        for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )

    from app.services.fee_calculator import compute_total_amount

    # Step 5 validation exactly as requested
    if not (doctor_data or {}).get("consultation_fee"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Consultation fee missing")
    if inferred_has_session and (include_session_fee is None or include_session_fee is True) and not (doctor_data or {}).get("session_fee"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session fee required")

    pricing = compute_total_amount(
        consultation_fee=(doctor_data or {}).get("consultation_fee"),
        session_fee=(doctor_data or {}).get("session_fee"),
        include_consultation_fee=include_consultation_fee,
        include_session_fee=include_session_fee,
    )

    token_data = {
        "token_number": token_number,
        "hex_code": hex_code,
        "display_code": display_code,
        "patient_id": current_user.user_id,
        "mrn": patient_mrn,
        "doctor_id": doctor_id,
        "hospital_id": hospital_id,
        "appointment_date": appointment_date,
        # Paid tokens are PENDING until /payments/confirm; free tokens are CONFIRMED immediately
        "status": TokenStatus.PENDING if requires_payment else TokenStatus.CONFIRMED,
        "payment_status": "pending" if requires_payment else "not_required",
        "payment_method": None,
        # 1-based position for UI; for future appointments keep 0
        "queue_position": (int(queue_status.get("people_ahead") or 0) + 1) if not queue_status.get("is_future_appointment") else 0,
        "total_queue": int(queue_status.get("total_queue") or 0),
        # For future appointments, keep 0 to avoid misleading UI
        "estimated_wait_time": int(queue_status.get("estimated_wait_time") or 0) if not queue_status.get("is_future_appointment") else 0,
        "is_future_appointment": queue_status.get("is_future_appointment", False),
        # Fee breakdown (token fee + selected doctor fees)
        "token_fee": pricing.get("token_fee"),
        "consultation_fee": pricing.get("consultation_fee"),
        "session_fee": pricing.get("session_fee"),
        "total_fee": pricing.get("total_fee"),
        "total_amount": pricing.get("total_amount"),
        "include_consultation_fee": pricing.get("include_consultation_fee"),
        "include_session_fee": pricing.get("include_session_fee"),
        # Embedded snapshots for resilient UI display
        "doctor_name": doctor_data.get("name"),
        "doctor_room": doctor_data.get("room") or doctor_data.get("room_number"),
        "doctor_room_number": doctor_data.get("room_number") or doctor_data.get("room"),
        "doctor_specialization": doctor_data.get("specialization") or doctor_data.get("department") or doctor_data.get("subcategory"),
        "doctor_avatar_initials": (
            doctor_data.get("avatar_initials")
            or ("".join([p[0] for p in str(doctor_data.get("name", "DR")).split()[:2]]).upper() or str(doctor_data.get("name", "DR")).upper()[:3])
        ),
        "hospital_name": hospital_data.get("name"),
        "fingerprint_key": fingerprint_key,
        "slot_hour": alloc.get("slot_hour"),
    }

    # Token already created transactionally. Enrich response fields and persist any display-only fields.
    token_data["id"] = token_id
    token_data["created_at"] = datetime.utcnow()
    token_data["updated_at"] = datetime.utcnow()
    try:
        db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
            {
                "display_code": token_data.get("display_code"),
                "hex_code": token_data.get("hex_code"),
                "doctor_specialization": token_data.get("doctor_specialization"),
                "doctor_avatar_initials": token_data.get("doctor_avatar_initials"),
                "doctor_room": token_data.get("doctor_room"),
                "doctor_room_number": token_data.get("doctor_room_number"),
                "total_queue": token_data.get("total_queue"),
                "queue_position": token_data.get("queue_position"),
                "estimated_wait_time": token_data.get("estimated_wait_time"),
                "is_future_appointment": token_data.get("is_future_appointment"),
                # Fee breakdown (doctor pricing)
                "consultation_fee": token_data.get("consultation_fee"),
                "session_fee": token_data.get("session_fee"),
                "total_fee": token_data.get("total_fee"),
                "mrn": token_data.get("mrn"),
                "fingerprint_key": token_data.get("fingerprint_key"),
                "slot_hour": token_data.get("slot_hour"),
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
    except Exception:
        pass

    # Mark slot as booked with token linkage
    try:
        slot_ref.set(
            {
                "status": "booked",
                "token_id": token_id,
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
    except Exception:
        # Non-fatal; token is created, but slot metadata couldn't update
        pass

    # Create activity log for token generation
    await create_activity_log(
        current_user.user_id,
        ActivityType.TOKEN_GENERATED,
        f"Generated SmartToken #{token_number} for appointment",
        {
            "token_id": token_id,
            "token_number": token_number,
            "hex_code": hex_code,
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "appointment_date": appointment_date.isoformat(),
        },
    )

    # -------------------- Real-time Notifications (WhatsApp & SMS) --------------------
    # Fetch user's phone number
    try:
        user_snap = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id).get()
        user_phone = (user_snap.to_dict() or {}).get("phone") if getattr(user_snap, "exists", False) else None
    except Exception:
        user_phone = None

    # Format appointment time as a readable string
    try:
        appt_str = appointment_date.strftime("%I:%M %p") if hasattr(appointment_date, "strftime") else str(appointment_date)
    except Exception:
        appt_str = ""

    notif_types = [NotificationType.WHATSAPP, NotificationType.SMS]

    if user_phone:
        async def _dispatch_notifications():
            try:
                await NotificationService.send_token_confirmation_notification(
                    token_id=token_id,
                    phone_number=user_phone,
                    token_number=str(token_number),
                    doctor_name=doctor_data.get("name") or "Doctor",
                    hospital_name=hospital_data.get("name") or "Hospital",
                    appointment_time=appt_str,
                    notification_types=notif_types,
                )
            except Exception:
                # Best-effort: do not block booking on notification errors
                pass

            try:
                # Template-based scheduling (case 1/2/3) using app/templates.py
                await schedule_messages(
                    {
                        "id": token_id,
                        "token_number": token_number,
                        "patient_id": current_user.user_id,
                        "patient_phone": user_phone,
                        "patient_name": (user_snap.to_dict() or {}).get("name") if getattr(user_snap, "exists", False) else None,
                        "doctor_id": doctor_id,
                        "doctor_name": doctor_data.get("name"),
                        "doctor_room": doctor_data.get("room") or doctor_data.get("room_number"),
                        "doctor_room_number": doctor_data.get("room_number") or doctor_data.get("room"),
                        "hospital_id": hospital_id,
                        "hospital_name": hospital_data.get("name"),
                        "appointment_date": appointment_date,
                        "appointment_time": appointment_date,
                        "estimated_wait_time": token_data.get("estimated_wait_time"),
                    }
                )
            except Exception:
                pass

        try:
            asyncio.create_task(_dispatch_notifications())
        except Exception:
            try:
                await _dispatch_notifications()
            except Exception:
                pass

    # Compute convenience flag for UI
    token_data["is_active"] = token_data.get("status") not in ["cancelled", "completed"]
    return SmartTokenResponse(**token_data)

# JSON-body variants and path aliases for mobile clients
@router.post("/generate/json")
@router.post("/generate-token")
@router.post("/book")
@router.post("/create")
@router.post("/token/generate")
async def generate_smart_token_json(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user = Depends(get_current_active_user),
):
    """Unified token create endpoint.

    - Default: existing SmartToken booking logic (doctor_id + hospital_id + optional appointment_date)
    - Queue mode: set header `X-Token-Mode: queue` or query `?mode=queue` and send hospital queue payload
    """

    mode = (request.headers.get("X-Token-Mode") or request.query_params.get("mode") or "").strip().lower()
    if mode == "queue":
        try:
            spec = QueueTokenCreateRequest(**(payload or {}))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid queue token payload")

        db = get_db()

        # Allocate next token number for this hospital+doctor (resets daily)
        day = _to_local_clock(datetime.utcnow().replace(tzinfo=timezone.utc)).date()
        token_number = _allocate_queue_token_number(db, spec.hospital_id, spec.doctor_id, day)
        now = datetime.utcnow()

        try:
            patient_mrn = get_or_create_patient_mrn(db, hospital_id=spec.hospital_id, patient_id=spec.patient_id)
        except Exception:
            patient_mrn = None
        
        # Persist token document
        doc_ref = db.collection(COLLECTIONS["TOKENS"]).document()
        token_id = doc_ref.id
        token_doc = {
            "token_id": token_id,
            "id": token_id,
            "hospital_id": spec.hospital_id,
            "department_id": spec.department_id,
            "doctor_id": spec.doctor_id,
            "patient_id": spec.patient_id,
            "patient_name": spec.patient_name,
            "mrn": patient_mrn,
            "token_number": int(token_number),
            "queue_day": str(day),
            "status": "waiting",
            "created_at": now,
            "updated_at": now,
        }
        doc_ref.set(token_doc)

        logger.info(
            "Queue token created",
            extra={
                "token_id": token_id,
                "hospital_id": spec.hospital_id,
                "doctor_id": spec.doctor_id,
                "patient_id": spec.patient_id,
                "token_number": token_number,
                "created_by": getattr(current_user, "user_id", None),
            },
        )

        return {"success": True, "token_number": int(token_number), "message": "Token booked successfully"}

    # Slot-based booking (explicit day + time)
    if isinstance(payload, dict) and (payload.get("day") or payload.get("time")):
        doctor_id = str(payload.get("doctor_id") or "").strip()
        hospital_id = str(payload.get("hospital_id") or "").strip()
        day = str(payload.get("day") or "").strip()
        time = str(payload.get("time") or "").strip()
        include_consultation_fee = payload.get("include_consultation_fee")
        include_session_fee = payload.get("include_session_fee")
        if not doctor_id or not hospital_id or not day or not time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doctor_id, hospital_id, day, time are required")

        from app.services.slot_booking_service import (
            reserve_slot_transactionally,
            finalize_slot_booking,
            appointment_dt_utc_for,
            _parse_day_dd_mm_yyyy,
            _parse_time_hhmm_ampm,
        )

        # Reserve slot first (prevents double booking)
        reservation = reserve_slot_transactionally(
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            patient_id=str(getattr(current_user, "user_id", "")),
            day=day,
            time=time,
        )

        # Build appointment datetime to reuse existing booking logic
        d = _parse_day_dd_mm_yyyy(day)
        hh, mm = _parse_time_hhmm_ampm(time)
        appointment_date = appointment_dt_utc_for(d, hh, mm)

        token_resp: SmartTokenResponse = await generate_smart_token(
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            appointment_date=appointment_date,
            current_user=current_user,
            include_consultation_fee=include_consultation_fee if isinstance(include_consultation_fee, bool) else None,
            include_session_fee=include_session_fee if isinstance(include_session_fee, bool) else None,
        )

        # Persist day/time on token doc for receptionist sync
        try:
            db = get_db()
            db.collection(COLLECTIONS["TOKENS"]).document(str(token_resp.id)).set(
                {
                    "day": day,
                    "time": time,
                    "updated_at": datetime.utcnow(),
                },
                merge=True,
            )
        except Exception:
            pass

        # Finalize slot booking with token id
        try:
            finalize_slot_booking(str(reservation.get("slot_id") or reservation.get("id")), str(token_resp.id))
        except Exception:
            pass

        return token_resp

    # Default SmartToken booking (legacy)
    try:
        spec = SmartTokenGenerateRequest(**(payload or {}))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token payload")

    return await generate_smart_token(
        doctor_id=spec.doctor_id,
        hospital_id=spec.hospital_id,
        appointment_date=spec.appointment_date,
        current_user=current_user,
    )


@router.get("/hospital/{hospital_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def get_hospital_queue_tokens(
    hospital_id: str,
    include_completed: bool = Query(False, description="If true, include completed/cancelled tokens"),
    limit: int = Query(500, ge=1, le=2000),
    current_user = Depends(get_current_active_user),
) -> Any:
    db = get_db()
    ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)

    docs: List[Dict[str, Any]] = []
    try:
        if hasattr(ref, "order_by"):
            q = ref.order_by("created_at").limit(int(limit))
            docs = [d.to_dict() for d in q.stream()]
        else:
            docs = [d.to_dict() for d in ref.limit(int(limit)).stream()]
    except Exception:
        docs = [d.to_dict() for d in ref.limit(int(limit)).stream()]

    items: List[Dict[str, Any]] = []
    for t in docs:
        st = str(t.get("status") or "").strip().lower()
        if not include_completed and st in ("completed", "cancelled", "canceled"):
            continue
        if not t.get("mrn") and t.get("patient_id"):
            try:
                t["mrn"] = get_or_create_patient_mrn(db, hospital_id=hospital_id, patient_id=str(t.get("patient_id")))
            except Exception:
                pass
        items.append(
            {
                "token_id": t.get("token_id") or t.get("id"),
                "token_number": t.get("token_number"),
                "patient_name": t.get("patient_name"),
                "mrn": t.get("mrn"),
                "doctor_id": t.get("doctor_id"),
                "department_id": t.get("department_id") or t.get("doctor_specialization"),
                "status": st or t.get("status"),
            }
        )

    # Ensure ordered by created_at asc in-memory as a fallback
    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    items.sort(key=lambda x: _to_dt((next((d for d in docs if (d.get("token_id") or d.get("id")) == x.get("token_id")), {}) or {}).get("created_at")) or datetime.min)
    return items


@router.patch("/update-status/{token_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def update_queue_token_status(
    token_id: str,
    payload: QueueTokenStatusUpdate,
    current_user = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = ref.get()
    if not _snap_exists(snap):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    new_status = _coerce_status(payload.status)
    ref.set({"status": new_status, "updated_at": datetime.utcnow()}, merge=True)

    logger.info(
        "Queue token status updated",
        extra={"token_id": token_id, "status": new_status, "user_id": getattr(current_user, "user_id", None)},
    )
    return {"success": True, "message": "Status updated"}

@router.get("/my-tokens", response_model=List[SmartTokenResponse])
async def get_my_tokens(
    only_active: bool = Query(True, description="If true, exclude cancelled/completed tokens"),
    current_user = Depends(get_current_active_user),
    response: Response = None
):
    """Get all SmartTokens for the current user"""
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    query = tokens_ref.where("patient_id", "==", current_user.user_id)
    docs = query.stream()
    
    # Collect and sort by updated_at desc in memory (avoid Firestore composite indexes)
    raw_tokens = []
    for doc in docs:
        d = doc.to_dict()
        if only_active:
            status_val = str(d.get("status") or "").lower()
            if status_val in ["cancelled", "completed"]:
                continue
        raw_tokens.append(d)

    raw_tokens.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)

    # Add is_active flag to each token
    enriched = []
    for t in raw_tokens:
        if not t.get("mrn") and t.get("hospital_id") and t.get("patient_id"):
            try:
                t["mrn"] = get_or_create_patient_mrn(db, hospital_id=str(t.get("hospital_id")), patient_id=str(t.get("patient_id")))
                # Best-effort persist on token doc for faster future reads
                try:
                    tid = str(t.get("id") or "")
                    if tid:
                        db.collection(COLLECTIONS["TOKENS"]).document(tid).set({"mrn": t.get("mrn"), "updated_at": datetime.utcnow()}, merge=True)
                except Exception:
                    pass
            except Exception:
                pass
        t["is_active"] = t.get("status") not in ["cancelled", "completed"]
        enriched.append(SmartTokenResponse(**t))
    # Prevent caching so new tokens appear immediately
    try:
        if response is not None:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return enriched

@router.get("/my-tokens/details")
async def get_my_tokens_details(
    only_active: bool = Query(True, description="If true, exclude cancelled/completed tokens"),
    current_user = Depends(get_current_active_user),
    response: Response = None
):
    """Get all SmartTokens for the current user with embedded doctor and hospital details.

    This is intended for the My Tokens screen to show doctor name, specialization,
    hospital name and a friendly appointment time alongside each token.
    """
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", current_user.user_id)
    docs = list(tokens_ref.stream())

    tokens = []
    for d in docs:
        data = d.to_dict()
        if only_active:
            status_val = str(data.get("status") or "").lower()
            if status_val in ["cancelled", "completed"]:
                continue
        tokens.append(data)
    tokens.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)

    items = []
    for t in tokens:
        # Fetch doctor
        doctor = None
        try:
            dref = db.collection(COLLECTIONS["DOCTORS"]).document(t.get("doctor_id"))
            doctor = dref.get().to_dict()
        except Exception:
            doctor = None

        # Fetch hospital
        hospital = None
        try:
            href = db.collection(COLLECTIONS["HOSPITALS"]).document(t.get("hospital_id"))
            hospital = href.get().to_dict()
        except Exception:
            hospital = None

        # Friendly appointment time: hide for same-day bookings
        appt_dt = t.get("appointment_date")
        try:
            if hasattr(appt_dt, 'strftime'):
                from datetime import datetime as _dt
                if appt_dt.date() == _dt.utcnow().date():
                    appointment_time_str = ""
                else:
                    appointment_time_str = appt_dt.strftime("%I:%M %p")
            else:
                appointment_time_str = ""
        except Exception:
            appointment_time_str = ""

        # is_active for UI filtering
        t["is_active"] = t.get("status") not in ["cancelled", "completed"]

        # Live queue status for card display (handles same-day vs future correctly)
        try:
            queue_status = SmartTokenService.get_queue_status(
                doctor_id=t.get("doctor_id"),
                token_number=t.get("token_number"),
                appointment_date=t.get("appointment_date"),
            )
        except Exception:
            queue_status = {"people_ahead": 0, "estimated_wait_time": 0, "total_queue": 0, "current_token": 0, "is_future_appointment": False}

        items.append({
            "token": SmartTokenResponse(**t),
            "doctor": {
                "id": t.get("doctor_id"),
                "name": t.get("doctor_name") or (doctor or {}).get("name") or "Dr. Doctor",
                "specialization": t.get("doctor_specialization")
                or (doctor or {}).get("specialization")
                or (doctor or {}).get("department")
                or (doctor or {}).get("subcategory")
                or "General",
                "avatar_initials": t.get("doctor_avatar_initials") or (doctor or {}).get("avatar_initials") or ((doctor or {}).get("name", "DR")[:3].upper())
            },
            "hospital": {
                "id": t.get("hospital_id"),
                "name": t.get("hospital_name") or (hospital or {}).get("name") or "Hospital"
            },
            "appointment_time": appointment_time_str,
            "queue": queue_status,
        })

    result = {
        "items": items,
        "total": len(items)
    }
    # Prevent caching so new tokens appear immediately
    try:
        if response is not None:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return result

@router.get("/my-active", response_model=SmartTokenResponse)
async def get_my_active_token(
    current_user = Depends(get_current_active_user)
):
    """Return the user's most recent active token (not cancelled/completed). 404 if none."""
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", current_user.user_id)
    docs = list(tokens_ref.stream())

    candidates = []
    for d in docs:
        data = d.to_dict()
        status_val = str(data.get("status") or "").lower()
        if status_val not in ["cancelled", "completed"]:
            candidates.append(data)

    if not candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active token found")

    candidates.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)
    # include is_active
    c0 = candidates[0]
    if not c0.get("mrn") and c0.get("hospital_id") and c0.get("patient_id"):
        try:
            c0["mrn"] = get_or_create_patient_mrn(db, hospital_id=str(c0.get("hospital_id")), patient_id=str(c0.get("patient_id")))
            try:
                tid = str(c0.get("id") or "")
                if tid:
                    db.collection(COLLECTIONS["TOKENS"]).document(tid).set({"mrn": c0.get("mrn"), "updated_at": datetime.utcnow()}, merge=True)
            except Exception:
                pass
        except Exception:
            pass
    c0["is_active"] = c0.get("status") not in ["cancelled", "completed"]
    return SmartTokenResponse(**c0)

@router.get("/my-active-details")
async def get_my_active_token_details(
    current_user = Depends(get_current_active_user)
):
    """Return enriched details for the user's most recent active token, for startup restore."""
    # Reuse the logic above to find the active token, then call appointment-details
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", current_user.user_id)
    docs = list(tokens_ref.stream())
    
    # Collect and sort by updated_at desc in memory (avoid Firestore composite indexes)
    candidates = []
    for d in docs:
        data = d.to_dict()
        status_val = str(data.get("status") or "").lower()
        if status_val not in ["cancelled", "completed"]:
            candidates.append(data)

    if not candidates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active token found")

    candidates.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)
    active_token_id = candidates[0]["id"]
    
    # Delegate to appointment-details for consistent structure
    return await get_appointment_details(active_token_id, current_user)

@router.get("/generate/form-data")
async def generate_token_form_data(
    current_user = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="If provided, return departments and doctors for this hospital"),
    department: Optional[str] = Query(None, description="If provided, filter doctors by department"),
) -> Dict[str, Any]:
    """Patient Portal: dropdown data for the 'Generate New Token' page."""
    db = get_db()

    def _s(v: Any) -> str:
        try:
            return str(v or "").strip()
        except Exception:
            return ""

    def _is_available(d: Dict[str, Any]) -> bool:
        st = _s(d.get("status")).lower()
        return st in ("available", "active", "")

    # Step 1: hospitals
    if not hospital_id:
        hs = [d.to_dict() for d in db.collection(COLLECTIONS["HOSPITALS"]).limit(2000).stream()]
        hospitals = [{"id": h.get("id"), "name": h.get("name"), "city": h.get("city")} for h in hs if h.get("id") and h.get("name")]
        return {"success": True, "data": {"hospitals": hospitals}}

    hid = _s(hospital_id)
    dep_norm = _s(department).lower()

    # Step 2: departments
    departments: List[Dict[str, Any]] = []
    try:
        dep_docs = list(db.collection("departments").where("hospital_id", "==", hid).limit(2000).stream())
        departments = [d.to_dict() for d in dep_docs]
    except Exception:
        departments = []

    if departments:
        departments_out = [{"id": x.get("id"), "name": x.get("name"), "hospital_id": x.get("hospital_id")} for x in departments if _s(x.get("name"))]
    else:
        docs = [d.to_dict() for d in db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hid).limit(2000).stream()]
        specs = sorted({_s(d.get("specialization")) for d in docs if _s(d.get("specialization"))})
        departments_out = [{"id": s.lower().replace(" ", "_"), "name": s, "hospital_id": hid} for s in specs]

    # Step 3: doctors (optional)
    docs_ref = db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hid)
    docs = [d.to_dict() for d in docs_ref.limit(2000).stream()]
    doctors_out = []
    for d in docs:
        spec = _s(d.get("specialization"))
        if dep_norm and spec.lower() != dep_norm:
            continue
        doctors_out.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "department": spec,
            "room": d.get("room") or d.get("room_number"),
            "status": _s(d.get("status")).lower(),
            "is_available": _is_available(d),
        })

    return {"success": True, "data": {"hospital_id": hid, "departments": departments_out, "doctors": doctors_out}}

@router.post("/generate/by-selection")
async def generate_token_by_selection(
    payload: Dict[str, Any] = Body(...),
    current_user = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Patient Portal: create token from hospital + department selection."""
    db = get_db()

    def _s(v: Any) -> str:
        try:
            return str(v or "").strip()
        except Exception:
            return ""

    hospital_id = _s((payload or {}).get("hospital_id"))
    department = _s((payload or {}).get("department"))
    doctor_id = _s((payload or {}).get("doctor_id"))
    assign_any = bool((payload or {}).get("assign_any_available_doctor"))

    # Patient details (from booking form)
    full_name = _s((payload or {}).get("full_name") or (payload or {}).get("name"))
    phone = _s((payload or {}).get("phone") or (payload or {}).get("phone_number"))
    family_name = _s((payload or {}).get("family_name"))
    family_phone = _s((payload or {}).get("family_phone"))
    gender = _s((payload or {}).get("gender"))
    reason = _s((payload or {}).get("reason") or (payload or {}).get("reason_for_visit"))
    special_notes = _s((payload or {}).get("special_notes") or (payload or {}).get("notes"))
    age_val = (payload or {}).get("age")
    try:
        age = int(age_val) if age_val is not None and str(age_val).strip() != "" else None
    except Exception:
        age = None

    if not hospital_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="hospital_id is required")
    if not department:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="department is required")

    # Professional validation for required patient fields
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="full_name is required")
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone is required")
    if not gender:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="gender is required")
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")

    # Persist patient details into USERS (best-effort)
    try:
        uref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
        uref.set(
            {
                "name": full_name,
                "phone": phone,
                "age": age,
                "gender": gender,
                "special_notes": special_notes or None,
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
    except Exception:
        pass

    chosen_id: Optional[str] = None
    if doctor_id and not assign_any:
        snap = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).get()
        if not getattr(snap, "exists", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        dd = snap.to_dict() or {}
        if _s(dd.get("hospital_id")) != hospital_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor does not belong to selected hospital")
        chosen_id = doctor_id
    else:
        docs = [d.to_dict() for d in db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hospital_id).limit(2000).stream()]
        dep_norm = department.lower()
        for d in docs:
            if _s(d.get("specialization")).lower() != dep_norm:
                continue
            st = _s(d.get("status")).lower()
            if st in ("available", "active", ""):
                chosen_id = _s(d.get("id"))
                break

    if not chosen_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available doctor found for selected department")

    fp_name = family_name if (family_name and family_phone) else full_name
    fp_phone = family_phone if (family_name and family_phone) else phone
    result = await generate_smart_token_with_details(
        SmartTokenGenerateRequest(doctor_id=chosen_id, hospital_id=hospital_id, appointment_date=None),
        current_user=current_user,
        fingerprint_name=fp_name,
        fingerprint_phone=fp_phone,
    )

    # Ensure MRN is available on token + response
    try:
        mrn_val = get_or_create_patient_mrn(db, hospital_id=hospital_id, patient_id=current_user.user_id)
        token_obj = (result or {}).get("token")
        token_id = getattr(token_obj, "id", None) if token_obj is not None else None
        if token_id and mrn_val:
            db.collection(COLLECTIONS["TOKENS"]).document(str(token_id)).set({"mrn": mrn_val, "updated_at": datetime.utcnow()}, merge=True)
        if token_obj is not None and mrn_val:
            try:
                setattr(token_obj, "mrn", mrn_val)
            except Exception:
                pass
    except Exception:
        pass

    # Persist patient details onto token doc and enrich response (best-effort)
    try:
        token_obj = (result or {}).get("token")
        token_id = getattr(token_obj, "id", None) if token_obj is not None else None
        if token_id:
            db.collection(COLLECTIONS["TOKENS"]).document(str(token_id)).set(
                {
                    "patient_name": full_name,
                    "patient_phone": phone,
                    "patient_age": age,
                    "patient_gender": gender,
                    "reason_for_visit": reason,
                    "special_notes": special_notes or None,
                    "updated_at": datetime.utcnow(),
                    "created_via": (result or {}).get("created_via") or "patient_portal",
                },
                merge=True,
            )
        # Update response token object too
        if token_obj is not None:
            try:
                setattr(token_obj, "patient_name", full_name)
                setattr(token_obj, "patient_phone", phone)
                setattr(token_obj, "patient_age", age)
                setattr(token_obj, "patient_gender", gender)
                setattr(token_obj, "reason_for_visit", reason)
                setattr(token_obj, "special_notes", special_notes or None)
            except Exception:
                pass
    except Exception:
        pass

    return result

@router.get("/{token_id}", response_model=SmartTokenResponse)
async def get_token(token_id: str, current_user = Depends(get_current_active_user)):
    """Get SmartToken by ID (only if user owns the token)"""
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()

    if token_data and (not token_data.get("mrn")) and token_data.get("hospital_id") and token_data.get("patient_id"):
        try:
            token_data["mrn"] = get_or_create_patient_mrn(db, hospital_id=str(token_data.get("hospital_id")), patient_id=str(token_data.get("patient_id")))
            try:
                db.collection(COLLECTIONS["TOKENS"]).document(token_id).set({"mrn": token_data.get("mrn"), "updated_at": datetime.utcnow()}, merge=True)
            except Exception:
                pass
        except Exception:
            pass
    
    # Check if user owns this token
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return SmartTokenResponse(**token_data)

@router.post("/{token_id}/payment", response_model=PaymentResponse)
async def process_payment(
    token_id: str,
    payment: PaymentCreate,
    current_user = Depends(get_current_active_user)
):
    """Process payment for a SmartToken"""
    db = get_db()
    
    # Get token
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Check if user owns this token
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Create payment record
    payment_ref = db.collection(COLLECTIONS["PAYMENTS"]).document()
    payment_data = payment.dict()
    payment_data["id"] = payment_ref.id
    # Ensure linkage to token and user for downstream refund lookups
    payment_data["token_id"] = token_id
    payment_data["user_id"] = token_data.get("patient_id")
    payment_data["method"] = payment_data.pop("payment_method")  # Map payment_method to method
    payment_data["created_at"] = datetime.utcnow()
    payment_data["updated_at"] = datetime.utcnow()
    
    payment_ref.set(payment_data)
    
    
    # Persist token-level fee for deterministic refunds/previews
    try:
        db.collection(COLLECTIONS["TOKENS"]).document(token_id).update({
            "token_fee": payment.amount,
            "payment_amount": payment.amount,
            # Back-compat for any older readers
            "amount": payment.amount,
            "updated_at": datetime.utcnow(),
        })
    except Exception:
        # Non-fatal: if this fails, preview may still fall back to payment lookup or specialization default
        pass

    # Update token payment status
    SmartTokenService.update_payment_status(
        token_id=token_id,
        payment_status=payment.status,
        payment_method=payment.payment_method
    )
    
    # Create activity log for payment
    await create_activity_log(
        current_user.user_id,
        ActivityType.PAYMENT_MADE,
        f"Payment processed for SmartToken #{token_data.get('token_number')}",
        {
            "token_id": token_id,
            "payment_id": payment_ref.id,
            "amount": payment.amount,
            "payment_method": payment.payment_method,
            "status": payment.status
        }
    )
    
    return PaymentResponse(**payment_data)

@router.put("/{token_id}/payment-status")
async def update_payment_status(
    token_id: str,
    payment_status: str,
    payment_method: str = None,
    current_user = Depends(get_current_active_user)
):
    """Update payment status of a SmartToken (for admin/reception use)"""
    # TODO: Add admin/reception role check
    
    # Update token payment status
    success = SmartTokenService.update_payment_status(
        token_id=token_id,
        payment_status=payment_status,
        payment_method=payment_method
    )
    
    if success:
        # Create activity log for payment status update
        await create_activity_log(
            current_user.user_id,
            ActivityType.PAYMENT_MADE,
            f"Payment status updated to {payment_status} for token {token_id}",
            {
                "token_id": token_id,
                "payment_status": payment_status,
                "payment_method": payment_method
            }
        )
        
        return {"message": "Payment status updated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update payment status"
        )

@router.get("/{token_id}/queue-status")
async def get_token_queue_status(
    token_id: str,
    current_user = Depends(get_current_active_user)
):
    """Return canonical queue object for the token's doctor and date."""
    db = get_db()
    snap = db.collection(COLLECTIONS["TOKENS"]).document(token_id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Token not found")
    token = snap.to_dict() or {}
    if token.get("patient_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Resolve clinic local day of the token's appointment
    doc_snap = db.collection(COLLECTIONS["DOCTORS"]).document(token["doctor_id"]).get()
    hosp_snap = db.collection(COLLECTIONS["HOSPITALS"]).document(token["hospital_id"]).get()
    doctor_data = doc_snap.to_dict() if getattr(doc_snap, "exists", False) else {}
    hospital_data = hosp_snap.to_dict() if getattr(hosp_snap, "exists", False) else {}
    tz_minutes = _tz_offset_for(doctor_data or {}, hospital_data or {})
    appt = token.get("appointment_date")
    if hasattr(appt, "tzinfo"):
        # appointment_date already a datetime; convert to local date
        day_local = _local_day_for(appt, tz_minutes)
    else:
        # Fallback to today local
        day_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)

    q = _queue_object_for(db, token["doctor_id"], token["hospital_id"], day_local, token.get("token_number"))
    # Mark future if appointment is not today
    today_local = _local_day_for(datetime.utcnow().replace(tzinfo=timezone.utc), tz_minutes)
    q["is_future"] = (day_local != today_local)
    return q

# -------------------- Spec: POST /tokens (atomic, idempotent) --------------------
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(spec: TokenCreateSpec, current_user = Depends(get_current_active_user)):
    """Create a token atomically for a specific doctor and clinic-local date with idempotency.

    - Ensures sequential token_number allocation per doctor+hospital+day (1..N)
    - Idempotency by (user, doctor, hospital, date, idempotency_key)
    - Returns canonical queue object along with token info
    """
    db = get_db()
    # Verify doctor and hospital
    dref = db.collection(COLLECTIONS["DOCTORS"]).document(spec.doctor_id)
    ds = dref.get()
    if not ds.exists:
        raise HTTPException(status_code=400, detail="Doctor not found")
    href = db.collection(COLLECTIONS["HOSPITALS"]).document(spec.hospital_id)
    hs = href.get()
    if not hs.exists:
        raise HTTPException(status_code=400, detail="Hospital not found")
    doctor_data = ds.to_dict() or {}
    hospital_data = hs.to_dict() or {}
    tz_minutes = _tz_offset_for(doctor_data, hospital_data)
    day = _parse_local_date(spec.appointment_date, tz_minutes)

    # Idempotency check
    idem_ref = db.collection(COLLECTIONS["IDEMPOTENCY"]).document(f"{current_user.user_id}_{spec.idempotency_key}")
    idem_snap = idem_ref.get()
    if getattr(idem_snap, "exists", False):
        prev = idem_snap.to_dict() or {}
        # Return existing token info
        token_id = prev.get("token_id")
        if token_id:
            t = db.collection(COLLECTIONS["TOKENS"]).document(token_id).get().to_dict()
            q = _queue_object_for(db, spec.doctor_id, spec.hospital_id, day, t.get("token_number") if t else None)
            return {
                "id": token_id,
                "token_number": (t or {}).get("token_number"),
                "doctor_id": spec.doctor_id,
                "hospital_id": spec.hospital_id,
                "appointment_date": (t or {}).get("appointment_date"),
                "status": (t or {}).get("status") or TokenStatus.PENDING,
                "queue": q,
            }

    # Allocate sequentially in a transaction
    cap_ref = db.collection(COLLECTIONS["CAPACITY"]).document(_capacity_doc_id(spec.doctor_id, spec.hospital_id, day))
    def _txn(tx):
        snap = cap_ref.get(transaction=tx)
        data = snap.to_dict() if getattr(snap, "exists", False) else None
        cap_val = _get_today_capacity(doctor_data)
        if not data:
            data = {
                "doctor_id": spec.doctor_id,
                "hospital_id": spec.hospital_id,
                "date": str(day),
                "capacity": int(cap_val),
                "booked_count": 0,
                "last_token_number": 0,
                "tz_offset_minutes": tz_minutes,
                "now_serving_number": int((doctor_data or {}).get("now_serving_number") or 1),
                "per_patient_minutes": int((doctor_data or {}).get("per_patient_minutes") or 5),
                "updated_at": datetime.utcnow(),
            }
        booked = int(data.get("booked_count", 0))
        capi = int(data.get("capacity", cap_val))
        if booked >= capi:
            raise HTTPException(status_code=409, detail="Doctor's daily capacity reached for that date.")
        booked += 1
        last = int(data.get("last_token_number", 0)) + 1
        if not data.get("now_serving_number"):
            data["now_serving_number"] = 1
        if not data.get("per_patient_minutes"):
            data["per_patient_minutes"] = int((doctor_data or {}).get("per_patient_minutes") or 5)
        data.update({"booked_count": booked, "last_token_number": last, "updated_at": datetime.utcnow()})
        tx.set(cap_ref, data, merge=True)
        return last, data["now_serving_number"], data["per_patient_minutes"]

    try:
        from google.cloud import firestore
        transaction = db.transaction()
        token_number, now_serving, per_min = firestore.transactional(lambda tx: _txn(tx))(transaction)
    except HTTPException:
        raise
    except Exception:
        # Fallback best-effort
        snap = cap_ref.get()
        data = snap.to_dict() if getattr(snap, "exists", False) else {}
        if int(data.get("booked_count", 0)) >= int(data.get("capacity") or _get_today_capacity(doctor_data)):
            raise HTTPException(status_code=409, detail="Doctor's daily capacity reached for that date.")
        token_number = int(data.get("last_token_number", 0)) + 1
        data.update({
            "doctor_id": spec.doctor_id,
            "hospital_id": spec.hospital_id,
            "date": str(day),
            "capacity": int(data.get("capacity") or _get_today_capacity(doctor_data)),
            "booked_count": int(data.get("booked_count", 0)) + 1,
            "last_token_number": token_number,
            "tz_offset_minutes": tz_minutes,
            "now_serving_number": int(data.get("now_serving_number") or 1),
            "per_patient_minutes": int(data.get("per_patient_minutes") or (doctor_data.get("per_patient_minutes") if doctor_data else 5) or 5),
            "updated_at": datetime.utcnow(),
        })
        cap_ref.set(data, merge=True)
        now_serving = int(data.get("now_serving_number") or 1)
        per_min = int(data.get("per_patient_minutes") or 5)

    # Persist token document
    appt_dt_utc = _minute_for_token_number(
        doctor_data.get("start_time") or "09:00",
        doctor_data.get("end_time") or "17:00",
        token_number,
        tz_minutes,
        base_utc=datetime.utcnow().replace(tzinfo=timezone.utc)
    )
    tokens = db.collection(COLLECTIONS["TOKENS"]).document()
    token_id = tokens.id
    token_doc = {
        "id": token_id,
        "patient_id": current_user.user_id,
        "doctor_id": spec.doctor_id,
        "hospital_id": spec.hospital_id,
        "token_number": token_number,
        "hex_code": f"{token_id[:8]}{token_number:03d}",
        "appointment_date": appt_dt_utc,
        "status": TokenStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
        "doctor_name": (doctor_data or {}).get("name"),
        "hospital_name": (hospital_data or {}).get("name"),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    tokens.set(token_doc)

# ... (rest of the code remains the same)

# -------------------- Tokens Tab: Upcoming Tokens --------------------
@router.get("/my-upcoming")
async def get_my_upcoming_tokens(
    current_user = Depends(get_current_active_user),
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    response: Response = None,
):
    """Return tokens to show on the Tokens tab:

    - All future-day tokens
    - Today's tokens whose appointment time has not passed yet
    - Excludes cancelled/completed
    - Sorted by appointment time ascending
    """
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", current_user.user_id)
    docs = list(tokens_ref.stream())

    from datetime import datetime as _dt
    now = _dt.utcnow()
    today = now.date()

    def _to_dt(x):
        if isinstance(x, _dt):
            return x
        try:
            return _dt.fromisoformat(str(x).replace('Z', '+00:00'))
        except Exception:
            return None

    items = []
    for d in docs:
        t = d.to_dict() or {}
        status_val = str(t.get("status") or "").lower()
        if status_val in ("cancelled", "completed"):
            continue
        appt = _to_dt(t.get("appointment_date"))
        if appt is None:
            continue
        appt_date = appt.date()
        # Include if future day, or today and time not passed
        if appt_date > today or (appt_date == today and appt >= now):
            item = {
                "id": t.get("id", d.id),
                "token_number": t.get("token_number"),
                "display_code": t.get("display_code"),
                "formatted_time": appt.strftime("%I:%M %p"),
                "appointment_time": appt.isoformat(),
                "is_today": appt_date == today,
                "doctor": {
                    "id": t.get("doctor_id"),
                    "name": t.get("doctor_name"),
                    "specialization": t.get("doctor_specialization"),
                },
                "hospital": {
                    "id": t.get("hospital_id"),
                    "name": t.get("hospital_name"),
                },
                "status": t.get("status"),
            }
            items.append((appt, item))

    # Sort ascending by appointment time
    items.sort(key=lambda x: x[0])
    result_items = [it for _, it in items[:limit]]

    result = {"items": result_items, "total": len(result_items)}
    # Prevent caching so UI stays fresh
    try:
        if response is not None:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    except Exception:
        pass
    return result

# ... (rest of the code remains the same)

# -------------------- Real-time Notification Endpoints (Twilio-ready) --------------------
@router.post("/{token_id}/notify/summary")
async def notify_appointment_summary(
    token_id: str,
    phone_number: Optional[str] = None,
    channels: Optional[list[str]] = Query(None, description="Override channels e.g. ['sms','whatsapp']"),
    current_user = Depends(get_current_active_user)
):
    """Send appointment summary over SMS/WhatsApp using Twilio or configured provider.

    Includes token label, doctor, hospital, appointment time, queue position and estimated wait.
    """
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = token_ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Token not found")
    token = snap.to_dict()
    if token.get("patient_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Doctor/Hospital for context
    doctor = db.collection(COLLECTIONS["DOCTORS"]).document(token["doctor_id"]).get().to_dict() or {}
    hospital = db.collection(COLLECTIONS["HOSPITALS"]).document(token["hospital_id"]).get().to_dict() or {}

    # Queue status
    queue = SmartTokenService.get_queue_status(
        doctor_id=token["doctor_id"],
        token_number=token.get("token_number"),
        appointment_date=token.get("appointment_date")
    ) or {}
    people_ahead = int(queue.get("people_ahead") or 0)
    est_wait = int(queue.get("estimated_wait_time") or 0)

    # Appointment time
    appt = token.get("appointment_date")
    try:
        appt_str = appt.strftime("%I:%M %p") if hasattr(appt, 'strftime') else ""
    except Exception:
        appt_str = ""

    # Visible token label: prefer daily token_number
    token_label = None
    try:
        _n = int(token.get("token_number") or 0)
        if _n > 0:
            token_label = SmartTokenService.format_token(_n)
    except Exception:
        token_label = None
    if not token_label:
        token_label = token.get("display_code") or str(token.get("token_number") or "") or (token.get("id") or "")[-8:].upper()

    # Determine channels from preferences if not overridden
    notif_types = []
    if channels:
        cset = {c.strip().lower() for c in channels if isinstance(c, str)}
        if 'sms' in cset:
            notif_types.append(NotificationType.SMS)
        if 'whatsapp' in cset:
            notif_types.append(NotificationType.WHATSAPP)
    else:
        prefs_ref = db.collection("notification_preferences")
        docs = list(prefs_ref.where("user_id", "==", current_user.user_id).limit(1).stream())
        prefs = docs[0].to_dict() if docs else {}
        settings = prefs.get("settings") or {}
        if settings.get("queue_updates", True) or True:
            if prefs.get("sms_enabled", True):
                notif_types.append(NotificationType.SMS)
            if prefs.get("whatsapp_enabled", True):
                notif_types.append(NotificationType.WHATSAPP)

    # Resolve phone number preference -> fallback to user's phone in USERS
    if not phone_number:
        pn = (prefs.get("phone_number") if 'prefs' in locals() else None) or None
        if not pn:
            user_doc = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id).get()
            u = user_doc.to_dict() if getattr(user_doc, 'exists', False) else {}
            pn = u.get("phone") or u.get("mobile")
        phone_number = pn
    if not phone_number:
        raise HTTPException(status_code=400, detail="No phone number available to send SMS")

    # Build address string
    address = hospital.get("address") or None
    
    # Determine if this is a same-day token
    from datetime import datetime, timezone
    is_same_day = False
    try:
        if hasattr(appt, 'date'):  # Already a date/datetime object
            appt_date = appt.date() if hasattr(appt, 'date') else None
        else:  # Try to parse string
            appt_date = datetime.strptime(str(appt), "%Y-%m-%d %H:%M:%S").date()
        
        today = datetime.now(timezone.utc).date()
        is_same_day = appt_date == today
    except (ValueError, AttributeError):
        # If we can't determine the date, assume it's not same-day
        is_same_day = False

    result = await NotificationService.send_appointment_summary(
        token_label=token_label,
        phone_number=phone_number,
        doctor_name=token.get("doctor_name") or doctor.get("name") or "Doctor",
        hospital_name=token.get("hospital_name") or hospital.get("name") or "Hospital",
        appointment_time=appt_str,
        people_ahead=people_ahead if is_same_day else None,
        estimated_wait_time=est_wait if is_same_day else None,
        notification_types=notif_types,
        address=address,
    )

    await create_activity_log(
        current_user.user_id,
        ActivityType.NOTIFICATION_SENT,
        f"Appointment summary sent for SmartToken #{token.get('token_number')}",
        {"token_id": token_id, "channels": [t.name for t in notif_types], "phone_number": phone_number}
    )

    return {"message": "Notification sent", "details": result}

# ... (rest of the code remains the same)
@router.post("/{token_id}/notifications")
async def send_notifications(
    token_id: str,
    notification: NotificationRequest,
    current_user = Depends(get_current_active_user)
):
    """Send notifications for a token (WhatsApp/SMS)"""
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Verify token belongs to current user
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Store notification record
    notifications_ref = db.collection("notifications")
    notification_ref = notifications_ref.document()
    
    notification_data = {
        "id": notification_ref.id,
        "token_id": token_id,
        "user_id": token_data.get("patient_id"),
        "phone_number": notification.phone_number,
        "message": notification.message,
        "notification_types": [nt.value for nt in notification.notification_types],
        "sent_at": datetime.utcnow(),
        "status": "sent",
        "is_read": False,
        "read_at": None,
    }
    
    notification_ref.set(notification_data)
    
    # Create activity log
    await create_activity_log(
        token_data.get("patient_id"),
        ActivityType.NOTIFICATION_SENT,
        f"Notifications sent for SmartToken #{token_data.get('token_number')}",
        {
            "token_id": token_id,
            "notification_types": notification_data["notification_types"],
            "phone_number": notification.phone_number
        }
    )
    
    return {
        "message": "Notifications sent successfully",
        "notification_id": notification_ref.id,
        "types_sent": notification_data["notification_types"]
    }

@router.get("/{token_id}/appointment-details")
async def get_appointment_details(
    token_id: str,
    current_user = Depends(get_current_active_user)
):
    """Get complete appointment details for a token"""
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Check if user owns this token
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Get doctor details
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(token_data["doctor_id"])
    doctor_data = doctor_ref.get().to_dict()
    
    # Get hospital details
    hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(token_data["hospital_id"])
    hospital_data = hospital_ref.get().to_dict()
    
    # Get queue status with appointment date to handle future appointments
    queue_status = SmartTokenService.get_queue_status(
        doctor_id=token_data["doctor_id"],
        token_number=token_data.get("token_number"),
        appointment_date=token_data.get("appointment_date")
    )

    # Ensure estimated_wait_time is present; derive a basic estimate if missing
    people_ahead = queue_status.get("people_ahead", 0)
    est_wait = queue_status.get("estimated_wait_time", 0)
    is_future = queue_status.get("is_future_appointment", False)
    
    # For future appointments, we don't calculate wait time
    if is_future:
        est_wait = 0
        people_ahead = 0
    elif est_wait is None or est_wait == 0:
        # Fallback: Assume ~9 minutes per patient as a simple heuristic
        est_wait = max(0, int(people_ahead) * 9)
        queue_status["estimated_wait_time"] = est_wait

    # Compute a friendly appointment_time string; hide for same-day
    appt_dt = token_data.get("appointment_date")
    try:
        if hasattr(appt_dt, 'strftime'):
            from datetime import datetime as _dt, timedelta
            if appt_dt.date() == _dt.utcnow().date():
                appointment_time_str = ""
            else:
                appointment_time_str = appt_dt.strftime("%I:%M %p")
        else:
            # Fallback: now + est_wait minutes (best effort) only for non-same-day
            from datetime import datetime as _dt, timedelta
            appointment_time_str = ( _dt.utcnow() + timedelta(minutes=int(est_wait)) ).strftime("%I:%M %p")
    except Exception:
        appointment_time_str = ""

    # Build resilient doctor/hospital objects with safe fallbacks for UI
    safe_doctor = {
        "id": token_data.get("doctor_id"),
        "name": token_data.get("doctor_name") or (doctor_data or {}).get("name") or "Dr. Doctor",
        "specialization": token_data.get("doctor_specialization") or (doctor_data or {}).get("specialization") or "General",
        "consultation_fee": (doctor_data or {}).get("consultation_fee", 3500),
        "avatar_initials": token_data.get("doctor_avatar_initials") or (doctor_data or {}).get("avatar_initials") or ((doctor_data or {}).get("name", "DR")[:3].upper())
    }

    safe_hospital = {
        "id": token_data.get("hospital_id"),
        "name": token_data.get("hospital_name") or (hospital_data or {}).get("name") or "Hospital",
        "address": (hospital_data or {}).get("address") or "",
        "phone": (hospital_data or {}).get("phone") or ""
    }

    # include is_active for appointment details token
    token_data["is_active"] = token_data.get("status") not in ["cancelled", "completed"]

    # Ensure a visible_token field for UI display (prefer per-day token_number)
    try:
        _num = int(token_data.get("token_number") or 0)
        _visible = f"T-{_num:06d}" if _num > 0 else None
    except Exception:
        _visible = None
    if not _visible:
        _code = (str(token_data.get("display_code") or "").strip())
        if _code:
            _visible = _code
        else:
            _hex = (str(token_data.get("hex_code") or "").strip())
            if _hex:
                _visible = _hex.upper()[:8]
            else:
                _tid = (str(token_data.get("id") or token_id or "").strip())
                _visible = _tid[-8:].upper() if _tid else "—"
    token_data["visible_token"] = token_data.get("visible_token") or _visible

    # Make sure queue payload carries a 1-based queue_position
    try:
        pa = int(queue_status.get("people_ahead") or 0)
    except Exception:
        pa = 0
    queue_status["queue_position"] = int(pa) + 1 if not queue_status.get("is_future_appointment") else 0
    return {
        "token": SmartTokenResponse(**token_data),
        "token_visible_token": token_data.get("visible_token"),
        "doctor": safe_doctor,
        "hospital": safe_hospital,
        "queue": queue_status,
        "queue_position": queue_status.get("queue_position"),
        "appointment_date": token_data.get("appointment_date"),
        "appointment_time": appointment_time_str
    }