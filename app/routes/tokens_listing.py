from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query
from app.security import get_current_active_user
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token
from app.utils.responses import ok

router = APIRouter(prefix="/tokens", tags=["SmartTokens (Listing)"])


_STATUS_ALIASES = {
    "waiting": "pending",
    "inprogress": "in_progress",
    "in-progress": "in_progress",
}


def _norm_status(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    k = str(s).strip().lower()
    return _STATUS_ALIASES.get(k, k)


@router.get("", summary="List tokens with pagination and filters")
async def list_tokens(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
    status: Optional[str] = Query(None, description="Filter by token status (e.g., waiting, confirmed, in_progress)"),
    department: Optional[str] = Query(None, description="Doctor department/specialization"),
    doctor_id: Optional[str] = Query(None, alias="doctorId", description="Filter by doctor id"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Dict[str, Any]:
    """List tokens with pagination and filters from PostgreSQL"""
    query = db.query(Token)

    # Role-based filtering: Patients only see their own tokens
    from app.utils.audit import get_user_role
    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = "patient"

    if role == "patient":
        query = query.filter(Token.patient_id == current_user.user_id)
    elif role == "doctor":
        query = query.filter(Token.doctor_id == current_user.user_id)
    # Admin and Receptionist can see all (or filtered by doctor_id/status)

    norm_status = _norm_status(status)
    if norm_status:
        query = query.filter(Token.status == norm_status)
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)

    if department:
        # Join with Doctor to filter by specialization
        query = query.join(Doctor, Token.doctor_id == Doctor.id).filter(
            func.lower(Doctor.specialization) == department.strip().lower()
        )

    total = query.count()
    offset = (page - 1) * limit
    tokens_objs = query.order_by(Token.created_at.desc()).offset(offset).limit(limit).all()
    
    page_items = [{k: v for k, v in t.__dict__.items() if not k.startswith('_')} for t in tokens_objs]

    return ok(
        data=page_items,
        meta={"page": page, "limit": limit, "total": total},
        message="Tokens fetched successfully",
    )
