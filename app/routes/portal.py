from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.security import require_roles, get_current_active_user 
from app.models import TokenData
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue, Department
from app.utils.responses import ok
from datetime import datetime, timedelta, timezone
import random
from app.services.token_service import SmartTokenService
from app.routes.pharmacy import router as pharmacy_router
from app.utils.mrn import get_or_create_patient_mrn
import uuid
import logging

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
            # Check for any variation of timezone offset in hospital model
            # Assuming db_models.Hospital might have it, if not default to 300
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
    # Assuming there's a Notification model in db_models, but let's check if it exists
    # If not, we'll need to add it or use a TODO. For now, assuming it exists based on previous logic.
    from app.db_models import ActivityLog as Notification  # Using ActivityLog as a fallback if Notification is missing
    
    query = db.query(Notification).filter(Notification.user_id == current.user_id)
    if unread_only:
        # Assuming ActivityLog or Notification has is_read
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
    # Placeholder for notification model
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
    """Get tokens/patient history - Returns all tokens (no doctor_id filter)"""
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"get_doctor_tokens - current.user_id: {current.user_id}, role: {current.role}")
    
    # Build query - NO doctor_id filter, return ALL tokens
    query = db.query(Token)
    
    # Optional: Filter by specific patient if provided
    if patient_id:
        query = query.filter(Token.patient_id == patient_id)
        logger.info(f"get_doctor_tokens - Filtered by patient_id: {patient_id}")
    
    # Optional status filter
    if status_filter:
        query = query.filter(Token.status == status_filter)
        logger.info(f"get_doctor_tokens - Applied status filter: {status_filter}")
    
    # Count total before pagination
    total = query.count()
    logger.info(f"get_doctor_tokens - Total tokens found: {total}")
    
    size = _parse_positive_int(page_size, 20)
    skip = (page - 1) * size
    
    # Order by appointment_date (most recent first)
    tokens = query.order_by(Token.appointment_date.desc()).offset(skip).limit(size).all()
    items = [{k: v for k, v in t.__dict__.items() if not k.startswith('_')} for t in tokens]
    
    return ok(
        data=items, 
        meta={
            "page": page, 
            "page_size": size, 
            "total": total
        }
    )


@router.get("/completed-consultations", dependencies=[Depends(require_roles("doctor", "admin"))])
async def get_completed_consultations(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=500),
):
    """Get completed tokens for the current doctor/admin with statistics."""
    # Find clinical doctor profile if applicable
    doctor = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    target_doctor_id = doctor.id if doctor else current.user_id
    
    # Base query for completed tokens
    base_query = db.query(Token).filter(
        Token.doctor_id == target_doctor_id,
        Token.status == "completed"
    )
    
    # Calculate statistics
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Total completed
    total_completed = base_query.count()
    
    # Completed today
    completed_today = base_query.filter(
        Token.completed_at >= today_start
    ).count() if hasattr(Token, 'completed_at') else base_query.filter(
        Token.updated_at >= today_start
    ).count()
    
    # Completed this month
    completed_this_month = base_query.filter(
        Token.completed_at >= month_start
    ).count() if hasattr(Token, 'completed_at') else base_query.filter(
        Token.updated_at >= month_start
    ).count()
    
    # Average consultation time (in minutes)
    avg_consultation_time = 0
    if hasattr(Token, 'started_at') and hasattr(Token, 'completed_at'):
        # Get tokens with both started_at and completed_at
        tokens_with_times = base_query.filter(
            Token.started_at.isnot(None),
            Token.completed_at.isnot(None)
        ).all()
        
        if tokens_with_times:
            total_minutes = 0
            count = 0
            for token in tokens_with_times:
                if token.started_at and token.completed_at:
                    duration = (token.completed_at - token.started_at).total_seconds() / 60
                    if duration > 0:  # Only count positive durations
                        total_minutes += duration
                        count += 1
            
            if count > 0:
                avg_consultation_time = round(total_minutes / count, 2)
    
    # Get paginated tokens
    total = base_query.count()
    size = _parse_positive_int(page_size, 20)
    skip = (page - 1) * size
    
    tokens = base_query.order_by(
        Token.completed_at.desc() if hasattr(Token, 'completed_at') else Token.updated_at.desc()
    ).offset(skip).limit(size).all()
    
    items = []
    for t in tokens:
      patient = db.query(User).filter(User.id == t.patient_id).first()  # ✅ User instead of Patient
      doctor_obj = db.query(Doctor).filter(Doctor.id == t.doctor_id).first()
    
      duration = None  # ✅ inside the loop now
      if t.started_at and t.completed_at:
        duration = round((t.completed_at - t.started_at).total_seconds() / 60, 2)
    
      items.append({  # ✅ inside the loop now
        "token_number": t.token_number,
        "mrn": patient.mrn if patient else None,
        "patient_name": patient.name if patient else None,
        "doctor_name": doctor_obj.name if doctor_obj else None,
        "department": doctor_obj.specialization if doctor_obj else None,
        "start_time": t.started_at,
        "end_time": t.completed_at,
        "duration": duration,
        "status": t.status,
    })

@router.get("/doctor/dashboard", dependencies=[Depends(require_roles("doctor", "patient", "admin"))])
async def doctor_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    upcoming_limit: int = Query(5, ge=0, le=50),
    skipped_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    # Try finding doctor by user_id first (newly created doctors)
    doctor = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    if not doctor:
        # Fallback to legacy check (where Doctor.id was used as user_id)
        doctor = db.query(Doctor).filter(Doctor.id == current.user_id).first()
    
    # Get user object for fallback name
    user = db.query(User).filter(User.id == current.user_id).first()
    user_name = user.name if user else "Doctor"
        
    # Determine doctor status safely
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

    # Today's tokens
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    # Query tokens where this doctor is assigned
    # If we found a clinical doctor profile, use doctor.id
    target_doctor_id = doctor.id if doctor else current.user_id
    
    todays = db.query(Token).filter(
        Token.doctor_id == target_doctor_id,
        Token.appointment_date >= today_start,
        Token.appointment_date < today_end
    ).all()

    completed_tokens = [t for t in todays if t.status == "completed"]
    skipped_tokens = [t for t in todays if t.status == "skipped"]
    
    # Active/Waiting tokens
    active_tokens = [t for t in todays if t.status in ("in_consultation", "pending", "confirmed", "waiting")]
    active_tokens.sort(key=lambda x: x.token_number)
    
    current_consult = next((t for t in active_tokens if t.status == "in_consultation"), None)
    
    curr_num = current_consult.token_number if current_consult else 0
    waiting_tokens = [t for t in active_tokens if t.status in ("pending", "confirmed", "waiting") and t.token_number > curr_num]

    def _patient_row(t: Token) -> Dict[str, Any]:
        # Calculate age from patient_age field or date_of_birth
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
            "mrn": t.mrn,
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
    # Basic stats
    doc_query = db.query(Doctor)
    if hospital_id:
        doc_query = doc_query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = doc_query.all()
    active_doctors = len([d for d in doctors if str(d.status).lower() in ("available", "active")])
    departments_count = db.query(func.count(func.distinct(Doctor.specialization))).scalar()

    # Today's tokens
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    token_query = db.query(Token).filter(Token.created_at >= today_start)
    if hospital_id:
        token_query = token_query.filter(Token.hospital_id == hospital_id)
    
    total_patients_today = token_query.count()

    # Wait time calculation (Average of started_at - created_at for today's tokens)
    wait_time_query = db.query(func.avg(
        func.extract('epoch', Token.started_at) - func.extract('epoch', Token.created_at)
    )).filter(
        Token.created_at >= today_start,
        Token.started_at.isnot(None)
    )
    if hospital_id:
        wait_time_query = wait_time_query.filter(Token.hospital_id == hospital_id)
    
    avg_wait_seconds = wait_time_query.scalar() or 0
    avg_wait_minutes = round(avg_wait_seconds / 60)

    # Patient Flow Today (Hourly)
    flow_today = []
    for hour in range(24):
        h_start = today_start + timedelta(hours=hour)
        h_end = h_start + timedelta(hours=1)
        count = db.query(Token).filter(
            Token.created_at >= h_start,
            Token.created_at < h_end
        ).count()
        flow_today.append({"hour": f"{hour:02d}:00", "count": count})

    # Patient Flow Monthly (Daily)
    flow_monthly = []
    # Get last 30 days
    for day in range(30):
        d_start = (now - timedelta(days=29-day)).replace(hour=0, minute=0, second=0, microsecond=0)
        d_end = d_start + timedelta(days=1)
        count = db.query(Token).filter(
            Token.created_at >= d_start,
            Token.created_at < d_end
        ).count()
        flow_monthly.append({"date": d_start.strftime("%d %b"), "count": count})

    # Logs
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
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    query = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.appointment_date >= today_start
    )
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)
    
    todays = query.all()
    
    waiting = [t for t in todays if t.status in ("pending", "confirmed")]
    completed = [t for t in todays if t.status == "completed"]
    skipped = [t for t in todays if t.status in ("skipped", "cancelled")]
    
    active = [t for t in todays if t.status in ("in_consultation", "pending", "confirmed", "called")]
    active.sort(key=lambda x: x.token_number)
    
    now_serving = next((t for t in active if t.status in ("in_consultation", "called")), active[0] if active else None)

    def _get_age_and_gender(patient_id, token_obj):
        # First try to get from token (walk-in tokens have this data)
        if token_obj:
            token_age = getattr(token_obj, 'patient_age', None)
            token_gender = getattr(token_obj, 'patient_gender', None)
            
            # If token has age, use it
            if token_age is not None:
                try:
                    age_val = int(token_age)
                    age = f"{age_val}y"
                except Exception:
                    age = "N/A"
            else:
                age = "N/A"
            
            # If token has gender, use it
            if token_gender:
                gender = str(token_gender).capitalize()
            else:
                gender = "Unknown"
            
            # Return token data if available
            if age != "N/A" or gender != "Unknown":
                return age, gender
        
        # Fallback to User table if token doesn't have the data
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

    upcoming = []
    for t in active:
        if now_serving and t.id == now_serving.id:
            continue
        age, gender = _get_age_and_gender(t.patient_id, t)
        
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
        if len(upcoming) >= upcoming_limit:
            break
            
    # Active Doctors for the hospital
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
                "avg_wait_minutes": (
                    sum((getattr(t, 'estimated_wait_time', 0) or 0) for t in active) // len([t for t in active if (getattr(t, 'estimated_wait_time', 0) or 0) > 0])
                ) if any((getattr(t, 'estimated_wait_time', 0) or 0) > 0 for t in active) else 0,
            }
        }
    )

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

    # Calculate dob from age if provided
    dob_str = None
    if age:
        try:
            years = int(age)
            dob_str = (datetime.utcnow() - timedelta(days=years*365)).strftime("%Y-%m-%d")
        except Exception:
            pass

    # Create or get patient user
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            name=patient_name,
            phone=phone,
            role="patient",
            password_hash="", # Dummy hash for walk-in patients to satisfy DB constraints
            date_of_birth=dob_str,
            gender=gender
        )
        db.add(user)
    else:
        # Update details if provided
        if dob_str and not user.date_of_birth:
            user.date_of_birth = dob_str
        if gender and not user.gender:
            user.gender = gender
        if patient_name and user.name != patient_name:
            user.name = patient_name

    db.commit()
    db.refresh(user)

    # Get Hospital Name
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    hospital_name_str = hospital.name if hospital else "Unknown Hospital"

    # Fetch/Generate MRN
    mrn = get_or_create_patient_mrn(db, user.id, hospital_id)

    # Calculate Fees
    doc_fee = float(doctor.consultation_fee or 0)
    token_fee = 50.0
    total_fee = doc_fee + token_fee

    # Allocation logic (Simplified)
    # TODO: Proper sequential allocation with locking
    last_token = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == datetime.utcnow().date()
    ).order_by(Token.token_number.desc()).first()
    
    next_num = (last_token.token_number + 1) if last_token else 1
    token_id = str(uuid.uuid4())
    
    # Format display code (e.g. A-001)
    doc_initial = doctor.name.strip()[0].upper() if doctor.name else "T"
    # Ensure it's alphabetical, if Dr. Ali, take "A". Replace "Dr" if it exists.
    if doctor.name and doctor.name.lower().startswith("dr"):
        clean_name = doctor.name[2:].replace(".", "").strip()
        doc_initial = clean_name[0].upper() if clean_name else "D"
        
    display_code = f"{doc_initial}-{next_num:03d}"
    
    # Track patients mathematically ahead in queue to assign estimated wait statically
    patients_ahead = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == datetime.utcnow().date(),
        Token.status.in_(["pending", "in_queue", "in_progress"])
    ).count()
    estimated_wait_time = max(0, patients_ahead * 15)
    
    # Calculate patient_age as integer from the age string or dob
    patient_age_int = None
    if age:
        try:
            patient_age_int = int(age)
        except Exception:
            pass
    elif user.date_of_birth:
        try:
            dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
            patient_age_int = (datetime.utcnow() - dob).days // 365
        except Exception:
            pass

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
    
    return ok(
        data={
            "token_id": token_id,
            "token_number": display_code,
            "hospital_name": hospital_name_str,
            "department": reason,
            "doctor_name": doctor.name,
            "patient_name": patient_name,
            "phone": phone,
            "mrn": mrn,
            "age": age,
            "gender": gender,
            "payment": "UNPAID",
            "status": "PENDING",
            "consultation_fee": doc_fee,
            "token_fee": token_fee,
            "total_fee": total_fee
        }, 
        message="Walk-in token created"
    )

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
    db.commit()
    
    return ok(message="Token skipped")


@router.post("/doctor/tokens/{token_id}/skip", dependencies=[Depends(require_roles("doctor", "admin"))])
async def doctor_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Skip a token from doctor portal"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Verify doctor owns this token
    doctor_profile = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    doctor_profile_id = doctor_profile.id if doctor_profile else None
    
    if str(current.user_id) != str(token.doctor_id) and str(doctor_profile_id) != str(token.doctor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only skip your own tokens"
        )
    
    # Check if token can be skipped
    st = str(token.status).lower()
    if st in ["completed", "cancelled", "skipped"]:
        raise HTTPException(
            status_code=400,
            detail=f"Token cannot be skipped. Current status: {st}"
        )
    
    now = datetime.utcnow()
    token.status = "skipped"
    token.updated_at = now
    
    db.commit()
    
    logger.info(f"Doctor {current.user_id} skipped token {token_id} via portal")
    
    # Auto-call next token
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
    """Update token details (receptionist can edit patient info, appointment time, status, etc.)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Prevent editing cancelled or completed tokens
    if token.status in ["cancelled", "completed"]:
        raise HTTPException(status_code=400, detail=f"Cannot edit token with status: {token.status}")
    
    # Special handling for status update (re-add skipped patient)
    if "status" in payload:
        new_status = str(payload["status"]).strip().lower()
        valid_statuses = ["pending", "waiting", "confirmed", "called", "skipped"]
        
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Allow re-adding skipped patients
        if token.status == "skipped" and new_status in ["waiting", "confirmed", "pending"]:
            token.status = new_status
            token.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Receptionist {current.user_id} re-added skipped token {token_id} with status: {new_status}")
            
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
        
        # For other status updates, just update if valid
        token.status = new_status
        token.updated_at = datetime.utcnow()
        db.commit()
        
        return ok(
            data={
                "token_id": token.id,
                "status": token.status
            },
            message="Token status updated successfully"
        )
    
    # Update allowed fields (if status is not being updated)
    updatable_fields = [
        "patient_name", "patient_phone", "patient_gender",
        "reason_for_visit", "appointment_date", "department"
    ]
    
    updated_fields = []
    for field in updatable_fields:
        if field in payload:
            setattr(token, field, payload[field])
            updated_fields.append(field)
    
    # Handle age to DOB conversion if age is provided
    if "patient_age" in payload:
        try:
            age_str = str(payload["patient_age"]).strip()
            # Remove 'y' suffix if present (e.g., "0y", "25y")
            if age_str.endswith('y'):
                age_str = age_str[:-1]
            
            age = int(age_str)
            # Update patient_age as integer
            token.patient_age = age
            if "patient_age" not in updated_fields:
                updated_fields.append("patient_age")
        except (ValueError, TypeError):
            # If age can't be parsed, skip it
            pass
    
    token.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(token)
    
    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "patient_name": token.patient_name,
            "patient_age": token.patient_age,
            "patient_gender": token.patient_gender,
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
    """Delete/cancel a token (receptionist can delete tokens)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Prevent deleting completed tokens
    if token.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot delete completed token")
    
    # If token is already cancelled, just confirm
    if token.status == "cancelled":
        return ok(message="Token is already cancelled")
    
    # Cancel the token
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

# -------------------- Utility --------------------
