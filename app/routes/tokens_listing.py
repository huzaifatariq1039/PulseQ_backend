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
    
    # Map objects explicitly to avoid __dict__ issues after db.refresh() or similar
    page_items = []
    for t in tokens_objs:
        status_val = str(t.status.value if hasattr(t.status, 'value') else t.status).lower()
        pay_status_val = str(t.payment_status.value if hasattr(t.payment_status, 'value') else t.payment_status).lower()
        
        page_items.append({
            "id": str(t.id),
            "patient_id": str(t.patient_id),
            "doctor_id": str(t.doctor_id),
            "hospital_id": str(t.hospital_id),
            "mrn": t.mrn,
            "token_number": t.token_number,
            "hex_code": t.hex_code,
            "display_code": t.display_code,
            "appointment_date": t.appointment_date,
            "status": status_val,
            "payment_status": pay_status_val,
            "payment_method": t.payment_method,
            "queue_position": t.queue_position,
            "total_queue": t.total_queue,
            "estimated_wait_time": t.estimated_wait_time,
            "consultation_fee": t.consultation_fee,
            "session_fee": t.session_fee,
            "total_fee": t.total_fee,
            "department": t.department,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "is_active": status_val not in ["cancelled", "completed"],
            "doctor_name": t.doctor_name,
            "doctor_specialization": t.doctor_specialization,
            "doctor_avatar_initials": t.doctor_avatar_initials,
            "hospital_name": t.hospital_name,
            "patient_name": t.patient_name,
            "patient_phone": t.patient_phone,
            "queue_opt_in": bool(t.queue_opt_in),
            "queue_opted_in_at": t.queue_opted_in_at,
            "confirmed": bool(t.confirmed),
            "confirmation_status": t.confirmation_status,
            "confirmed_at": t.confirmed_at,
            "cancelled_at": t.cancelled_at
        })

    return ok(
        data=page_items,
        meta={"page": page, "limit": limit, "total": total},
        message="Tokens fetched successfully",
    )
