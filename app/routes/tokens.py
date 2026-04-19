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
from datetime import datetime, timedelta, timezone

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
from app.services.refund_service import RefundService
from app.services.message_scheduler import schedule_messages
from app.services.confirmation_scheduler import schedule_confirmation_checks
from app.utils.mrn import get_or_create_patient_mrn
from app.utils.state import is_transition_allowed
from app.utils.responses import ok
from app.services.fee_calculator import compute_total_amount
from app.routes.ai import (
    get_current_hour, get_current_day, calculate_patients_ahead,
    calculate_queue_length, calculate_queue_velocity, get_last_patient_duration,
    avg_last_5, avg_last_30, count_available_doctors, get_hour_history,
    get_weekday_history, get_doctor_history
)
from app.services.ai_engine import ai_engine

router = APIRouter()
logger = logging.getLogger(__name__)

# -------------------- Queue/TZ Helpers --------------------

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

def _to_smart_token_response(t: Token) -> SmartTokenResponse:
    """Explicitly map Token model to SmartTokenResponse schema."""
    # Handle status/payment_status enum normalization
    status_val = str(t.status.value if hasattr(t.status, 'value') else t.status).lower()
    pay_status_val = str(t.payment_status.value if hasattr(t.payment_status, 'value') else t.payment_status).lower()
    
    # Calculate is_active flag
    is_active = status_val not in ["cancelled", "completed"]

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
        queue_opt_in=bool(t.queue_opt_in),
        queue_opted_in_at=t.queue_opted_in_at,
        confirmed=bool(t.confirmed),
        confirmation_status=t.confirmation_status,
        confirmed_at=t.confirmed_at,
        cancelled_at=t.cancelled_at
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

def _slot_hour_key(dt_utc: datetime, tz_minutes: int) -> str:
    local = _to_local_clock(dt_utc, tz_minutes)
    return local.strftime("%Y%m%d%H")

def _xor_key(s1: str, s2: str) -> str:
    import hashlib
    h1 = int(hashlib.md5(s1.encode()).hexdigest(), 16)
    h2 = int(hashlib.md5(s2.encode()).hexdigest(), 16)
    return hex(h1 ^ h2)[2:]

def _normalize_available_days(days: Optional[List[str]]) -> List[str]:
    if not days: return []
    return [str(d).lower() for d in days]

def _day_in_list(days: List[str], day: str) -> bool:
    return day.lower() in days

def _is_within_time_window(dt: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    try:
        h_s, m_s = map(int, start_hhmm.split(":"))
        h_e, m_e = map(int, end_hhmm.split(":"))
        m_start = h_s * 60 + m_s
        m_end = h_e * 60 + m_e
        m_now = dt.hour * 60 + dt.minute
        return m_start <= m_now <= m_end
    except Exception:
        return True

def _parse_hhmm_to_minutes(hhmm: str) -> Optional[int]:
    try:
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m
    except Exception:
        return None

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

def _recalculate_token_wait_times(db: Session, doctor_id: str, hospital_id: str, day_local: datetime.date):
    """
    Recalculates and updates wait times for all active tokens in a doctor's queue.
    This should be triggered whenever the queue state changes (e.g., patient called, finished, or cancelled).
    """
    try:
        # 1. Fetch doctor data for AI context
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        if not doctor:
            return
        doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
        
        # 2. Get all active tokens for this doctor today, ordered by token number
        active_tokens = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            func.date(Token.appointment_date) == day_local,
            Token.status.in_(["pending", "confirmed", "waiting", "called", "in_progress", "in_consultation"])
        ).order_by(Token.token_number.asc()).all()
        
        if not active_tokens:
            return

        # 3. Get currently serving patient (if any) to refine patients_ahead
        
        # 4. Prepare AI Engine
        if not ai_engine.model:
            ai_engine.load()
            
        # 5. Calculate common AI inputs (doctor history, etc.) once outside the loop
        doc_history = get_doctor_history(doctor_id, db)
        q_velocity = calculate_queue_velocity(doctor_id, db)
        last_duration = get_last_patient_duration(doctor_id, db)
        avg_5 = avg_last_5(doctor_id, db)
        avg_30 = avg_last_30(doctor_id, db)
        doctors_avail = count_available_doctors(db)
        hour_hist = get_hour_history(db)
        weekday_hist = get_weekday_history(db)
        
        # 6. Update each token: Use the Alpha-weighted ETA formula
        # ETA = α * AI_ETA + (1-α) * (patients_ahead * rolling_service_time)
        # alpha = 0.7 (trust factor for AI model)
        alpha = 0.7
        
        # Calculate rolling_service_time from recent averages
        # (avg last 5 + avg last 30 + last patient) / 3
        metrics = [m for m in [avg_5, avg_30, last_duration] if m > 0]
        rolling_service_time = sum(metrics) / len(metrics) if metrics else (doc_history if doc_history > 0 else 12.0)
        
        for i, token in enumerate(active_tokens):
            # patients_ahead for this specific token is its index
            patients_ahead = i 
            
            # If it's the very first person in the queue, wait time is 0
            if patients_ahead == 0:
                token.estimated_wait_time = 0
                token.updated_at = datetime.utcnow()
                continue

            # Predict individual consultation durations and sum them for cumulative AI_ETA
            # We calculate this specifically for each position
            user_age = 30
            if token.patient_id:
                patient_user = db.query(User).filter(User.id == token.patient_id).first()
                if patient_user and patient_user.date_of_birth:
                    try:
                        dob = datetime.strptime(patient_user.date_of_birth, "%Y-%m-%d")
                        user_age = (datetime.now() - dob).days // 365
                    except Exception: pass

            ai_input = {
                "hour_of_day": current_hour,
                "day_of_week": get_current_day(),
                "patients_ahead_of_user": patients_ahead,
                "patients_in_queue": q_len, 
                "queue_velocity": q_velocity,
                "last_patient_duration": last_duration,
                "avg_service_time_last_5": avg_5,
                "avg_service_time_last_30": avg_30,
                "doctors_available": doctors_avail,
                "avg_wait_time_this_hour_past_week": hour_hist,
                "avg_wait_time_this_weekday_past_month": weekday_hist,
                "avg_service_time_doctor_history": doc_history,
                "doctor": doctor_data.get("name", "Unknown"),
                "age": user_age, 
                "disease_type": getattr(token, "department", "General") or "General",
                "clinic_type": "Specialist" if doctor_data.get("has_session") else "General"
            }
            
            try:
                # --- TRACE LOGGING (STEP 3) ---
                print(f"➡️ Predicting AI_ETA for token index: {patients_ahead}")
                
                # Base AI prediction for this position
                ai_predicted_wait = ai_engine.predict_duration(ai_input)
                
                # Formula: α * AI_ETA + (1-α) * (patients_ahead * rolling_avg)
                historical_wait = patients_ahead * rolling_service_time
                final_eta = (alpha * ai_predicted_wait) + ((1 - alpha) * historical_wait)
                
                print(f"   AI_ETA: {ai_predicted_wait}, Historical_Wait: {historical_wait:.2f}, Final: {final_eta:.2f}")
                
                token.estimated_wait_time = int(round(final_eta))
            except Exception as e:
                # --- SILENT FALLBACK CHECK (STEP 4) ---
                print(f"❌ AI PREDICTION FAILED for index {patients_ahead}: {e}")
                # Fallback: Just use rolling_service_time * patients_ahead
                token.estimated_wait_time = int(round(patients_ahead * rolling_service_time))
            
            token.updated_at = datetime.utcnow()
            
        db.commit()
        print(f"[DEBUG] Recalculated dynamic wait times using Alpha-weighted ETA formula.")
        
    except Exception as e:
        print(f"[ERROR] Failed to recalculate wait times: {e}")
        db.rollback()

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None, db: Session = None):
    if db is None: return
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

def _count_doctor_bookings_for_date(db: Session, doctor_id: str, date_val: datetime.date) -> int:
    return db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == date_val,
        Token.status.notin_(["cancelled", "completed"])
    ).count()

def _allocate_same_day_slot(db: Session, doctor_id: str, hospital_id: str, now_local: datetime, doctor_data: dict) -> datetime:
    return datetime.utcnow() + timedelta(minutes=5)

def _coerce_status(s: str) -> str:
    s = str(s or "").lower().strip()
    if s == "inprogress": return "in_progress"
    return s

def _allocate_queue_token_number(db: Session, hospital_id: str, doctor_id: str, day: datetime.date) -> int:
    last = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == day
    ).order_by(Token.token_number.desc()).first()
    return (last.token_number + 1) if last else 1

# -------------------- Core Logic --------------------

async def cancel_token_logic(
    token_id: str,
    cancellation: TokenCancellationRequest,
    db: Session,
    current_user: Any
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    if token.patient_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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
    token.updated_at = datetime.utcnow()
    db.commit()

    # Send WhatsApp Cancelled Notification
    try:
        from app.services.whatsapp_service import send_template_message
        if token.patient_phone:
            # We use asyncio.create_task to not block the response
            import asyncio
            asyncio.create_task(send_template_message(
                token.patient_phone, 
                "cancelled", 
                [token.patient_name or "Patient"]
            ))
    except Exception as e:
        print(f"[ERROR] Failed to send cancel notification: {e}")

    # Problem 1 & 2 Fix: Recalculate wait times for everyone else after a cancellation
    try:
        doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
        doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
        tz_minutes = _tz_offset_for(doctor_data)
        day_local = _local_day_for(token.appointment_date, tz_minutes)
        _recalculate_token_wait_times(db, token.doctor_id, token.hospital_id, day_local)
    except Exception as e:
        print(f"[ERROR] Recalculation failed after cancel: {e}")

    await create_activity_log(
        current_user.user_id,
        ActivityType.TOKEN_CANCELLED,
        f"Cancelled SmartToken #{token.token_number}",
        {"token_id": token_id, "refund_id": refund_id},
        db=db
    )

    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
    tz_minutes = _tz_offset_for(doctor_data)
    day_local = _local_day_for(token.appointment_date, tz_minutes)
    
    q = _queue_object_for(db, token.doctor_id, token.hospital_id, day_local)
    
    return {
        "message": "Token cancelled successfully",
        "token_id": token_id,
        "refund_id": refund_id,
        "queue": q
    }

# -------------------- Endpoints --------------------

@router.post("/generate/details")
async def generate_smart_token_with_details(
    payload: SmartTokenGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    fingerprint_name: Optional[str] = None,
    fingerprint_phone: Optional[str] = None,
):
    token_resp: SmartTokenResponse = await generate_smart_token(
        doctor_id=payload.doctor_id,
        hospital_id=payload.hospital_id,
        appointment_date=payload.appointment_date,
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
    token_number = _allocate_queue_token_number(db, hospital_id, doctor_id, day_local)
    
    token_id = str(uuid.uuid4())
    pricing = compute_total_amount(
        consultation_fee=doctor_data.get("consultation_fee"),
        session_fee=doctor_data.get("session_fee"),
        include_consultation_fee=include_consultation_fee,
        include_session_fee=include_session_fee,
    )
    
    # Generate patient MRN if not exists
    mrn = get_or_create_patient_mrn(db, current_user.user_id, hospital_id)

    # --- AI Estimated Wait Time Calculation ---
    estimated_wait_time = 0
    target_date = appointment_date.date() if hasattr(appointment_date, 'date') else appointment_date
    
    try:
        # 1. Count ALL ACTIVE tokens for this doctor on the TARGET date

        total_tokens_today = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.notin_(["cancelled"]),
            func.date(Token.appointment_date) == target_date
        ).count()
        
        # 2. Count patients currently ahead (active in queue)
        patients_ahead = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(["pending", "waiting", "confirmed", "called", "in_consultation"]),
            func.date(Token.appointment_date) == target_date
        ).count()
        
        print(f"[DEBUG] AI Wait Time Calculation:")
        print(f"  - Doctor ID: {doctor_id}")
        print(f"  - Target Date: {target_date}")
        print(f"  - Total Tokens Today: {total_tokens_today}")
        print(f"  - Patients Ahead: {patients_ahead}")
        
        if total_tokens_today == 0:
            estimated_wait_time = 0
            print(f"  - Result: First token of the day, setting to 0")
        else:
            # Alpha-weighted ETA Formula: α * AI_ETA + (1-α) * (patients_ahead * rolling_avg)
            # alpha = 0.7 (trust factor for AI model)
            alpha = 0.7
            
            # Count patients currently ahead
            patients_ahead = db.query(Token).filter(
                Token.doctor_id == doctor_id,
                Token.status.in_(["pending", "waiting", "confirmed", "called", "in_consultation"]),
                func.date(Token.appointment_date) == target_date
            ).count()

            # Ensure AI engine is loaded
            if not ai_engine.model:
                ai_engine.load()
            
            # Common metrics for AI and historical average
            doc_history = get_doctor_history(doctor_id, db)
            q_velocity = calculate_queue_velocity(doctor_id, db)
            last_duration = get_last_patient_duration(doctor_id, db)
            avg_5 = avg_last_5(doctor_id, db)
            avg_30 = avg_last_30(doctor_id, db)
            doctors_avail = count_available_doctors(db)
            hour_hist = get_hour_history(db)
            weekday_hist = get_weekday_history(db)
            
            # Calculate rolling_service_time from recent averages
            metrics = [m for m in [avg_5, avg_30, last_duration] if m > 0]
            rolling_service_time = sum(metrics) / len(metrics) if metrics else (doc_history if doc_history > 0 else 12.0)

            # Calculate age for the current user
            user_age = 30
            if hasattr(current_user, 'date_of_birth') and current_user.date_of_birth:
                try:
                    dob = datetime.strptime(current_user.date_of_birth, "%Y-%m-%d")
                    user_age = (datetime.now() - dob).days // 365
                except Exception: pass

            ai_input = {
                "hour_of_day": get_current_hour(),
                "day_of_week": get_current_day(),
                "patients_ahead_of_user": patients_ahead,
                "patients_in_queue": patients_ahead + 1, 
                "queue_velocity": q_velocity,
                "last_patient_duration": last_duration,
                "avg_service_time_last_5": avg_5,
                "avg_service_time_last_30": avg_30,
                "doctors_available": doctors_avail,
                "avg_wait_time_this_hour_past_week": hour_hist,
                "avg_wait_time_this_weekday_past_month": weekday_hist,
                "avg_service_time_doctor_history": doc_history,
                "doctor": doctor_data.get("name", "Unknown"),
                "age": user_age, 
                "disease_type": payload.department or "General",
                "clinic_type": "Specialist" if doctor_data.get("has_session") else "General"
            }
            
            try:
                # --- TRACE LOGGING (STEP 3) ---
                print(f"➡️ Generating token: Calculating AI_ETA for index {patients_ahead}")
                
                ai_predicted_wait = ai_engine.predict_duration(ai_input)
                
                # Formula: α * AI_ETA + (1-α) * (patients_ahead * rolling_avg)
                historical_wait = patients_ahead * rolling_service_time
                final_eta = (alpha * ai_predicted_wait) + ((1 - alpha) * historical_wait)
                
                print(f"   AI_ETA: {ai_predicted_wait}, Historical_Wait: {historical_wait:.2f}, Final: {final_eta:.2f}")
                
                estimated_wait_time = int(round(final_eta))
            except Exception as e:
                # --- SILENT FALLBACK CHECK (STEP 4) ---
                print(f"AI PREDICTION FAILED for generating token: {e}")
                estimated_wait_time = int(round(patients_ahead * rolling_service_time))
            
            print(f"  - Result: AI Dynamic Wait Time (Alpha Formula) calculated as {estimated_wait_time}m")
            
    except Exception as e:
        print(f"[ERROR] AI Wait Time Calculation failed: {e}")
        # Problem 3 Fix: Better fallback using doctor history
        calc_ahead_fallback = max(patients_ahead if 'patients_ahead' in locals() else 0, 1)
        doc_hist = get_doctor_history(doctor_id, db) if 'db' in locals() else 15
        fallback_val = doc_hist if doc_hist > 5 else 15
        estimated_wait_time = int(calc_ahead_fallback * fallback_val)
        print(f"  - Result: Fallback used ({fallback_val}m/patient): {estimated_wait_time}m")

    # Fetch full user details from DB to get name and phone
    patient_user = db.query(User).filter(User.id == current_user.user_id).first()
    
    token_doc = {
        "id": token_id,
        "token_number": token_number,
        "patient_id": current_user.user_id,
        "doctor_id": doctor_id,
        "hospital_id": hospital_id,
        "mrn": mrn,
        "hex_code": f"{token_id[:7]}{token_number:03d}",
        "appointment_date": appointment_date,
        "status": TokenStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
        "doctor_name": doctor_data.get("name"),
        "hospital_name": hospital_data.get("name"),
        "patient_name": patient_user.name if patient_user else "Patient",
        "patient_phone": patient_user.phone if patient_user else None,
        "consultation_fee": pricing.get("consultation_fee"),
        "session_fee": pricing.get("session_fee"),
        "total_fee": pricing.get("total_amount"),
        "estimated_wait_time": estimated_wait_time,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    # Create token model in PostgreSQL
    valid_fields = {c.name for c in Token.__table__.columns}
    filtered_token_doc = {k: v for k, v in token_doc.items() if k in valid_fields}
    
    new_token = Token(**filtered_token_doc)
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    # RE-FETCH AND MAP FOR RESPONSE
    out_dict = {k: v for k, v in new_token.__dict__.items() if not k.startswith('_')}
    # Force the calculated wait time into the dictionary in case the DB column is missing or doesn't persist it
    out_dict["estimated_wait_time"] = estimated_wait_time
    
    response_obj = SmartTokenResponse(**out_dict)
    print(f"[DEBUG] FINAL RETURN estimated_wait_time: {response_obj.estimated_wait_time}")

    await create_activity_log(current_user.user_id, ActivityType.TOKEN_GENERATED, f"Generated Token #{token_number}", {"token_id": token_id}, db=db)
    
    # 🔥 WHATSAPP NOTIFICATION (Fix 4 Logic)
    try:
        from app.services.whatsapp_service import send_queue_message
        # Calculate current position (total tokens today)
        position = total_tokens_today + 1
        send_queue_message(
            phone=new_token.patient_phone,
            name=new_token.patient_name or "Patient",
            position=position,
            wait_time=estimated_wait_time,
            doctor_name=new_token.doctor_name or "Doctor",
            hospital_name=new_token.hospital_name or "Hospital",
            room_number="Room 1" # Defaulting as it's not in the token model yet
        )
        
        # Schedule confirmation check after 15 mins
        schedule_confirmation_checks(token_id)
    except Exception as e:
        print(f"[ERROR] Failed to trigger WhatsApp notification or schedule reminder: {e}")

    return response_obj

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

@router.get("/my-tokens", response_model=List[SmartTokenResponse])
async def get_my_tokens(
    only_active: bool = Query(True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    query = db.query(Token).filter(Token.patient_id == current_user.user_id)
    if only_active:
        query = query.filter(Token.status.notin_(["cancelled", "completed"]))
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
        Token.status.notin_(["cancelled", "completed"]),
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

@router.get("/{token_id}/appointment-details")
async def get_appointment_details(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token: raise HTTPException(status_code=404, detail="Token not found")
    if token.patient_id != current_user.user_id: raise HTTPException(status_code=403, detail="Access denied")
    
    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == token.hospital_id).first()
    
    queue = SmartTokenService.get_queue_status(token.doctor_id, token.token_number, token.appointment_date)
    
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
    if not token: raise HTTPException(status_code=404, detail="Token not found")
    
    return SmartTokenService.get_queue_status(token.doctor_id, token.token_number, token.appointment_date, db=db)

@router.post("/{token_id}/payment", response_model=PaymentResponse)
async def process_payment(
    token_id: str,
    payment: PaymentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token: raise HTTPException(status_code=404, detail="Token not found")
    
    token.payment_status = PaymentStatus.PAID
    token.status = TokenStatus.CONFIRMED
    token.updated_at = datetime.utcnow()
    db.commit()
    
    await create_activity_log(current_user.user_id, ActivityType.PAYMENT_MADE, f"Paid for Token #{token.token_number}", {"token_id": token_id}, db=db)
    
    return PaymentResponse(id=str(uuid.uuid4()), token_id=token_id, amount=payment.amount, status=PaymentStatus.PAID, created_at=datetime.utcnow())

@router.get("/hospital/{hospital_id}")
async def get_hospital_tokens(
    hospital_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    tokens = db.query(Token).filter(Token.hospital_id == hospital_id).all()
    return [{k: v for k, v in t.__dict__.items() if not k.startswith('_')} for t in tokens]

@router.patch("/update-status/{token_id}")
async def update_token_status(
    token_id: str,
    payload: QueueTokenStatusUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token: raise HTTPException(status_code=404, detail="Token not found")
    
    old_status = token.status
    new_status = _coerce_status(payload.status)
    token.status = new_status
    token.updated_at = datetime.utcnow()
    
    # Update timing fields based on status
    if new_status == "in_progress" and old_status != "in_progress":
        token.started_at = datetime.utcnow()
    elif new_status == "completed" and old_status != "completed":
        token.completed_at = datetime.utcnow()
        if token.started_at:
            duration = (token.completed_at - token.started_at).total_seconds() / 60.0
            token.duration_minutes = round(duration, 2)
        
        # Send WhatsApp Thankyou Notification
        try:
            from app.services.whatsapp_service import send_template_message
            from app.templates import TEMPLATES
            if token.patient_phone:
                import asyncio
                tpl = TEMPLATES.get("THANKYOU")
                if tpl:
                    asyncio.create_task(send_template_message(
                        token.patient_phone, 
                        tpl, 
                        []
                    ))
        except Exception as e:
            print(f"[ERROR] Failed to send thankyou notification: {e}")
    elif new_status == "cancelled" and old_status != "cancelled":
        token.cancelled_at = datetime.utcnow()
        # Send WhatsApp Cancelled Notification
        try:
            from app.services.whatsapp_service import send_template_message
            if token.patient_phone:
                import asyncio
                asyncio.create_task(send_template_message(
                    token.patient_phone, 
                    "cancelled", 
                    [token.patient_name or "Patient"]
                ))
        except Exception as e:
            print(f"[ERROR] Failed to send cancel notification: {e}")
    elif new_status == "skipped" and old_status != "skipped":
        token.skipped_at = datetime.utcnow()
        # Send WhatsApp Skipped Notification
        try:
            from app.services.whatsapp_service import send_template_message
            from app.templates import TEMPLATES
            if token.patient_phone:
                import asyncio
                tpl = TEMPLATES.get("RESCHEDULED")
                if tpl:
                    asyncio.create_task(send_template_message(
                        token.patient_phone, 
                        tpl, 
                        [token.patient_name or "Patient", token.token_number]
                    ))
        except Exception as e:
            print(f"[ERROR] Failed to send skipped notification: {e}")
    
    # If status is moving to completed or cancelled, trigger recalculation for remaining tokens
    # Also if someone is "called", the wait times for others might change
    if new_status != old_status:
        db.commit() # Save the status change first
        
        # Determine the local day for this token's appointment
        doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
        doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {}
        tz_minutes = _tz_offset_for(doctor_data)
        day_local = _local_day_for(token.appointment_date, tz_minutes)
        
        # Trigger recalculation
        _recalculate_token_wait_times(db, token.doctor_id, token.hospital_id, day_local)
    else:
        db.commit()

    return {"success": True}

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    spec: TokenCreateSpec,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a token atomically for a specific doctor and clinic-local date."""
    doctor = db.query(Doctor).filter(Doctor.id == spec.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == spec.hospital_id).first()
    if not doctor or not hospital:
        raise HTTPException(status_code=400, detail="Doctor or Hospital not found")

    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    tz_minutes = _tz_offset_for(doctor_data)
    day = _parse_local_date(spec.appointment_date, tz_minutes)

    token_number = _allocate_queue_token_number(db, spec.hospital_id, spec.doctor_id, day)
    
    appt_dt_utc = _minute_for_token_number(
        doctor_data.get("start_time") or "09:00",
        doctor_data.get("end_time") or "17:00",
        token_number,
        tz_minutes,
        base_utc=datetime.utcnow().replace(tzinfo=timezone.utc)
    )
    
    token_id = str(uuid.uuid4())
    # Generate patient MRN if not exists
    mrn = get_or_create_patient_mrn(db, current_user.user_id, spec.hospital_id)

    token_doc = {
        "id": token_id,
        "patient_id": current_user.user_id,
        "doctor_id": spec.doctor_id,
        "hospital_id": spec.hospital_id,
        "mrn": mrn,
        "token_number": token_number,
        "hex_code": f"{token_id[:7]}{token_number:03d}",
        "appointment_date": appt_dt_utc,
        "status": TokenStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
        "doctor_name": doctor_data.get("name"),
        "hospital_name": hospital.name,
        "patient_name": getattr(current_user, "name", None),
        "patient_phone": getattr(current_user, "phone", None),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    # Create token model in PostgreSQL
    valid_fields = {c.name for c in Token.__table__.columns}
    filtered_token_doc = {k: v for k, v in token_doc.items() if k in valid_fields}
    
    new_token = Token(**filtered_token_doc)
    db.add(new_token)
    db.commit()
    db.refresh(new_token)

    # Schedule confirmation check after 15 mins
    try:
        schedule_confirmation_checks(token_doc["id"])
    except Exception as e:
        print(f"[ERROR] Failed to schedule confirmation check: {e}")

    q = _queue_object_for(db, spec.doctor_id, spec.hospital_id, day, token_number)
    token_resp = _to_smart_token_response(new_token)
    
    # We return a custom object here because the frontend expects 'queue' embedded
    return {
        **token_resp.model_dump(),
        "queue": q,
    }

@router.post("/cancel", response_model=CancellationResponse)
async def cancel_token_alias(
    payload: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token_id = payload.get("token_id")
    if not token_id: raise HTTPException(status_code=400, detail="token_id is required")
    return await cancel_token_endpoint(token_id, payload, db, current_user)

@router.delete("/{token_id}/cancel", response_model=CancellationResponse)
async def cancel_token_delete(
    token_id: str,
    payload: dict = Body({}),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    return await cancel_token_endpoint(token_id, payload, db, current_user)

@router.get("/my-active", response_model=SmartTokenResponse)
async def get_my_active_token(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.notin_(["cancelled", "completed"])
    ).order_by(Token.created_at.desc()).first()
    
    if not token:
        raise HTTPException(status_code=404, detail="No active token found")
    
    return _to_smart_token_response(token)

@router.get("/my-active-details")
async def get_my_active_token_details(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    active = await get_my_active_token(db, current_user)
    return await get_appointment_details(active.id, db, current_user)

@router.get("/history", response_model=List[SmartTokenResponse])
async def get_token_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    tokens = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.in_(["cancelled", "completed"])
    ).order_by(Token.created_at.desc()).all()
    return [_to_smart_token_response(t) for t in tokens]

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

@router.post("/generate/by-selection")
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
        SmartTokenGenerateRequest(doctor_id=doctor_id, hospital_id=hospital_id),
        db=db,
        current_user=current_user
    )

@router.post("/{token_id}/notify/summary")
async def notify_appointment_summary(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token: raise HTTPException(status_code=404, detail="Token not found")
    
    # Mock notification
    return {"success": True, "message": "Summary sent"}

@router.post("/{token_id}/notifications")
async def send_token_notifications(
    token_id: str,
    request: NotificationRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    # Mock notification
    return {"success": True, "message": "Notifications sent"}
