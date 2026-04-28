from fastapi import APIRouter, HTTPException, status, Depends, Query, Response, Body, Request
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
import logging
import uuid
import random
import os
import asyncio
from datetime import datetime, timedelta, timezone, time

from app.models import (
    SmartTokenCreate, SmartTokenResponse, PaymentCreate, PaymentResponse, 
    ActivityType, TokenCancellationRequest, QueueResponse, NotificationRequest,
    TokenStatus, NotificationType, CancellationResponse, RefundCalculation,
    CancellationReason, RefundMethod, RefundStatus, SmartTokenGenerateRequest,
    PaymentStatus, QueueTokenStatusUpdate, TokenCreateSpec
)
from app.database import get_db
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue
from app.config import TOKEN_FEE
from app.security import get_current_active_user
from app.security import require_roles
from app.services.token_service import SmartTokenService
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.services.refund_service import RefundService
from app.services.message_scheduler import schedule_messages
from app.services.confirmation_scheduler import schedule_confirmation_checks
from app.utils.mrn import get_or_create_patient_mrn
from app.utils.state import is_transition_allowed
from app.utils.responses import ok
from app.services.fee_calculator import compute_total_amount

# Use avg_last_10 to match AI model expectations
from app.routes.ai import (
    get_current_hour, get_current_day, calculate_patients_ahead,
    calculate_queue_length, calculate_queue_velocity, get_last_patient_duration,
    avg_last_5, avg_last_10, count_available_doctors, get_hour_history,
    get_weekday_history, get_doctor_history
)
from app.services.ai_engine import ai_engine
from app.services.whatsapp_service import send_queue_message

router = APIRouter(tags=["SmartTokens"])
logger = logging.getLogger(__name__)

# -------------------- Helpers --------------------

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
    return 300


def _utc_bounds_for_local_day(local_day: datetime.date, tz_minutes: int):
    """Calculates the absolute UTC start and end boundaries for a given local day."""
    local_start = datetime.combine(local_day, time.min)
    local_end = datetime.combine(local_day, time.max)
    tz = timezone(timedelta(minutes=tz_minutes))
    
    local_start_aware = local_start.replace(tzinfo=tz)
    local_end_aware = local_end.replace(tzinfo=tz)
    
    utc_start = local_start_aware.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end_aware.astimezone(timezone.utc).replace(tzinfo=None)
    
    return utc_start, utc_end


def _to_smart_token_response(t: Token) -> SmartTokenResponse:
    status_val = str(t.status.value if hasattr(t.status, 'value') else t.status).lower()
    pay_status_val = str(t.payment_status.value if hasattr(t.payment_status, 'value') else t.payment_status).lower()
    is_active = status_val not in ["cancelled", "completed", "skipped"]

    return SmartTokenResponse(
        id=str(t.id),
        patient_id=str(t.patient_id),
        doctor_id=str(t.doctor_id),
        hospital_id=str(t.hospital_id),
        mrn=t.mrn,
        token_number=t.token_number,
        hex_code=t.hex_code,
        display_code=t.display_code,
        appointment_date=t.appointment_date,
        status=status_val,
        payment_status=pay_status_val,
        payment_method=t.payment_method,
        queue_position=t.queue_position,
        total_queue=t.total_queue,
        estimated_wait_time=t.estimated_wait_time,
        consultation_fee=t.consultation_fee,
        session_fee=t.session_fee,
        total_fee=t.total_fee,
        department=t.department,
        created_at=t.created_at,
        updated_at=t.updated_at,
        is_active=is_active,
        doctor_name=t.doctor_name,
        doctor_specialization=t.doctor_specialization,
        doctor_avatar_initials=t.doctor_avatar_initials,
        hospital_name=t.hospital_name,
        patient_name=t.patient_name,
        patient_phone=t.patient_phone,
        patient_age=t.patient_age,
        patient_gender=t.patient_gender,
        reason_for_visit=t.reason_for_visit,
        patient={
            "name": t.patient_name,
            "phone": t.patient_phone,
            "age": t.patient_age,
            "gender": t.patient_gender,
        },
        queue_opt_in=bool(t.queue_opt_in),
        queue_opted_in_at=t.queue_opted_in_at,
        confirmed=bool(t.confirmed),
        confirmation_status=t.confirmation_status,
        confirmed_at=t.confirmed_at,
        cancelled_at=t.cancelled_at,
    )


def _local_day_for(dt_utc: datetime, tz_minutes: int) -> datetime.date:
    try:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        tz = timezone(timedelta(minutes=tz_minutes))
        return dt_utc.astimezone(tz).date()
    except Exception:
        return dt_utc.date()


def _to_local_clock(dt_utc: datetime, tz_minutes: int = 300) -> datetime:
    try:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        tz = timezone(timedelta(minutes=tz_minutes))
        return dt_utc.astimezone(tz)
    except Exception:
        return dt_utc


def _parse_local_date(date_str: str, tz_minutes: int) -> datetime.date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return _local_day_for(datetime.utcnow(), tz_minutes)


def _minute_for_token_number(start_hhmm: str, end_hhmm: str, token_no: int, tz_minutes: int, base_utc: datetime) -> datetime:
    try:
        h, m = map(int, start_hhmm.split(":"))
        tz = timezone(timedelta(minutes=tz_minutes))
        local_start = base_utc.astimezone(tz).replace(hour=h, minute=m, second=0, microsecond=0)
        offset_minutes = (token_no - 1) * 9
        appt_local = local_start + timedelta(minutes=offset_minutes)
        return appt_local.astimezone(timezone.utc)
    except Exception:
        return base_utc


def _allocate_queue_token_number(db: Session, hospital_id: str, doctor_id: str, day: datetime.date, tz_minutes: int = 300) -> int:
    utc_start, utc_end = _utc_bounds_for_local_day(day, tz_minutes)
    
    last = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.doctor_id == doctor_id,
        Token.appointment_date >= utc_start,
        Token.appointment_date <= utc_end
    ).order_by(Token.token_number.desc()).first()
    
    return (last.token_number + 1) if last else 1


def _queue_object_for(db: Session, doctor_id: str, hospital_id: str, day_local: datetime.date, my_token_no: Optional[int] = None) -> dict:
    q = db.query(DBQueue).filter(DBQueue.doctor_id == doctor_id).first()
    now_serving = int(getattr(q, "current_token", 1) or 1)
    total_queue = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == day_local,
        Token.status.notin_(["cancelled", "completed"])
    ).count()
    people_ahead = max(0, my_token_no - now_serving) if my_token_no else 0
    per_min = 9
    return {
        "current_token": now_serving,
        "total_queue": total_queue,
        "people_ahead": people_ahead,
        "estimated_wait_time": people_ahead * per_min,
        "is_future": day_local > datetime.utcnow().date()
    }


async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None, db: Session = None):
    if db is None:
        return
    try:
        log = ActivityLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            activity_type=activity_type.value if hasattr(activity_type, 'value') else str(activity_type),
            description=description,
            metadata=metadata or {},
            created_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to create activity log: {e}")


def _allocate_same_day_slot(db: Session, doctor_id: str, hospital_id: str, now_local: datetime, doctor_data: dict) -> datetime:
    return datetime.utcnow() + timedelta(minutes=5)


def _coerce_status(s: str) -> str:
    s = str(s or "").lower().strip()
    if s == "inprogress":
        return "in_progress"
    return s


# -------------------- Core Logic --------------------

async def cancel_token_logic(
    token_id: str,
    cancellation: TokenCancellationRequest,
    db: Session,
    current_user: Any
):
    logger.info(f"Attempting to cancel token {token_id} for user {current_user.user_id}")
    
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        logger.error(f"Token {token_id} not found")
        raise HTTPException(status_code=404, detail="Token not found")
    if token.patient_id != current_user.user_id:
        logger.error(f"Access denied: Token {token_id} does not belong to user {current_user.user_id}")
        raise HTTPException(status_code=403, detail="Access denied")

    status_val = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()
    if status_val in ["cancelled", "completed"]:
        logger.error(f"Token {token_id} is already {status_val}")
        raise HTTPException(status_code=400, detail=f"Token is already {status_val}")

    try:
        reason_enum = cancellation.reason if isinstance(cancellation.reason, CancellationReason) else CancellationReason(str(cancellation.reason or "other").lower())
    except Exception:
        reason_enum = CancellationReason.OTHER

    refund_calc = RefundService.calculate_refund(TOKEN_FEE, reason_enum)
    refund_id = RefundService.create_refund_record(
        token_id=token_id,
        user_id=token.patient_id,
        refund_calculation=refund_calc,
        refund_method=cancellation.refund_method or RefundMethod.SMARTTOKEN_WALLET,
        cancellation_reason=reason_enum,
    )

    token.status = TokenStatus.CANCELLED
    token.cancelled_at = datetime.utcnow()
    token.updated_at = datetime.utcnow()
    db.commit()
    
    logger.info(f"Token {token_id} cancelled successfully with refund {refund_id}")

    try:
        from app.services.app_scheduler import get_scheduler
        sch = get_scheduler()
        if sch:
            for job_id in [f"confirm_reminder:{token_id}", f"confirm_final:{token_id}"]:
                try:
                    sch.remove_job(job_id)
                    logger.info(f"Cancelled scheduled job {job_id} after token cancellation")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Failed to cancel reminder jobs for token {token_id}: {e}")

    await create_activity_log(
        current_user.user_id,
        ActivityType.TOKEN_CANCELLED,
        f"Cancelled SmartToken #{token.token_number}",
        {"token_id": token_id, "refund_id": refund_id, "reason": reason_enum.value},
        db=db
    )

    if token.patient_phone:
        try:
            from app.services.whatsapp_service import send_template_message
            await send_template_message(
                phone=token.patient_phone,
                template_name="cancelled",
                params=[token.patient_name or "Patient"]
            )
            logger.info(f"WhatsApp cancellation message sent to {token.patient_phone} for token {token_id}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp cancellation message for token {token_id}: {e}")

    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
    tz_minutes = _tz_offset_for(doctor_data)
    day_local = _local_day_for(token.appointment_date, tz_minutes)

    q = _queue_object_for(db, token.doctor_id, token.hospital_id, day_local)

    return {
        "message": "Token cancelled successfully",
        "token_id": token_id,
        "cancellation_reason": reason_enum,
        "refund_info": {
            "original_amount": refund_calc["original_amount"],
            "processing_fee_percentage": refund_calc["processing_fee_percentage"],
            "processing_fee_amount": refund_calc["processing_fee_amount"],
            "refund_amount": refund_calc["refund_amount"],
            "refund_method": cancellation.refund_method,
            "processing_time_days": refund_calc["processing_time"]
        },
        "refund_id": refund_id,
        "queue": q
    }


# ====================================================================================
# ROUTES — STATIC ROUTES FIRST, DYNAMIC /{token_id} ROUTES LAST
# ====================================================================================

@router.get("/generate/form-data")
async def generate_token_form_data(
    hospital_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    if not hospital_id:
        hs = db.query(Hospital).all()
        return {"success": True, "data": {"hospitals": [{"id": h.id, "name": h.name} for h in hs]}}

    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()
    if department:
        doctors = [d for d in doctors if (d.specialization or "").lower() == department.lower()]

    return {
        "success": True,
        "data": {
            "doctors": [{"id": d.id, "name": d.name, "specialization": d.specialization} for d in doctors]
        }
    }


@router.get("/my-active-details")
async def get_my_active_token_details(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.notin_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"])
    ).order_by(Token.created_at.desc()).first()

    if not token:
        raise HTTPException(status_code=404, detail="No active token found")

    if not token.patient_name or not token.patient_phone:
        user = db.query(User).filter(User.id == current_user.user_id).first()
        if user:
            if not token.patient_name:
                token.patient_name = user.name
            if not token.patient_phone:
                token.patient_phone = user.phone
            try:
                db.commit()
            except Exception:
                db.rollback()

    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == token.hospital_id).first()

    queue = SmartTokenService.get_queue_status(token.doctor_id, token.token_number, token.appointment_date)

    return {
        "token": _to_smart_token_response(token),
        "doctor": {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {},
        "hospital": {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {},
        "queue": queue
    }


@router.get("/my-active", response_model=SmartTokenResponse)
async def get_my_active_token(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.notin_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"])
    ).order_by(Token.created_at.desc()).first()

    if not token:
        raise HTTPException(status_code=404, detail="No active token found")

    if not token.patient_name or not token.patient_phone:
        user = db.query(User).filter(User.id == current_user.user_id).first()
        if user:
            if not token.patient_name:
                token.patient_name = user.name
            if not token.patient_phone:
                token.patient_phone = user.phone
            try:
                db.commit()
            except Exception:
                db.rollback()

    return _to_smart_token_response(token)


@router.get("/my-tokens", response_model=List[SmartTokenResponse])
async def get_my_tokens(
    only_active: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    query = db.query(Token).filter(Token.patient_id == current_user.user_id)
    if only_active:
        query = query.filter(Token.status.notin_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"]))
    tokens = query.order_by(Token.created_at.desc()).all()
    return [_to_smart_token_response(t) for t in tokens]


@router.get("/my-upcoming")
async def get_my_upcoming_tokens(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    limit: int = Query(50, ge=1, le=200),
):
    now = datetime.utcnow()
    tokens = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.notin_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"]),
        Token.appointment_date >= now
    ).order_by(Token.appointment_date.asc()).limit(limit).all()

    items = []
    for t in tokens:
        items.append({
            "id": t.id,
            "token_number": t.token_number,
            "appointment_date": t.appointment_date,
            "doctor_name": t.doctor_name,
            "hospital_name": t.hospital_name,
            "status": t.status
        })
    return {"items": items, "total": len(items)}


@router.get("/history", response_model=List[SmartTokenResponse])
async def get_token_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    tokens = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.in_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"])
    ).order_by(Token.created_at.desc()).all()
    return [_to_smart_token_response(t) for t in tokens]


@router.get("/hospital/{hospital_id}")
async def get_hospital_tokens(
    hospital_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    tokens = db.query(Token).filter(Token.hospital_id == hospital_id).all()
    return [{k: v for k, v in t.__dict__.items() if not k.startswith('_')} for t in tokens]


@router.post("/generate/details")
async def generate_smart_token_with_details(
    payload: SmartTokenGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
):
    token_resp: SmartTokenResponse = await generate_smart_token(
        payload=payload,
        db=db,
        current_user=current_user,
        fingerprint_name=fingerprint_name,
        fingerprint_phone=fingerprint_phone,
    )

    doctor = db.query(Doctor).filter(Doctor.id == token_resp.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == token_resp.hospital_id).first()
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
    hospital_data = {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {}

    queue_status = SmartTokenService.get_queue_status(
        token_resp.doctor_id,
        token_resp.token_number,
        appointment_date=token_resp.appointment_date,
    )

    return {
        "token": token_resp,
        "doctor": doctor_data,
        "hospital": hospital_data,
        "queue": queue_status,
        "appointment_date": token_resp.appointment_date
    }


# ====================================================================================
# ✅ THE CORE AI GENERATION ENDPOINT
# ====================================================================================
@router.post("/generate", response_model=SmartTokenResponse)
async def generate_smart_token(
    payload: SmartTokenGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
    include_consultation_fee: Optional[bool] = None,
    include_session_fee: Optional[bool] = None,
):
    doctor_id = payload.doctor_id
    hospital_id = payload.hospital_id
    appointment_date = payload.appointment_date

    # --- RACE CONDITION FIX: Prevent double-booking ---
    existing_token = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.doctor_id == doctor_id,
        Token.status.notin_(["cancelled", "completed", "TokenStatus.CANCELLED", "TokenStatus.COMPLETED"])
    ).first()
    
    if existing_token:
        return _to_smart_token_response(existing_token)

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not doctor or not hospital:
        raise HTTPException(status_code=400, detail="Doctor or Hospital not found")

    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    hospital_data = {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')}

    tz_minutes = _tz_offset_for(doctor_data, hospital_data)
    now_local = _to_local_clock(datetime.utcnow(), tz_minutes)

    if appointment_date is None:
        appointment_date = _allocate_same_day_slot(db, doctor_id, hospital_id, now_local, doctor_data)

    day_local = _local_day_for(appointment_date, tz_minutes)
    token_number = _allocate_queue_token_number(db, hospital_id, doctor_id, day_local, tz_minutes)

    token_id = str(uuid.uuid4())
    pricing = compute_total_amount(
        consultation_fee=doctor_data.get("consultation_fee"),
        session_fee=doctor_data.get("session_fee"),
        include_consultation_fee=include_consultation_fee,
        include_session_fee=include_session_fee,
    )

    mrn = get_or_create_patient_mrn(db, current_user.user_id, hospital_id)

    # ---------------------------------------------------------
    # AI Estimated Wait Time Calculation
    # ---------------------------------------------------------
    estimated_wait_time = 0
    utc_start, utc_end = _utc_bounds_for_local_day(day_local, tz_minutes)

    try:
        # Replaced func.date() with absolute UTC boundary matching
        patients_ahead = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(["waiting", "confirmed", "pending", "called", "in_consultation", "TokenStatus.PENDING", "TokenStatus.WAITING", "TokenStatus.CONFIRMED"]),
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        completed_today = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(["completed", "TokenStatus.COMPLETED"]),
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        # PHASE 1: Fast-Start Override
        if completed_today == 0:
            estimated_wait_time = (patients_ahead + 1) * 5

        # PHASE 2: Live XGBoost Engine
        else:
            if patients_ahead == 0:
                estimated_wait_time = 0 
            else:
                if not ai_engine.model:
                    ai_engine.load()

                last_5 = avg_last_5(doctor_id, db) or 5.0
                last_10 = avg_last_10(doctor_id, db) or 5.0 
                last_1 = get_last_patient_duration(doctor_id, db) or 5.0

                ai_input: Dict[str, Any] = {
                    "hour_of_day": get_current_hour(),
                    "day_of_week": get_current_day(),
                    "patients_ahead_of_user": patients_ahead,
                    "patients_in_queue": patients_ahead + 1,
                    "queue_length_last_10_min": 0, 
                    "queue_velocity": calculate_queue_velocity(doctor_id, db),
                    "last_patient_duration": last_1,
                    "avg_service_time_last_5": last_5,
                    "avg_service_time_last_10": last_10,
                    "doctors_available": count_available_doctors(db),
                    "doctor_type": "Specialist" if doctor_data.get("has_session") else "General Medicine",
                    "clinic_type": "Specialist" if doctor_data.get("has_session") else "General Medicine",
                    "avg_wait_time_this_hour_past_week": get_hour_history(db),
                    "avg_wait_time_this_weekday_past_month": get_weekday_history(db),
                    "avg_service_time_doctor_historic": get_doctor_history(doctor_id, db),
                    "Name": current_user.name if hasattr(current_user, 'name') else "Unknown",
                    "Doctor Name": doctor_data.get("name", "Unknown"),
                    "Service_Duration": 0, 
                    "Disease": payload.reason_for_visit or payload.department or "General",
                    "Age": payload.patient_age or 30
                }

                predicted_duration = ai_engine.predict_duration(ai_input)
                predicted_duration = max(predicted_duration, 3.5) 

                rolling_service_time = (0.5 * last_5) + (0.3 * last_10) + (0.2 * last_1)
                ai_eta = patients_ahead * predicted_duration

                if completed_today >= 30:
                    alpha = 0.7   
                elif completed_today >= 10:
                    alpha = 0.5   
                else:
                    alpha = 0.2   

                eta = alpha * ai_eta + (1 - alpha) * (patients_ahead * rolling_service_time)
                estimated_wait_time = max(int(eta), 5) 

    except Exception as e:
        logger.error(f"AI Wait Time Calculation failed: {e}", exc_info=True)
        last_5 = avg_last_5(doctor_id, db) or 5.0
        estimated_wait_time = int(max(patients_ahead, 1) * last_5)

    # ---------------------------------------------------------
    # Token Creation & Saving (UPDATED WITH ENUM VALUES)
    # ---------------------------------------------------------
    user = db.query(User).filter(User.id == current_user.user_id).first()
    patient_name = user.name if user else None
    patient_phone = user.phone if user else None
    
    # Safely extract actual string values to prevent database matching errors
    status_val = TokenStatus.PENDING.value if hasattr(TokenStatus.PENDING, 'value') else "pending"
    payment_val = PaymentStatus.PENDING.value if hasattr(PaymentStatus.PENDING, 'value') else "pending"
    
    token_doc = {
        "id": token_id,
        "token_number": token_number,
        "patient_id": current_user.user_id,
        "doctor_id": doctor_id,
        "hospital_id": hospital_id,
        "mrn": mrn,
        "hex_code": f"{token_id[:7]}{token_number:03d}",
        "display_code": f"{doctor_data.get('hex_code', 'A')}-{token_number:03d}",
        "appointment_date": appointment_date,
        "status": status_val,
        "payment_status": payment_val,
        "doctor_name": doctor_data.get("name"),
        "doctor_specialization": doctor_data.get("specialization"),
        "doctor_avatar_initials": doctor_data.get("avatar_initials"),
        "hospital_name": hospital_data.get("name"),
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "department": doctor_data.get("specialization"),
        "patient_age": payload.patient_age,
        "patient_gender": payload.patient_gender,
        "reason_for_visit": payload.reason_for_visit or None,
        "consultation_fee": pricing.get("consultation_fee"),
        "session_fee": pricing.get("session_fee"),
        "total_fee": pricing.get("total_amount"),
        "estimated_wait_time": estimated_wait_time,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    valid_fields = {c.name for c in Token.__table__.columns}
    filtered_token_doc = {k: v for k, v in token_doc.items() if k in valid_fields}

    new_token = Token(**filtered_token_doc)
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    out_dict = {k: v for k, v in new_token.__dict__.items() if not k.startswith('_')}
    out_dict["estimated_wait_time"] = estimated_wait_time

    response_obj = SmartTokenResponse(**out_dict)

    await create_activity_log(
        current_user.user_id,
        ActivityType.TOKEN_GENERATED,
        f"Generated Token #{token_number}",
        {"token_id": token_id},
        db=db
    )

    if patient_phone:
        try:
            await send_template_message(
            phone=patient_phone,
            template_name="token_number",
            params=[
                doctor_data.get("name", "Doctor"),
                patient_name or "Patient",
                hospital_data.get("name", "Clinic"),
                doctor_data.get("specialization", "General"), 
                str(estimated_wait_time or 0)
            ]
            )
            logger.info(f"WhatsApp confirmation sent to {patient_phone} for token {token_id}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp confirmation for token {token_id}: {e}")
    
        try:
                schedule_confirmation_checks(
                    token_id=token_id,
                    first_delay_minutes=15,
                    second_delay_minutes=15
                )
                logger.info(f"Confirmation reminder scheduled for token {token_id}")
        except Exception as e:
                logger.error(f"Failed to schedule confirmation reminder for token {token_id}: {e}")

    return response_obj


@router.post("/generate/selection")
async def generate_token_by_selection(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    doctor_id = payload.get("doctor_id")
    hospital_id = payload.get("hospital_id")
    if not doctor_id or not hospital_id:
        raise HTTPException(status_code=400, detail="doctor_id and hospital_id are required")

    return await generate_smart_token_with_details(
        payload=SmartTokenGenerateRequest(
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            patient_age=payload.get("patient_age"),
            patient_gender=payload.get("patient_gender"),
            reason_for_visit=payload.get("reason_for_visit"),
        ),
        db=db,
        current_user=current_user
    )


@router.post("/patients/token/generate")
async def generate_token_alias(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    return await generate_token_by_selection(payload, db, current_user)


@router.post("/cancel")
async def cancel_token_alias(
    payload: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token_id = payload.get("token_id")
    if not token_id:
        raise HTTPException(status_code=400, detail="token_id is required")
    
    result = await cancel_token_endpoint(token_id, payload, db, current_user)
    
    return {
        "success": True,
        "message": result.message if hasattr(result, 'message') else result.get("message", "Token cancelled successfully"),
        "token_id": result.token_id if hasattr(result, 'token_id') else result.get("token_id"),
        "refund_id": result.refund_id if hasattr(result, 'refund_id') else result.get("refund_id"),
        "data": result
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    spec: TokenCreateSpec,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    doctor = db.query(Doctor).filter(Doctor.id == spec.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == spec.hospital_id).first()
    if not doctor or not hospital:
        raise HTTPException(status_code=400, detail="Doctor or Hospital not found")

    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    tz_minutes = _tz_offset_for(doctor_data)
    day = _parse_local_date(spec.appointment_date, tz_minutes)

    token_number = _allocate_queue_token_number(db, spec.hospital_id, spec.doctor_id, day, tz_minutes)

    appt_dt_utc = _minute_for_token_number(
        doctor_data.get("start_time") or "09:00",
        doctor_data.get("end_time") or "17:00",
        token_number,
        tz_minutes,
        base_utc=datetime.utcnow().replace(tzinfo=timezone.utc)
    )

    token_id = str(uuid.uuid4())
    mrn = get_or_create_patient_mrn(db, current_user.user_id, spec.hospital_id)
    
    user = db.query(User).filter(User.id == current_user.user_id).first()
    patient_name = user.name if user else None
    patient_phone = user.phone if user else None

    status_val = TokenStatus.PENDING.value if hasattr(TokenStatus.PENDING, 'value') else "pending"
    payment_val = PaymentStatus.PENDING.value if hasattr(PaymentStatus.PENDING, 'value') else "pending"

    token_doc = {
        "id": token_id,
        "patient_id": current_user.user_id,
        "doctor_id": spec.doctor_id,
        "hospital_id": spec.hospital_id,
        "mrn": mrn,
        "token_number": token_number,
        "hex_code": f"{token_id[:7]}{token_number:03d}",
        "appointment_date": appt_dt_utc,
        "status": status_val,
        "payment_status": payment_val,
        "doctor_name": doctor_data.get("name"),
        "doctor_specialization": doctor_data.get("specialization"),
        "hospital_name": hospital.name,
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "department": doctor_data.get("specialization"),
        "patient_age": spec.patient_age,
        "patient_gender": spec.patient_gender,
        "reason_for_visit": spec.reason_for_visit or None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    valid_fields = {c.name for c in Token.__table__.columns}
    filtered_token_doc = {k: v for k, v in token_doc.items() if k in valid_fields}

    new_token = Token(**filtered_token_doc)
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    q = _queue_object_for(db, spec.doctor_id, spec.hospital_id, day, token_number)
    token_resp = _to_smart_token_response(new_token)

    return {
        **token_resp.model_dump(),
        "queue": q,
    }


# -------------------- Dynamic /{token_id} Routes LAST --------------------

@router.get("/{token_id}/appointment-details")
async def get_appointment_details(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    user_role = str(getattr(current_user, "role", "")).lower()
    is_owner = str(token.patient_id) == str(current_user.user_id)
    is_staff = user_role in ["doctor", "receptionist", "admin"]

    if not is_owner and not is_staff:
        raise HTTPException(status_code=403, detail="Access denied")

    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == token.hospital_id).first()

    queue = SmartTokenService.get_queue_status(
        token.doctor_id, 
        token.token_number, 
        token.appointment_date,
        db=db 
    )

    return {
        "token": _to_smart_token_response(token),
        "doctor": {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {},
        "hospital": {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {},
        "queue": queue
    }

@router.get("/{token_id}/queue-status")
async def get_token_queue_status(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    return SmartTokenService.get_queue_status(token.doctor_id, token.token_number, token.appointment_date, db=db)


@router.post("/{token_id}/cancel", response_model=CancellationResponse)
async def cancel_token_endpoint(
    token_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    req = TokenCancellationRequest(
        reason=payload.get("reason"),
        refund_method=payload.get("refund_method"),
    )
    result = await cancel_token_logic(token_id, req, db, current_user)
    return CancellationResponse(**result)


@router.delete("/{token_id}/cancel", response_model=CancellationResponse)
async def cancel_token_delete(
    token_id: str,
    payload: dict = Body({}),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return await cancel_token_endpoint(token_id, payload, db, current_user)


@router.post("/{token_id}/payment", response_model=PaymentResponse)
async def process_payment(
    token_id: str,
    payment: PaymentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    token.payment_status = PaymentStatus.PAID
    token.status = TokenStatus.CONFIRMED
    token.updated_at = datetime.utcnow()
    db.commit()

    await create_activity_log(
        current_user.user_id,
        ActivityType.PAYMENT_MADE,
        f"Paid for Token #{token.token_number}",
        {"token_id": token_id},
        db=db
    )

    return PaymentResponse(
        id=str(uuid.uuid4()),
        token_id=token_id,
        amount=payment.amount,
        status=PaymentStatus.PAID,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        method=payment.payment_method,
    )


@router.patch("/update-status/{token_id}")
async def update_token_status(
    token_id: str,
    payload: QueueTokenStatusUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    token.status = _coerce_status(payload.status)
    token.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.post("/{token_id}/notify/summary")
async def notify_appointment_summary(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"success": True, "message": "Summary sent"}


@router.post("/{token_id}/notifications")
async def send_token_notifications(
    token_id: str,
    request: NotificationRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return {"success": True, "message": "Notifications sent"}