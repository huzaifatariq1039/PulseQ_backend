from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.routes import tokens
from app.security import require_roles, get_current_active_user 
from app.models import TokenData
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue, Department
from app.utils.responses import ok
from datetime import datetime, timedelta, timezone, time
import random
from app.services.token_service import SmartTokenService
from app.routes.pharmacy import router as pharmacy_router
from app.utils.mrn import get_or_create_patient_mrn
import uuid
import logging
from app.routes.tokens import avg_last_5, avg_last_10
# OR wherever these functions live in your codebase

# --- 🚀 AI Engine Imports ---
from app.services.ai_engine import ai_engine
from app.services.queue_management_service import (
    get_current_hour, get_current_day, calculate_queue_velocity, get_last_patient_duration,
    avg_last_5, avg_last_10, count_available_doctors, get_hour_history,
    get_weekday_history, get_doctor_history
)

router = APIRouter()

logger = logging.getLogger(__name__)

# Include Pharmacy portal endpoints under the centralized portal router
router.include_router(pharmacy_router)


def _parse_positive_int(value: Optional[int], default: int, maximum: int = 100) -> int:
    try:
        v = int(value or default)
        if v <= 0:
            return default
        return min(v, maximum)
    except Exception:
        return default


# -------------------- Shared datetime helpers --------------------
def _tz_offset_minutes(hospital: Optional[Hospital]) -> int:
    try:
        if hospital:
            return getattr(hospital, "tz_offset_minutes", 300)
    except Exception:
        pass
    return 300


def _as_utc(dt: datetime) -> datetime:
    try:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return dt


def _to_local(dt: datetime, tz_minutes: int) -> datetime:
    try:
        tz = timezone(timedelta(minutes=int(tz_minutes or 0)))
        return _as_utc(dt).astimezone(tz)
    except Exception:
        return dt


@router.get("/notifications")
async def list_portal_notifications(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    unread_only: bool = Query(True),
    limit: Optional[int] = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    from app.db_models import ActivityLog as Notification  
    
    query = db.query(Notification).filter(Notification.user_id == current.user_id)
    if unread_only:
        if hasattr(Notification, 'is_read'):
            query = query.filter(Notification.is_read == False)

    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    items = [{k: v for k, v in n.__dict__.items() if not k.startswith('_')} for n in notifications]
    
    return ok(data=items, meta={"unread_only": unread_only, "count": len(items)})


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    from app.db_models import ActivityLog as Notification
    
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    
    if str(notif.user_id) != str(current.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if hasattr(notif, 'is_read'):
        notif.is_read = True
        if hasattr(notif, 'read_at'):
            notif.read_at = datetime.utcnow()
        db.commit()
        
    return ok(message="Notification marked as read")


@router.get("/doctor/tokens", dependencies=[Depends(require_roles("doctor", "patient", "admin"))])
async def get_doctor_tokens(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    patient_id: Optional[str] = Query(None, description="Filter by specific patient ID"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=500),
) -> Dict[str, Any]:
    """Get tokens/patient history - Doctors see only their own tokens, admins see all"""
    
    query = db.query(Token)
    
    # Filter by doctor if user is a doctor (not admin)
    user_role = str(getattr(current, "role", "")).lower()
    if user_role == "doctor":
        # ✅ Fix — look up doctor by user_id first, then filter by doctor.id
        doctor = db.query(Doctor).filter(
            or_(
                Doctor.user_id == current.user_id,
                Doctor.id == current.user_id
            )
        ).first()

        if not doctor:
            # No doctor profile found — return empty
            return ok(data=[], meta={"page": page, "page_size": page_size, "total": 0})

        query = query.filter(Token.doctor_id == doctor.id)  # ✅ use doctor.id not user_id

    
    if patient_id:
        query = query.filter(Token.patient_id == patient_id)
    
    if status_filter:
        query = query.filter(func.lower(Token.status) == str(status_filter).lower())
    
    total = query.count()
    size = _parse_positive_int(page_size, 20)
    skip = (page - 1) * size
    
    tokens = query.order_by(Token.appointment_date.desc()).offset(skip).limit(size).all()
    items = []
    
    for t in tokens:
        # ✅ FIX: Time calculation fallback for standard token list
        start = t.started_at or t.created_at
        end = t.completed_at or t.updated_at
        duration = 0
        if start and end:
            if end > start:
                duration = round((end - start).total_seconds() / 60)
            elif str(t.status).lower() == "completed":
                duration = 1 # Give 1 min minimum to prevent 0 min glitch
                
        items.append({
          "token_id": t.id,
          "token_number": t.display_code or str(t.token_number),
           "patient_name": t.patient_name or "Unknown",
           "patient_age": t.patient_age,
           "patient_gender": t.patient_gender,
           "patient_phone": getattr(t, 'patient_phone', None),
           "doctor_name": t.doctor_name,
           "appointment_date": t.appointment_date,
           "status": str(t.status).lower(),
           "mrn": getattr(t, 'mrn', None) or "N/A",
           "department": t.department,
           "reason_for_visit": t.reason_for_visit or "",   
           "consultation_notes": t.consultation_notes or "",              
           "started_at": start, # ✅ Overrides nulls
           "completed_at": end, # ✅ Overrides nulls
           "duration": duration,
        })
    
    return ok(data=items, meta={"page": page, "page_size": size, "total": total})


@router.get("/completed-consultations", dependencies=[Depends(require_roles("doctor", "admin"))])
async def get_completed_consultations(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=500),
):
    """Get completed tokens for the current doctor/admin with statistics."""
    
    is_admin = getattr(current, "role", "") == "admin"
    
    # ✅ FIX 1: Strict status filtering to absolutely block "skipped" tokens
    base_filters = [func.lower(Token.status) == "completed"]

    if not is_admin:
        doctor = db.query(Doctor).filter(or_(Doctor.user_id == current.user_id, Doctor.id == current.user_id)).first()
        target_doctor_id = doctor.id if doctor else current.user_id
        base_filters.append(Token.doctor_id == target_doctor_id)
    else:
        if getattr(current, "hospital_id", None):
            base_filters.append(Token.hospital_id == current.hospital_id)

    base_query = db.query(Token).filter(*base_filters)
    
    # ✅ FIX 2: Timezone correction for Top Cards (Aligning Server UTC to PKT UTC+5)
    tz_offset_minutes = 300 
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(minutes=tz_offset_minutes)
    
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local - timedelta(minutes=tz_offset_minutes)
    
    month_start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_start_local - timedelta(minutes=tz_offset_minutes)
    
    total_completed = base_query.count()
    completed_today = base_query.filter(
        or_(Token.completed_at >= today_start_utc, Token.updated_at >= today_start_utc)
    ).count()
    completed_this_month = base_query.filter(
        or_(Token.completed_at >= month_start_utc, Token.updated_at >= month_start_utc)
    ).count()
    
    # Average consultation time (in minutes) using fallback timestamps
    avg_consultation_time = 0
    all_completed = base_query.all()
    if all_completed:
        total_minutes = 0
        count = 0
        for token in all_completed:
            start = token.started_at or token.created_at
            end = token.completed_at or token.updated_at
            if start and end:
                if end > start:
                    total_minutes += (end - start).total_seconds() / 60
                else:
                    total_minutes += 1 # At least 1 min
                count += 1
                
        if count > 0:
            avg_consultation_time = round(total_minutes / count)
    
    size = _parse_positive_int(page_size, 20)
    skip = (page - 1) * size
    
    tokens = base_query.order_by(
        Token.completed_at.desc() if hasattr(Token, 'completed_at') else Token.updated_at.desc()
    ).offset(skip).limit(size).all()
    
    items = []
    patient_ids = [t.patient_id for t in tokens]
    doctor_ids = [t.doctor_id for t in tokens]

    patients = {u.id: u for u in db.query(User).filter(User.id.in_(patient_ids)).all()}
    doctors = {d.id: d for d in db.query(Doctor).filter(Doctor.id.in_(doctor_ids)).all()}

    for t in tokens:
        patient = patients.get(t.patient_id)
        doctor_obj = doctors.get(t.doctor_id)

        # ✅ FIX 3: Robust Fallback to fix "12:00 AM" and "0 min" visual bugs
        start = t.started_at or t.created_at
        end = t.completed_at or t.updated_at
        duration = 0 
        
        if start and end:
            if end > start:
                duration = round((end - start).total_seconds() / 60)
            else:
                duration = 1 # Prevent mathematically impossible 0 minute completions

        # ✅ FIX 4: Explicitly pull MRN if token misses it
        mrn_val = getattr(t, 'mrn', None)
        if not mrn_val and patient:
            mrn_val = getattr(patient, 'mrn', None)
    
        items.append({ 
            "token_number": t.token_number,
            "mrn": mrn_val or "N/A",
            "patient_name": t.patient_name or (patient.name if patient else "Unknown"),
            "doctor_name": getattr(t, 'doctor_name', None) or (doctor_obj.name if doctor_obj else "Unknown"),
            "department": getattr(t, 'department', None) or (doctor_obj.specialization if doctor_obj else "General"),
            "start_time": start, # Frontend receives valid ISO string instead of null
            "end_time": end,     # Frontend receives valid ISO string instead of null
            "duration": duration,
            "status": str(t.status).lower(),
            "consultation_notes": getattr(t, 'consultation_notes', ""), 
        })
    
    return ok(
        data=items,
        meta={
            "page": page,
            "page_size": size,
            "total": total_completed,
            "total_completed": total_completed,
            "completed_today": completed_today,
            "completed_this_month": completed_this_month,
            "avg_consultation_time": avg_consultation_time,
        }
    )

@router.get("/doctor/dashboard", dependencies=[Depends(require_roles("doctor", "patient", "admin"))])
async def doctor_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    upcoming_limit: int = Query(5, ge=0, le=50),
    skipped_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    doctor = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    if not doctor:
        doctor = db.query(Doctor).filter(Doctor.id == current.user_id).first()
    
    user = db.query(User).filter(User.id == current.user_id).first()
    user_name = user.name if user else "Doctor"
        
    if doctor and doctor.status:
        if isinstance(doctor.status, str):
            doctor_status = doctor.status.lower()
        elif hasattr(doctor.status, 'value'):
            doctor_status = doctor.status.value.lower()
        else:
            doctor_status = "available"
    else:
        doctor_status = "available"
    
    doctor_header = {
        "id": doctor.id if doctor else current.user_id,
        "name": doctor.name if doctor else user_name,
        "department": doctor.specialization if doctor and doctor.specialization else "General Medicine",
        "room": getattr(doctor, "room_number", None) or getattr(doctor, "room", None) or "Not Assigned",
        "status": doctor_status,
        "email": doctor.email if doctor and doctor.email else None,
        "consultation_fee": doctor.consultation_fee if doctor else None,
        "session_fee": doctor.session_fee if doctor else None,
        "available_days": doctor.available_days if doctor else [],
        "start_time": doctor.start_time if doctor else None,
        "end_time": doctor.end_time if doctor else None,
    }

    tz_offset_minutes = 300 
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(minutes=tz_offset_minutes)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local - timedelta(minutes=tz_offset_minutes)
    today_end_utc = today_start_utc + timedelta(days=1)
    
    target_doctor_id = doctor.id if doctor else current.user_id
    
    todays = db.query(Token).filter(
        Token.doctor_id == target_doctor_id,
        Token.appointment_date >= today_start_utc,
        Token.appointment_date < today_end_utc
    ).all()

    completed_tokens = [t for t in todays if str(t.status).lower() == "completed"]
    skipped_tokens = [t for t in todays if str(t.status).lower() == "skipped"]
    
    active_tokens = [t for t in todays if str(t.status).lower() in ("in_consultation", "pending", "confirmed", "waiting")]
    active_tokens.sort(key=lambda x: x.token_number)
    
    current_consult = next((t for t in active_tokens if str(t.status).lower() == "in_consultation"), None)
    
    curr_num = current_consult.token_number if current_consult else 0
    waiting_tokens = [t for t in active_tokens if str(t.status).lower() in ("pending", "confirmed", "waiting") and t.token_number > curr_num]

    def _patient_row(t: Token) -> Dict[str, Any]:
        age_display = "N/A"
        if t.patient_age is not None:
            try:
                age_val = int(t.patient_age)
                age_display = f"{age_val}y"
            except (ValueError, TypeError):
                age_display = "N/A"
        
        return {
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "mrn": getattr(t, 'mrn', None) or "N/A",
            "patient_name": t.patient_name or "Unknown",
            "patient_age": age_display,
            "patient_gender": t.patient_gender or "Unknown",
            "phone": getattr(t, 'patient_phone', None) or "N/A",
            "reason_for_visit": getattr(t, 'reason_for_visit', None) or "General Consultation",
            "status": t.status.value if hasattr(t.status, 'value') else str(t.status).lower(),
            "payment": "Paid" if t.payment_status == "paid" else "Unpaid",
            "source": "walk_in" if getattr(t, 'is_walk_in', False) else "online",
        }

    upcoming = [_patient_row(t) for t in waiting_tokens[:upcoming_limit]]
    skipped = [_patient_row(t) for t in skipped_tokens[:skipped_limit]]

    return ok(
        data={
            "doctor": doctor_header,
            "active_session": bool(current_consult),
            "cards": {
                "waiting_in_queue": len(waiting_tokens),
                "patients_served": len(completed_tokens),
            },
            "current_consultation": _patient_row(current_consult) if current_consult else None,
            "upcoming_patients": upcoming,
            "skipped_patients": skipped,
        }
    )


@router.get("/admin/dashboard", dependencies=[Depends(require_roles("admin", "patient"))])
async def admin_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None),
    logs_limit: int = Query(10, ge=1, le=50),
):
    doc_query = db.query(Doctor)
    if hospital_id:
        doc_query = doc_query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = doc_query.all()
    active_doctors = len([d for d in doctors if str(d.status).lower() in ("available", "active")])
    departments_count = db.query(func.count(func.distinct(Doctor.specialization))).scalar()

    tz_offset_minutes = 300 
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(minutes=tz_offset_minutes)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local - timedelta(minutes=tz_offset_minutes)
    
    token_query = db.query(Token).filter(Token.created_at >= today_start_utc)
    if hospital_id:
        token_query = token_query.filter(Token.hospital_id == hospital_id)
    
    total_patients_today = token_query.count()

    wait_time_query = db.query(func.avg(
        func.extract('epoch', Token.started_at) - func.extract('epoch', Token.created_at)
    )).filter(
        Token.created_at >= today_start_utc,
        Token.started_at.isnot(None)
    )
    if hospital_id:
        wait_time_query = wait_time_query.filter(Token.hospital_id == hospital_id)
    
    avg_wait_seconds = wait_time_query.scalar() or 0
    avg_wait_minutes = round(avg_wait_seconds / 60)

    flow_today = []
    for hour in range(24):
        h_start = today_start_utc + timedelta(hours=hour)
        h_end = h_start + timedelta(hours=1)
        count = db.query(Token).filter(
            Token.created_at >= h_start,
            Token.created_at < h_end
        ).count()
        flow_today.append({"hour": f"{hour:02d}:00", "count": count})

    flow_monthly = []
    for day in range(30):
        d_start = (now_utc - timedelta(days=29-day)).replace(hour=0, minute=0, second=0, microsecond=0)
        d_end = d_start + timedelta(days=1)
        count = db.query(Token).filter(
            Token.created_at >= d_start,
            Token.created_at < d_end
        ).count()
        flow_monthly.append({"date": d_start.strftime("%d %b"), "count": count})

    recent_tokens = token_query.order_by(Token.created_at.desc()).limit(logs_limit).all()
    logs = []
    for t in recent_tokens:
        logs.append({
            "message": f"Token {t.display_code or t.token_number} generated for {t.doctor_name}",
            "time_ago": "recent",
            "created_at": t.created_at.isoformat()
        })

    return ok(
        data={
            "cards": {
                "total_patients_today": total_patients_today,
                "active_doctors": active_doctors,
                "avg_wait_time_minutes": avg_wait_minutes,
                "departments": departments_count,
            },
            "patient_flow_today": flow_today,
            "patient_flow_monthly": flow_monthly,
            "live_system_logs": logs,
        }
    )


@router.get("/receptionist/dashboard", dependencies=[Depends(require_roles("receptionist", "patient", "admin"))])
async def receptionist_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    upcoming_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    tz_offset_minutes = 300 
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(minutes=tz_offset_minutes)
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local - timedelta(minutes=tz_offset_minutes)
    
    query = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.appointment_date >= today_start_utc
    )
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)
    
    todays = query.all()
    
    waiting = [t for t in todays if str(t.status).lower() in ("pending", "confirmed")]
    completed = [t for t in todays if str(t.status).lower() == "completed"]
    skipped = [t for t in todays if str(t.status).lower() in ("skipped", "cancelled")]
    
    active = [t for t in todays if str(t.status).lower() in ("in_consultation", "pending", "confirmed", "called")]
    active.sort(key=lambda x: x.token_number)
    
    now_serving = next((t for t in active if str(t.status).lower() in ("in_consultation", "called")), active[0] if active else None)

    def _get_age_and_gender(patient_id, token_obj):
        if token_obj:
            token_age = getattr(token_obj, 'patient_age', None)
            token_gender = getattr(token_obj, 'patient_gender', None)
            
            if token_age is not None:
                try:
                    age_val = int(token_age)
                    age = f"{age_val}y"
                except Exception:
                    age = "N/A"
            else:
                age = "N/A"
            
            if token_gender:
                gender = str(token_gender).capitalize()
            else:
                gender = "Unknown"
            
            if age != "N/A" or gender != "Unknown":
                return age, gender
        
        if not patient_id: return "N/A", "Unknown"
        user = db.query(User).filter(User.id == patient_id).first()
        if not user: return "N/A", "Unknown"
        
        age = "N/A"
        if user.date_of_birth:
            try:
                dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
                age = f"{(datetime.utcnow() - dob).days // 365}y"
            except Exception: pass
        
        gender = getattr(user, 'gender', None) or "Unknown"
        if gender and gender != "Unknown":
            gender = str(gender).capitalize()
        
        return age, gender
    
    def _get_avg_service_time(doctor_id: str) -> float:
        try:
           last_5 = avg_last_5(doctor_id, db) or 5.0
           last_10 = avg_last_10(doctor_id, db) or 5.0
           return round((0.6 * last_5) + (0.4 * last_10), 1)
        except Exception:
           return 5.0

    upcoming = []
    position = 1
    for t in active:
        if now_serving and t.id == now_serving.id:
            continue
        age, gender = _get_age_and_gender(t.patient_id, t)

        doc_id = t.doctor_id or doctor_id
        avg_service = _get_avg_service_time(doc_id)
        live_wait = max(1, round(position * avg_service))

        
        upcoming.append({
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "patient_name": t.patient_name,
            "patient_age": age,
            "patient_gender": gender,
            "status": str(t.status).lower(),
            "doctor_name": t.doctor_name,
            "waiting_time_minutes": getattr(t, 'estimated_wait_time', 0) or 0
        })

        position += 1
        if len(upcoming) >= upcoming_limit:
            break
            
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()
    active_doctors = []
    for d in doctors:
        status_val = str(getattr(d, 'status', 'available') or 'available').lower()
        if status_val in ("available", "busy"):
            active_doctors.append({
                "doctor_id": d.id,
                "doctor_name": d.name,
                "department": getattr(d, 'specialization', None) or getattr(d, 'department', None) or "General",
                "room_number": getattr(d, 'room_number', None) or getattr(d, 'room', None) or "101",
                "status": status_val
            })

    now_serving_age, now_serving_gender = "N/A", "Unknown"
    if now_serving:
         now_serving_age, now_serving_gender = _get_age_and_gender(now_serving.patient_id, now_serving)

    return ok(
        data={
            "now_serving": {
                "token_id": now_serving.id,
                "token_number": now_serving.display_code or str(now_serving.token_number),
                "patient_name": now_serving.patient_name,
                "patient_age": now_serving_age,
                "patient_gender": now_serving_gender,
                "reason": getattr(now_serving, 'department', None) or "General Consultation",
                "doctor_name": now_serving.doctor_name,
            } if now_serving else None,
            "upcoming_queue": upcoming,
            "active_doctors": active_doctors,
            "cards": {
                "waiting": len(waiting),
                "completed": len(completed),
                "skipped": len(skipped),
                #"avg_wait_minutes": (
                #    sum((getattr(t, 'estimated_wait_time', 0) or 0) for t in active) // len([t for t in active if (getattr(t, 'estimated_wait_time', 0) or 0) > 0])
                #) if any((getattr(t, 'estimated_wait_time', 0) or 0) > 0 for t in active) else 0,
                "avg_wait_minutes": round(
                    _get_avg_service_time(doctor_id or (doctors[0].id if doctors else None))
                ) if active else 0,
            }
        }
    )

# --------------------------------------------------------------------------------
# 🚀 UNIFIED AI WALK-IN TOKEN ENDPOINT
# --------------------------------------------------------------------------------
@router.post("/receptionist/walkin-token", dependencies=[Depends(require_roles("receptionist", "patient", "admin"))])
async def receptionist_create_walkin_token(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    hospital_id = payload.get("hospital_id")
    doctor_id = payload.get("doctor_id")
    patient_name = payload.get("patient_name")
    phone = payload.get("phone")
    age = payload.get("age")
    gender = payload.get("gender")
    reason = payload.get("reason")
    
    if not all([hospital_id, doctor_id, patient_name, phone]):
        raise HTTPException(status_code=400, detail="Missing required fields: hospital, doctor, name, phone")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    
    # 1. Calculate precise UTC bounds for today to match Patient Portal exactly
    tz_doc = doctor_data.get("tz_offset_minutes", 300)
    tz = timezone(timedelta(minutes=tz_doc))
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone(tz)
    day_local = now_local.date()
    
    local_start = datetime.combine(day_local, time.min).replace(tzinfo=tz)
    local_end = datetime.combine(day_local, time.max).replace(tzinfo=tz)
    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    # 2. Find or Create User
    dob_str = None
    patient_age_int = 30 # Default for AI if missing
    if age:
        try:
            patient_age_int = int(age)
            dob_str = (datetime.utcnow() - timedelta(days=patient_age_int*365)).strftime("%Y-%m-%d")
        except Exception:
            pass

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            name=patient_name,
            phone=phone,
            role="patient",
            password_hash="", 
            date_of_birth=dob_str,
            gender=gender
        )
        db.add(user)
    else:
        if dob_str and not user.date_of_birth:
            user.date_of_birth = dob_str
        if gender and not user.gender:
            user.gender = gender
        if patient_name and user.name != patient_name:
            user.name = patient_name
            
        if user.date_of_birth and not age:
            try:
                dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
                patient_age_int = (datetime.utcnow() - dob).days // 365
            except Exception:
                pass

    db.commit()
    db.refresh(user)

    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    hospital_name_str = hospital.name if hospital else "Unknown Hospital"
    mrn = get_or_create_patient_mrn(db, user.id, hospital_id)

    doc_fee = float(doctor.consultation_fee or 0)
    token_fee = 50.0
    total_fee = doc_fee + token_fee

    last_token = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.doctor_id == doctor_id,
        Token.appointment_date >= utc_start,
        Token.appointment_date <= utc_end
    ).order_by(Token.token_number.desc()).first()
    
    next_num = (last_token.token_number + 1) if last_token else 1
    token_id = str(uuid.uuid4())
    
    doc_initial = doctor.name.strip()[0].upper() if doctor.name else "T"
    if doctor.name and doctor.name.lower().startswith("dr"):
        clean_name = doctor.name[2:].replace(".", "").strip()
        doc_initial = clean_name[0].upper() if clean_name else "D"
        
    display_code = f"{doc_initial}-{next_num:03d}"
    
    # ---------------------------------------------------------
    # 🚀 AI ESTIMATED WAIT TIME CALCULATION
    # ---------------------------------------------------------
    estimated_wait_time = 0
    BLOCKING_STATUSES = ["waiting", "confirmed", "pending", "called", "in_consultation", "in_progress", "TokenStatus.PENDING", "TokenStatus.WAITING", "TokenStatus.CONFIRMED"]

    try:
        patients_ahead = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(BLOCKING_STATUSES),
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        completed_today = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            func.lower(Token.status) == "completed",
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        if completed_today == 0:
            estimated_wait_time = (patients_ahead + 1) * 5
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
                    "Name": patient_name,
                    "Doctor Name": doctor_data.get("name", "Unknown"),
                    "Service_Duration": 0, 
                    "Disease": reason or doctor_data.get("specialization") or "General",
                    "Age": patient_age_int
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
        logger.error(f"AI Wait Time Calculation failed for walk-in: {e}", exc_info=True)
        # Safe Fallback
        try:
            last_5 = avg_last_5(doctor_id, db) or 5.0
            estimated_wait_time = int(max(patients_ahead, 1) * last_5)
        except Exception:
            estimated_wait_time = max(0, patients_ahead * 15)

    # ---------------------------------------------------------

    new_token = Token(
        id=token_id,
        patient_id=user.id,
        doctor_id=doctor_id,
        hospital_id=hospital_id,
        mrn=mrn,
        token_number=next_num,
        display_code=display_code,
        hex_code=token_id[:8],
        appointment_date=datetime.utcnow(),
        status="pending",
        patient_name=patient_name,
        patient_phone=phone,
        patient_age=patient_age_int,
        patient_gender=gender,
        doctor_name=doctor.name,
        doctor_specialization=doctor.specialization,
        department=doctor.specialization,
        reason_for_visit=reason,
        hospital_name=hospital_name_str,
        consultation_fee=doc_fee,
        total_fee=total_fee,
        estimated_wait_time=estimated_wait_time
    )
    
    db.add(new_token)
    db.commit()

    # ✅ Send WhatsApp appointment confirmation to patient
    if phone:
        try:
            from app.services.whatsapp_service import send_template_message

            def _normalize_phone(p: str) -> str:
                p = str(p).strip().replace(" ", "").replace("-", "")
                if p.startswith("0") and len(p) == 11:
                    return "+92" + p[1:]
                if not p.startswith("+"):
                    return "+" + p
                return p

            room_number = getattr(doctor, 'room_number', None) or getattr(doctor, 'room', None) or "TBD"

            await send_template_message(
                phone=_normalize_phone(phone),
                template_name="token_number",  # ← replace with your actual template name
                params=[
                    doctor.name,                  # {doctor_name}
                    patient_name,                 # {name}
                    hospital_name_str,            # {hospital_name}
                    str(room_number),             # {room_number}
                    str(estimated_wait_time),     # {wait_time}
                ]
            )
            logger.info(f"WhatsApp walk-in confirmation sent to {phone} for token {token_id}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp walk-in confirmation for token {token_id}: {e}")

    return ok(data={"token_id": token_id})

@router.post("/receptionist/tokens/{token_id}/skip", dependencies=[Depends(require_roles("receptionist", "patient", "admin"))])
async def receptionist_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
        
    token.status = "skipped"
    token.updated_at = datetime.utcnow()
    token.skipped_at = datetime.utcnow()
    db.commit()

    try:
        from app.services.message_scheduler import schedule_skip_messages
        await schedule_skip_messages(token_id)
        logger.info(f"Skip message scheduler triggered for token {token_id}")
    except Exception as e:
        logger.error(f"Failed to schedule skip messages for token {token_id}: {e}")
    
    return ok(message="Token skipped")


@router.post("/doctor/tokens/{token_id}/skip", dependencies=[Depends(require_roles("doctor", "admin"))])
async def doctor_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    doctor_profile = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    doctor_profile_id = doctor_profile.id if doctor_profile else None
    
    if str(current.user_id) != str(token.doctor_id) and str(doctor_profile_id) != str(token.doctor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only skip your own tokens"
        )
    
    st = str(token.status).lower()
    if st in ["completed", "cancelled", "skipped"]:
        raise HTTPException(
            status_code=400,
            detail=f"Token cannot be skipped. Current status: {st}"
        )
    
    now = datetime.utcnow()
    token.status = "skipped"
    token.skipped_at = now
    token.updated_at = now
    
    db.commit()
    
    try:
        from app.services.message_scheduler import schedule_skip_messages
        await schedule_skip_messages(token_id)
        logger.info(f"Skip message scheduler triggered for token {token_id}")
    except Exception as e:
        logger.error(f"Failed to schedule skip messages for token {token_id}: {e}")
    
    today = now.date()
    next_token_obj = db.query(Token).filter(
        Token.doctor_id == token.doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed"]),
        func.date(Token.appointment_date) == today,
        Token.token_number > token.token_number
    ).order_by(Token.token_number.asc()).first()
    
    next_token_data = None
    if next_token_obj:
        next_token_obj.status = "called"
        next_token_obj.called_at = now
        next_token_obj.updated_at = now
        
        db.commit()
        next_token_data = {k: v for k, v in next_token_obj.__dict__.items() if not k.startswith('_')}
    
    return ok(
        data={
            "token_id": token_id,
            "status": "skipped",
            "next_called_token": next_token_data
        },
        message="Token skipped successfully"
    )


@router.patch("/receptionist/tokens/{token_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_update_token(
    token_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if str(token.status).lower() in ["cancelled", "completed"]:
        raise HTTPException(status_code=400, detail=f"Cannot edit token with status: {token.status}")
    
    if "status" in payload:
        new_status = str(payload["status"]).strip().lower()
        valid_statuses = ["pending", "waiting", "confirmed", "called", "skipped", "completed", "cancelled"]
        
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        if str(token.status).lower() == "skipped" and new_status in ["waiting", "confirmed", "pending"]:
            token.status = new_status
            token.updated_at = datetime.utcnow()
            db.commit()
            return ok(
                data={
                    "token_id": token.id,
                    "display_code": token.display_code,
                    "patient_name": token.patient_name,
                    "status": token.status,
                    "previous_status": "skipped"
                },
                message=f"Token re-added successfully with status: {new_status}"
            )
        
        token.status = new_status
        token.updated_at = datetime.utcnow()
        db.commit()
        
        return ok(
            data={"token_id": token.id, "status": token.status},
            message="Token status updated successfully"
        )
    
    updatable_fields = [
        "patient_name", "patient_phone", "patient_gender",
        "reason_for_visit", "appointment_date", "department"
    ]
    
    if "reason" in payload and "reason_for_visit" not in payload:
        payload["reason_for_visit"] = payload["reason"]
    updated_fields = []
    for field in updatable_fields:
        if field in payload:
            setattr(token, field, payload[field])
            updated_fields.append(field)
    
    if "patient_age" in payload:
        try:
            age_str = str(payload["patient_age"]).strip()
            if age_str.endswith('y'):
                age_str = age_str[:-1]
            age = int(age_str)
            token.patient_age = age
            if "patient_age" not in updated_fields:
                updated_fields.append("patient_age")
        except (ValueError, TypeError):
            pass
    
    token.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(token)

    user = db.query(User).filter(User.id == token.patient_id).first()
    if user:
        if "patient_name" in updated_fields:
            user.name = token.patient_name
        if "patient_phone" in updated_fields:
            user.phone = token.patient_phone
        user.updated_at = datetime.utcnow()
        db.commit()
    
    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "patient_name": token.patient_name,
            "patient_age": token.patient_age,
            "patient_gender": token.patient_gender,
            "patient_phone": token.patient_phone,
            "status": token.status,
            "updated_fields": updated_fields
        },
        message="Token updated successfully"
    )


@router.delete("/receptionist/tokens/{token_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_delete_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if str(token.status).lower() == "completed":
        raise HTTPException(status_code=400, detail="Cannot delete completed token")
    
    if str(token.status).lower() == "cancelled":
        return ok(message="Token is already cancelled")
    
    token.status = "cancelled"
    token.cancelled_at = datetime.utcnow()
    token.updated_at = datetime.utcnow()
    db.commit()
    
    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "status": "cancelled",
            "cancelled_at": token.cancelled_at
        },
        message="Token cancelled/deleted successfully"
    )