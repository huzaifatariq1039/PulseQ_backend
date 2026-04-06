from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from datetime import datetime

from app.security import require_roles, get_current_active_user
from app.models import TokenData
from app.config import COLLECTIONS
from app.database import get_db
from app.utils.responses import ok
from app.services.token_service import SmartTokenService


router = APIRouter(prefix="/patient", tags=["Patient"])


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


def _status_val(token: Dict[str, Any]) -> str:
    raw = (token or {}).get("status")
    return str(getattr(raw, "value", raw) or "").lower()


def _visible_token(token: Dict[str, Any]) -> Optional[str]:
    if not token:
        return None
    for k in ("display_code", "displayCode"):
        if token.get(k):
            return str(token.get(k))
    try:
        return SmartTokenService.format_token(int(token.get("token_number") or 0))
    except Exception:
        return None


@router.get("/visit-history", dependencies=[Depends(require_roles("patient"))])
async def patient_visit_history(
    current: TokenData = Depends(get_current_active_user),
    doctor_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None, description="Doctor specialization/department"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD (filter by end_time date >= from_date)"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD (filter by end_time date <= to_date)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Patient Visit History

    Returns only completed consultations for the logged-in patient, newest first.
    """
    db = get_db()

    ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", current.user_id)
    docs = [d.to_dict() for d in ref.limit(8000).stream()]

    # Filter in-memory to avoid Firestore composite index requirements
    items: List[Dict[str, Any]] = []
    dep_norm = str(department or "").strip().lower()

    def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
        try:
            if not s:
                return None
            return datetime.fromisoformat(str(s)).date()
        except Exception:
            return None

    fd = _parse_date(from_date)
    td = _parse_date(to_date)

    for t in docs:
        if _status_val(t) != "completed":
            continue
        if doctor_id and str(t.get("doctor_id") or "") != str(doctor_id):
            continue
        if dep_norm:
            dep_val = str(t.get("department") or t.get("doctor_specialization") or "").strip().lower()
            if dep_val != dep_norm:
                continue

        end_dt = _to_dt(t.get("end_time") or t.get("completed_at") or t.get("appointment_date"))
        if end_dt is not None:
            d = end_dt.date()
            if fd and d < fd:
                continue
            if td and d > td:
                continue

        items.append(t)

    items.sort(
        key=lambda x: _to_dt(x.get("end_time") or x.get("completed_at") or x.get("appointment_date")) or datetime.min,
        reverse=True,
    )

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    out: List[Dict[str, Any]] = []
    for t in page_items:
        st = _to_dt(t.get("start_time"))
        et = _to_dt(t.get("end_time") or t.get("completed_at"))
        out.append(
            {
                "token_id": t.get("id"),
                "token_number": _visible_token(t),
                "doctor_id": t.get("doctor_id"),
                "doctor_name": t.get("doctor_name"),
                "department": t.get("department") or t.get("doctor_specialization"),
                "start_time": st.isoformat() + "Z" if st else None,
                "end_time": et.isoformat() + "Z" if et else None,
                "duration_minutes": t.get("duration") or t.get("duration_minutes"),
                "status": "completed",
            }
        )

    return ok(
        data={"total_visits": total, "visits": out},
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/visit/{token_id}", dependencies=[Depends(require_roles("patient"))])
async def patient_visit_detail(
    token_id: str,
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Patient Visit Detail

    Returns full consultation details for a completed visit. Enforces strict ownership.
    """
    db = get_db()
    snap = db.collection(COLLECTIONS["TOKENS"]).document(token_id).get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    t = snap.to_dict() or {}

    if str(t.get("patient_id") or "") != str(current.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if _status_val(t) != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visit is not completed")

    st = _to_dt(t.get("start_time"))
    et = _to_dt(t.get("end_time") or t.get("completed_at"))

    # Normalize prescription structure
    prescription = t.get("prescription") or t.get("medications") or []
    if prescription is None:
        prescription = []

    payload = {
        "token_id": t.get("id") or token_id,
        "token_number": _visible_token(t),
        "patient_id": t.get("patient_id"),
        "doctor_id": t.get("doctor_id"),
        "doctor_name": t.get("doctor_name"),
        "department": t.get("department") or t.get("doctor_specialization"),
        "start_time": st.isoformat() + "Z" if st else None,
        "end_time": et.isoformat() + "Z" if et else None,
        "duration_minutes": t.get("duration") or t.get("duration_minutes"),
        "status": "completed",
        "consultation_notes": t.get("consultation_notes") or t.get("notes") or t.get("doctor_notes"),
        "diagnosis": t.get("diagnosis"),
        "prescription": prescription,
        "medical_records_url": t.get("medical_records_url") or t.get("records_url"),
        "lab_reports": t.get("lab_reports") or t.get("lab_reports_url") or t.get("lab_reports_urls"),
        "uploaded_files": t.get("uploaded_files") or t.get("attachments"),
        "raw": t,
    }

    return ok(data=payload)
