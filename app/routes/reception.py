from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue

from app.security import get_current_active_user
from app.database import get_db
from app.models import TokenData
from app.security import require_roles
from app.services.token_service import SmartTokenService
from app.utils.responses import ok


router = APIRouter(prefix="/reception", tags=["Reception (Queue Fees)"])


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
        
        department = getattr(t, 'doctor_specialization', None) or (doctor.specialization if doctor else "")
        dept_text = f"{department or ''}"
        inferred_has_session = _infer_has_session(dept_text)

        consultation_fee = getattr(t, 'consultation_fee', None) or (doctor.consultation_fee if doctor else None)
        session_fee = getattr(t, 'session_fee', None) or (getattr(doctor, 'session_fee', None) if doctor else None)

        total_fee = (consultation_fee or 0) + (session_fee or 0 if inferred_has_session else 0)

        items.append({
            "token_id": t.id,
            "token_number": t.token_number,
            "patient_name": t.patient_name,
            "doctor_name": t.doctor_name,
            "department": department,
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
