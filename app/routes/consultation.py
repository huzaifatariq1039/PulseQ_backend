from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

from app.security import get_current_active_user
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token, ActivityLog
from app.security import require_roles
from app.utils.responses import ok
from app.utils.audit import get_user_role, log_action
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES


router = APIRouter()


def _to_dt(v: Any) -> Optional[datetime]:
    try:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        to_dt = getattr(v, "to_datetime", None)
        if callable(to_dt):
            return to_dt()
        return datetime.fromisoformat(str(v))
    except Exception:
        return None


def _is_empty(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def _auto_skip_called_tokens(db: Session, hospital_id: Optional[str] = None, doctor_id: Optional[str] = None) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=3)
    
    query = db.query(Token).filter(Token.status == "called", Token.called_at <= cutoff)
    if hospital_id:
        query = query.filter(Token.hospital_id == hospital_id)
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)
        
    called_tokens = query.all()
    updated = 0
    for t in called_tokens:
        t.status = "skipped"
        t.skipped_at = now
        t.updated_at = now
        updated += 1
    
    if updated > 0:
        db.commit()
        
    return updated


@router.get("/doctor/current-patient/{doctor_id}", dependencies=[Depends(require_roles("doctor", "admin", "patient"))])
async def doctor_current_patient(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
        
    if role not in ("admin", "patient") and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _auto_skip_called_tokens(db, hospital_id=hospital_id, doctor_id=doctor_id)

    today = datetime.utcnow().date()
    query = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "called",
        func.date(Token.appointment_date) == today
    )
    if hospital_id:
        query = query.filter(Token.hospital_id == hospital_id)

    token = query.order_by(Token.token_number.asc()).first()
    token_data = {k: v for k, v in token.__dict__.items() if not k.startswith('_')} if token else None
    
    return ok(data={"token": token_data})


@router.post("/start", dependencies=[Depends(require_roles("doctor", "admin", "patient"))])
async def consultation_start(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
) -> Dict[str, Any]:
    token_id = str((payload or {}).get("token_id") or "").strip()
    doctor_id = str((payload or {}).get("doctor_id") or "").strip()
    
    if not token_id or not doctor_id:
        missing = []
        if not token_id:
            missing.append("token_id")
        if not doctor_id:
            missing.append("doctor_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Missing required fields: {', '.join(missing)}. Please provide both token_id and doctor_id in the request body."
        )

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
        
    if role not in ("admin", "patient") and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _auto_skip_called_tokens(db, doctor_id=doctor_id)

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        
    dstatus = str(doctor.status).lower()
    # Assuming these fields exist in Doctor model
    queue_paused = getattr(doctor, "queue_paused", False) or getattr(doctor, "paused", False)
    
    if dstatus in {"offline", "on_leave"} or queue_paused:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    if dstatus == "busy":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor busy")

    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if str(token.doctor_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not assigned to this doctor")

    st = str(token.status).lower()
    if st in ("completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token already completed")

    if st not in ("called", "pending", "waiting", "confirmed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token cannot be started from current status")

    now = datetime.utcnow()
    token.status = "in_consultation"
    token.updated_at = now
    
    # Safely set attributes if they exist in the model
    for attr in ["start_time", "started_at"]:
        if hasattr(token, attr):
            setattr(token, attr, now)
    
    doctor.status = "busy"
    doctor.updated_at = now
    
    db.commit()

    try:
        log_action(current_user.user_id, role, action="START", token_id=token_id)
    except Exception:
        pass

    return ok(data={"token_id": token_id, "doctor_id": doctor_id, "status": "in_consultation"}, message="Consultation started")


@router.post("/end", dependencies=[Depends(require_roles("doctor", "admin", "patient"))])
async def consultation_end(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
) -> Dict[str, Any]:
    token_id = str((payload or {}).get("token_id") or "").strip()
    doctor_id = str((payload or {}).get("doctor_id") or "").strip()
    
    if not token_id or not doctor_id:
        missing = []
        if not token_id:
            missing.append("token_id")
        if not doctor_id:
            missing.append("doctor_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Missing required fields: {', '.join(missing)}. Please provide both token_id and doctor_id in the request body."
        )

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
        
    if role not in ("admin", "patient") and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if str(token.doctor_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not assigned to this doctor")

    st = str(token.status).lower()
    if st == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token already completed")
    if st != "in_consultation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not in consultation")

    now = datetime.utcnow()
    token.status = "completed"
    token.updated_at = now
    
    # Safely set attributes if they exist in the model
    for attr in ["completed_at", "end_time"]:
        if hasattr(token, attr):
            setattr(token, attr, now)
    
    doctor.status = "available"
    doctor.updated_at = now
    
    db.commit()

    # Auto-call next token logic
    today = now.date()
    next_token_obj = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed"]),
        func.date(Token.appointment_date) == today,
        Token.token_number > token.token_number
    ).order_by(Token.token_number.asc()).first()

    next_token_data = None
    if next_token_obj:
        next_token_obj.status = "called"
        next_token_obj.updated_at = now
        
        # Safely set attributes if they exist in the model
        if hasattr(next_token_obj, "called_at"):
            setattr(next_token_obj, "called_at", now)
        
        db.commit()
        next_token_data = {k: v for k, v in next_token_obj.__dict__.items() if not k.startswith('_')}

    try:
        log_action(current_user.user_id, role, action="DONE", token_id=token_id)
    except Exception:
        pass

    return ok(
        data={
            "token_id": token_id,
            "doctor_id": doctor_id,
            "status": "completed",
            "next_called_token": next_token_data,
        },
        message="Consultation completed",
    )
