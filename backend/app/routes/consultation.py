from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import logging

from app.security import get_current_active_user
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db_models import User, Doctor, Hospital, Token, ActivityLog
from app.security import require_roles
from app.utils.responses import ok
from app.utils.audit import get_user_role, log_action
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES
from app.utils.date_utils import to_dt, is_empty
from app.models import TokenData


router = APIRouter()

logger = logging.getLogger(__name__)


# Use centralized helpers from app.utils.date_utils


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
    # Get role from current_user JWT token (already validated by require_roles)
    role = str(current_user.role or "").lower()
    
    # Allow admin and patient roles without restriction
    # For doctor role, verify they're accessing their own consultations
    if role == "admin" or role == "patient":
        # Admins and patients can access any consultation
        pass
    elif role == "doctor":
        # Doctors can only start/end their own consultations
        # Check if the doctor_id in payload matches their user_id OR their doctor profile id
        doctor_profile = db.query(Doctor).filter(Doctor.user_id == current_user.user_id).first()
        doctor_profile_id = doctor_profile.id if doctor_profile else None
        
        if str(current_user.user_id) != str(doctor_id) and str(doctor_profile_id) != str(doctor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Access denied: You can only access your own consultations"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied: Invalid role '{role}'. Required: doctor, admin, or patient"
        )

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

    # Get role from current_user JWT token (already validated by require_roles)
    role = str(current_user.role or "").lower()
    
    # Allow admin and patient roles without restriction
    # For doctor role, verify they're accessing their own consultations
    if role == "admin" or role == "patient":
        # Admins and patients can access any consultation
        pass
    elif role == "doctor":
        # Doctors can only start/end their own consultations
        # Check if the doctor_id in payload matches their user_id OR their doctor profile id
        doctor_profile = db.query(Doctor).filter(Doctor.user_id == current_user.user_id).first()
        doctor_profile_id = doctor_profile.id if doctor_profile else None
        
        if str(current_user.user_id) != str(doctor_id) and str(doctor_profile_id) != str(doctor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Access denied: You can only access your own consultations"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied: Invalid role '{role}'. Required: doctor, admin, or patient"
        )

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
    consultation_notes = (payload or {}).get("consultation_notes")
    if consultation_notes is not None:
        consultation_notes = str(consultation_notes).strip()

    
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

    # Get role from current_user JWT token (already validated by require_roles)
    role = str(current_user.role or "").lower()
    
    # Allow admin and patient roles without restriction
    # For doctor role, verify they're accessing their own consultations
    if role == "admin" or role == "patient":
        # Admins and patients can access any consultation
        pass
    elif role == "doctor":
        # Doctors can only start/end their own consultations
        # Check if the doctor_id in payload matches their user_id OR their doctor profile id
        doctor_profile = db.query(Doctor).filter(Doctor.user_id == current_user.user_id).first()
        doctor_profile_id = doctor_profile.id if doctor_profile else None
        
        if str(current_user.user_id) != str(doctor_id) and str(doctor_profile_id) != str(doctor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Access denied: You can only access your own consultations"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Access denied: Invalid role '{role}'. Required: doctor, admin, or patient"
        )

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

    if consultation_notes is not None:
        token.consultation_notes = consultation_notes
    
    # Safely set attributes if they exist in the model
    for attr in ["completed_at", "end_time"]:
        if hasattr(token, attr):
            setattr(token, attr, now)
    
    doctor.status = "available"
    doctor.updated_at = now
    
    db.commit()

    # Send WhatsApp thank you message after consultation completion
    if token.patient_phone:
        try:
            from app.services.whatsapp_service import send_template_message
            await send_template_message(
                phone=token.patient_phone,
                template_name="template",  # Thank you template
                params=[]
            )
            logger.info(f"WhatsApp thank you message sent to {token.patient_phone} for completed token {token_id}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp thank you message for token {token_id}: {e}")

    # Auto-call next token logic
    today = now.date()
    next_token_data = None
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


@router.post("/skip/{token_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def consultation_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Skip a token from consultation or queue (doctor only)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    # Get role from current_user JWT token
    role = str(current_user.role or "").lower()
    
    # For doctor role, verify they're accessing their own consultations
    if role == "doctor":
        doctor_profile = db.query(Doctor).filter(Doctor.user_id == current_user.user_id).first()
        doctor_profile_id = doctor_profile.id if doctor_profile else None
        
        if str(current_user.user_id) != str(token.doctor_id) and str(doctor_profile_id) != str(token.doctor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Access denied: You can only skip your own tokens"
            )

    # Check if token can be skipped
    st = str(token.status).lower()
    if st in ["completed", "cancelled", "skipped"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Token cannot be skipped. Current status: {st}"
        )

    now = datetime.utcnow()
    token.status = "skipped"
    token.skipped_at = now if hasattr(token, "skipped_at") else None
    token.updated_at = now
    
    db.commit()

    try:
        log_action(current_user.user_id, role, action="SKIP", token_id=token_id)
    except Exception:
        pass

    logger.info(f"Doctor {current_user.user_id} skipped token {token_id}")

    # Auto-call next token logic
    doctor_id = token.doctor_id
    today = now.date()
    next_token_obj = db.query(Token).filter(
    Token.doctor_id == doctor_id,
    Token.status.in_(["pending", "waiting", "confirmed"]),
    func.date(Token.appointment_date) == today,
    Token.token_number > token.token_number
    ).order_by(Token.token_number.asc()).first()
    
    next_token_data = None 
    if next_token_obj:
       next_token_data = {k: v for k, v in next_token_obj.__dict__.items() if not k.startswith('_')}

    return ok(
        data={
            "token_id": token_id,
            "doctor_id": doctor_id,
            "status": "skipped",
            "next_called_token": next_token_data,
        },
        message="Token skipped successfully",
    )

@router.post("/re-add/{token_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def re_add_skipped_patient(
    token_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Re-add a skipped patient back to the queue"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    # For doctor role, verify they own this token
    role = str(current_user.role or "").lower()
    if role == "doctor":
        doctor_profile = db.query(Doctor).filter(Doctor.user_id == current_user.user_id).first()
        doctor_profile_id = doctor_profile.id if doctor_profile else None

        if str(current_user.user_id) != str(token.doctor_id) and str(doctor_profile_id) != str(token.doctor_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only re-add your own tokens"
            )

    if token.status != "skipped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token is not skipped. Current status: {token.status}"
        )

    now = datetime.utcnow()
    token.status = "pending"
    token.updated_at = now
    db.commit()
    db.refresh(token)

    logger.info(f"User {current_user.user_id} re-added skipped token {token_id}")

    try:
        log_action(current_user.user_id, role, action="RE_ADD", token_id=token_id)
    except Exception:
        pass

    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "patient_name": token.patient_name,
            "status": token.status,
            "previous_status": "skipped"
        },
        message="Patient re-added to queue successfully"
    )

@router.get("/patient/{patient_id}/history", dependencies=[Depends(require_roles("doctor", "receptionist", "admin"))])
async def get_patient_consultation_history(
    patient_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Get full consultation history for a specific patient"""

    # ✅ Verify patient exists
    patient = db.query(User).filter(User.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    query = db.query(Token).filter(Token.patient_id == patient_id)

    # ✅ Doctor can only see their own patients
    role = str(getattr(current, "role", "")).lower()
    if role == "doctor":
        doctor = db.query(Doctor).filter(
            or_(
                Doctor.user_id == current.user_id,
                Doctor.id == current.user_id
            )
        ).first()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor profile not found")
        query = query.filter(Token.doctor_id == doctor.id)

    total = query.count()
    skip = (page - 1) * page_size
    tokens = query.order_by(Token.appointment_date.desc()).offset(skip).limit(page_size).all()

    # ✅ Batch fetch doctors to avoid N+1
    doctor_ids = list({t.doctor_id for t in tokens if t.doctor_id})
    doctors_map = {
        d.id: d for d in db.query(Doctor).filter(Doctor.id.in_(doctor_ids)).all()
    }

    items = []
    for t in tokens:
        doctor_obj = doctors_map.get(t.doctor_id)
        start = t.started_at or t.created_at
        end = t.completed_at or t.updated_at
        duration = 0
        if start and end and end > start:
            duration = round((end - start).total_seconds() / 60)

        items.append({
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "mrn": getattr(t, "mrn", None) or "N/A",
            "appointment_date": t.appointment_date,
            "status": str(t.status).lower(),
            "department": t.department or (doctor_obj.specialization if doctor_obj else "General"),
            "doctor_name": t.doctor_name or (doctor_obj.name if doctor_obj else "Unknown"),
            "doctor_id": t.doctor_id,
            "reason_for_visit": t.reason_for_visit or "",
            "consultation_notes": t.consultation_notes or "",
            "patient_age": t.patient_age,
            "patient_gender": t.patient_gender,
            "payment_status": str(t.payment_status or "pending").lower(),
            "consultation_fee": t.consultation_fee,
            "total_fee": t.total_fee,
            "started_at": start,
            "completed_at": end,
            "duration_minutes": duration,
        })

    return ok(
        data={
            "patient": {
                "id": patient.id,
                "name": patient.name,
                "phone": patient.phone,
                "email": getattr(patient, "email", None),
                "date_of_birth": getattr(patient, "date_of_birth", None),
                "gender": getattr(patient, "gender", None),
            },
            "history": items,
        },
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    )