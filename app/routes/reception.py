from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue
from app.models import TokenData, ReceptionistCreate, ReceptionistResponse
from app.security import get_current_active_user, require_roles, get_password_hash
from app.database import get_db
from app.services.token_service import SmartTokenService
from app.utils.responses import ok
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/receptionists", response_model=ReceptionistResponse, dependencies=[Depends(require_roles("admin"))])
async def create_receptionist(
    receptionist: ReceptionistCreate,
    db: Session = Depends(get_db)
):
    """Create a new receptionist user (Admin only).
    
    This creates a User record with the 'receptionist' role.
    """
    # 1. Check if user with this email already exists
    existing_user = db.query(User).filter(func.lower(User.email) == receptionist.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {receptionist.email} already exists"
        )
    
    # 2. Check if hospital exists
    hospital = db.query(Hospital).filter(Hospital.id == receptionist.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )

    # 3. Create User record for credentials
    user_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    new_user = User(
        id=user_id,
        name=receptionist.name,
        email=receptionist.email.lower(),
        phone=receptionist.phone,
        password_hash=get_password_hash(receptionist.password),
        role="receptionist",
        hospital_id=receptionist.hospital_id,
        created_at=now,
        updated_at=now
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Map to response
    return ReceptionistResponse(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        phone=new_user.phone,
        hospital_id=new_user.hospital_id,
        role=new_user.role,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at
    )


def _to_dt(v: Any) -> Optional[datetime]:
    try:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _infer_has_session(dept_text: str) -> bool:
    dt = (dept_text or "").lower()
    return any(kw in dt for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio"))


@router.get("/queue", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_queue(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(..., description="Hospital id managed by receptionist"),
    doctor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Receptionist Queue View from PostgreSQL"""
    today = datetime.utcnow().date()
    query = db.query(Token).filter(Token.hospital_id == hospital_id, func.date(Token.appointment_date) == today)
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)

    total = query.count()
    tokens = query.order_by(Token.token_number.asc()).offset((page-1)*page_size).limit(page_size).all()

    items: List[Dict[str, Any]] = []
    for t in tokens:
        doctor = db.query(Doctor).filter(Doctor.id == t.doctor_id).first()
        user = db.query(User).filter(User.id == t.patient_id).first()
        
        # Calculate Age and Gender
        age, gender = "0y", "Unknown"
        if user:
            gender = getattr(user, 'gender', "Unknown")
            if user.date_of_birth:
                try:
                    dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
                    age = f"{(datetime.utcnow() - dob).days // 365}y"
                except Exception:
                    pass
        
        department = getattr(t, 'doctor_specialization', None) or (doctor.specialization if doctor else "")
        dept_text = f"{department or ''}"
        inferred_has_session = _infer_has_session(dept_text)

        consultation_fee = getattr(t, 'consultation_fee', None) or (doctor.consultation_fee if doctor else 0.0)
        session_fee = getattr(t, 'session_fee', None) or (getattr(doctor, 'session_fee', None) if doctor else 0.0)

        # Force total_fee to use the Token's actual saved total_fee which includes the Token fee of 50
        total_fee = getattr(t, 'total_fee', None) 
        if total_fee is None:
            total_fee = (consultation_fee or 0) + (session_fee or 0 if inferred_has_session else 0)

        items.append({
            "token_id": t.id,
            "token_number": t.display_code or str(t.token_number),
            "mrn": t.mrn,
            "patient_name": t.patient_name,
            "patient_age": age,
            "patient_gender": gender,
            "doctor_name": t.doctor_name,
            "department": department,
            "reason": getattr(t, 'department', None) or "",
            "consultation_fee": consultation_fee,
            "session_fee": session_fee if inferred_has_session else None,
            "total_fee": total_fee,
            "status": str(t.status).lower()
        })

    return ok(
        data=items,
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/tokens", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_tokens(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Receptionist view of slot bookings from PostgreSQL"""
    query = db.query(Token).filter(Token.hospital_id == hospital_id)
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)

    total = query.count()
    tokens = query.order_by(Token.appointment_date.desc()).offset((page-1)*page_size).limit(page_size).all()

    items: List[Dict[str, Any]] = []
    for t in tokens:
        items.append({
            "token_id": t.id,
            "doctor_id": t.doctor_id,
            "doctor_name": t.doctor_name,
            "patient_name": t.patient_name,
            "appointment_date": t.appointment_date.isoformat() if t.appointment_date else None,
            "status": str(t.status).lower(),
        })

    return ok(data=items, meta={"page": page, "page_size": page_size, "total": total})
