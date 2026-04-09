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

router = APIRouter(prefix="/portal", tags=["Portal (Role-Protected)"])

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

    return {"success": True, "data": items, "meta": {"unread_only": unread_only, "count": len(items)}}


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
        
    return {"success": True}


@router.get("/doctor/tokens", dependencies=[Depends(require_roles("doctor"))])
async def get_doctor_tokens(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    query = db.query(Token).filter(Token.doctor_id == current.user_id)
    if status_filter:
        query = query.filter(Token.status == status_filter)
    
    total = query.count()
    size = _parse_positive_int(page_size, 20)
    skip = (page - 1) * size
    
    tokens = query.order_by(Token.created_at.desc()).offset(skip).limit(size).all()
    items = [{k: v for k, v in t.__dict__.items() if not k.startswith('_')} for t in tokens]
    
    return {"success": True, "data": items, "meta": {"page": page, "page_size": size, "total": total}}


@router.get("/doctor/dashboard", dependencies=[Depends(require_roles("doctor"))])
async def doctor_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    upcoming_limit: int = Query(5, ge=0, le=50),
    skipped_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    doctor = db.query(Doctor).filter(Doctor.id == current.user_id).first()
    if not doctor:
        # Try fallback user_id if needed
        # doctor = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
        pass
        
    doctor_header = {
        "id": doctor.id if doctor else current.user_id,
        "name": doctor.name if doctor else current.name,
        "department": doctor.specialization if doctor else None,
        "room": getattr(doctor, "room", None) if doctor else None,
        "status": doctor.status.value if doctor and hasattr(doctor.status, 'value') else str(getattr(doctor, 'status', '')).lower(),
    }

    # Today's tokens
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    todays = db.query(Token).filter(
        Token.doctor_id == current.user_id,
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
        return {
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "mrn": t.mrn,
            "patient_name": t.patient_name,
            "phone": getattr(t, 'patient_phone', None), # Assuming fields exist in Token model or joined User
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


@router.get("/admin/dashboard", dependencies=[Depends(require_roles("admin"))])
async def admin_dashboard(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None),
    logs_limit: int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    # Basic stats
    doc_query = db.query(Doctor)
    if hospital_id:
        doc_query = doc_query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = doc_query.all()
    active_doctors = len([d for d in doctors if str(d.status).lower() in ("available", "active")])
    departments_count = db.query(func.count(func.distinct(Doctor.specialization))).scalar()

    # Today's tokens
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    token_query = db.query(Token).filter(Token.created_at >= today_start)
    if hospital_id:
        token_query = token_query.filter(Token.hospital_id == hospital_id)
    
    total_patients_today = token_query.count()

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
                "avg_wait_time_minutes": 0, # TODO: Implement wait time logic
                "departments": departments_count,
            },
            "patient_flow_today": [], # TODO: Implement flow buckets
            "patient_flow_monthly": [],
            "live_system_logs": logs,
        }
    )


@router.get("/receptionist/dashboard", dependencies=[Depends(require_roles("receptionist"))])
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
    skipped = [t for t in todays if t.status == "skipped"]
    
    active = [t for t in todays if t.status in ("in_consultation", "pending", "confirmed")]
    active.sort(key=lambda x: x.token_number)
    
    now_serving = next((t for t in active if t.status == "in_consultation"), active[0] if active else None)

    upcoming = []
    for t in active:
        if now_serving and t.id == now_serving.id:
            continue
        upcoming.append({
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "patient_name": t.patient_name,
            "status": str(t.status).lower(),
            "doctor_name": t.doctor_name,
        })
        if len(upcoming) >= upcoming_limit:
            break

    return ok(
        data={
            "now_serving": {
                "token_id": now_serving.id,
                "token_number": now_serving.display_code or str(now_serving.token_number),
                "patient_name": now_serving.patient_name,
                "doctor_name": now_serving.doctor_name,
            } if now_serving else None,
            "upcoming_queue": upcoming,
            "cards": {
                "waiting": len(waiting),
                "completed": len(completed),
                "skipped": len(skipped),
                "avg_wait_minutes": len(waiting) * 9,
            }
        }
    )

@router.post("/receptionist/walkin-token", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_create_walkin_token(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    hospital_id = payload.get("hospital_id")
    doctor_id = payload.get("doctor_id")
    patient_name = payload.get("patient_name")
    phone = payload.get("phone")
    
    if not all([hospital_id, doctor_id, patient_name, phone]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Create or get patient user
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            name=patient_name,
            phone=phone,
            role="patient"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Allocation logic (Simplified)
    # TODO: Proper sequential allocation with locking
    last_token = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == datetime.utcnow().date()
    ).order_by(Token.token_number.desc()).first()
    
    next_num = (last_token.token_number + 1) if last_token else 1
    token_id = str(uuid.uuid4())
    
    new_token = Token(
        id=token_id,
        patient_id=user.id,
        doctor_id=doctor_id,
        hospital_id=hospital_id,
        token_number=next_num,
        hex_code=token_id[:8],
        appointment_date=datetime.utcnow(),
        status="pending",
        is_walk_in=True,
        patient_name=patient_name,
        doctor_name=doctor.name,
        hospital_name="Hospital" # TODO: Fetch hospital name
    )
    
    db.add(new_token)
    db.commit()
    
    return ok(data={"token_id": token_id}, message="Walk-in token created")

@router.post("/receptionist/tokens/{token_id}/skip", dependencies=[Depends(require_roles("receptionist"))])
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

# -------------------- Utility --------------------
import uuid
