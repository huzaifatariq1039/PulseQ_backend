from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from datetime import datetime

from app.security import require_roles, get_current_active_user
from app.models import TokenData
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token, ActivityLog
from app.utils.responses import ok
from app.services.token_service import SmartTokenService


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


def _status_val(token_obj: Token) -> str:
    raw = token_obj.status
    return str(getattr(raw, "value", raw) or "").lower()


def _visible_token(token_obj: Token) -> Optional[str]:
    if not token_obj:
        return None
    if hasattr(token_obj, 'display_code') and token_obj.display_code:
        return str(token_obj.display_code)
    try:
        return SmartTokenService.format_token(int(token_obj.token_number or 0))
    except Exception:
        return None


@router.get("/visit-history", dependencies=[Depends(require_roles("patient"))])
async def patient_visit_history(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    doctor_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None, description="Doctor specialization/department"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Patient Visit History from PostgreSQL"""
    query = db.query(Token).filter(Token.patient_id == current.user_id, Token.status == "completed")
    
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)
    if department:
        dep_norm = department.strip().lower()
        query = query.filter(func.lower(Token.doctor_specialization) == dep_norm) # Assuming field exists
        
    if from_date:
        query = query.filter(func.date(Token.appointment_date) >= datetime.fromisoformat(from_date).date())
    if to_date:
        query = query.filter(func.date(Token.appointment_date) <= datetime.fromisoformat(to_date).date())

    total = query.count()
    tokens = query.order_by(Token.appointment_date.desc()).offset((page-1)*page_size).limit(page_size).all()

    out: List[Dict[str, Any]] = []
    for t in tokens:
        out.append({
            "token_id": t.id,
            "token_number": _visible_token(t),
            "doctor_id": t.doctor_id,
            "doctor_name": t.doctor_name,
            "department": getattr(t, 'doctor_specialization', None),
            "start_time": t.started_at.isoformat() + "Z" if t.started_at else None,
            "end_time": t.completed_at.isoformat() + "Z" if t.completed_at else None,
            "duration_minutes": getattr(t, 'duration_minutes', None),
            "status": "completed",
        })

    return ok(
        data={"total_visits": total, "visits": out},
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/visit/{token_id}", dependencies=[Depends(require_roles("patient"))])
async def patient_visit_detail(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Patient Visit Detail from PostgreSQL"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    if str(token.patient_id) != str(current.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if _status_val(token) != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visit is not completed")

    payload = {
        "token_id": token.id,
        "token_number": _visible_token(token),
        "patient_id": token.patient_id,
        "doctor_id": token.doctor_id,
        "doctor_name": token.doctor_name,
        "department": getattr(token, 'doctor_specialization', None),
        "start_time": token.started_at.isoformat() + "Z" if token.started_at else None,
        "end_time": token.completed_at.isoformat() + "Z" if token.completed_at else None,
        "status": "completed",
        "consultation_notes": getattr(token, 'doctor_notes', None),
        "diagnosis": getattr(token, 'diagnosis', None),
        "prescription": getattr(token, 'prescription', []),
    }

    return ok(data=payload)
