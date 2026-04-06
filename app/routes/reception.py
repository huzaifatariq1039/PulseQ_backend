from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.security import get_current_active_user
from app.database import get_db
from app.config import COLLECTIONS
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
        to_dt = getattr(v, "to_datetime", None)
        if callable(to_dt):
            return to_dt()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _infer_has_session(dept_text: str) -> bool:
    dt = (dept_text or "").lower()
    return any(kw in dt for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio"))


@router.get("/queue", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_queue(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(..., description="Hospital id managed by receptionist"),
    doctor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    GET /api/reception/queue
    Returns patient, doctor, department, and fee breakdown for today's tokens.
    """
    db = get_db()
    today = datetime.utcnow().date()

    ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)
    if doctor_id:
        ref = ref.where("doctor_id", "==", doctor_id)

    docs = [d.to_dict() for d in ref.limit(5000).stream()]

    # Simple cache to avoid repeated reads
    doctor_cache: Dict[str, Dict[str, Any]] = {}
    user_cache: Dict[str, Dict[str, Any]] = {}

    def get_doctor_meta(did: Optional[str]) -> Dict[str, Any]:
        if not did:
            return {}
        did = str(did)
        if did in doctor_cache:
            return doctor_cache[did]
        try:
            snap = db.collection(COLLECTIONS["DOCTORS"]).document(did).get()
            doctor_cache[did] = snap.to_dict() if getattr(snap, "exists", False) else {}
        except Exception:
            doctor_cache[did] = {}
        return doctor_cache[did]

    def get_user(uid: Optional[str]) -> Dict[str, Any]:
        if not uid:
            return {}
        uid = str(uid)
        if uid in user_cache:
            return user_cache[uid]
        try:
            snap = db.collection(COLLECTIONS["USERS"]).document(uid).get()
            user_cache[uid] = snap.to_dict() if getattr(snap, "exists", False) else {}
        except Exception:
            user_cache[uid] = {}
        return user_cache[uid]

    items: List[Dict[str, Any]] = []
    for t in docs:
        appt = _to_dt(t.get("appointment_date"))
        if not appt or appt.date() != today:
            continue

        token_id = t.get("id") or t.get("token_id")
        token_number = t.get("token_number")

        pid = t.get("patient_id")
        u = get_user(pid)
        patient_name = t.get("patient_name") or u.get("name")
        patient_phone = t.get("patient_phone") or u.get("phone")

        did = t.get("doctor_id")
        dmeta = get_doctor_meta(did)

        department = (
            t.get("doctor_specialization")
            or t.get("department")
            or t.get("specialization")
            or dmeta.get("specialization")
            or dmeta.get("department")
        )
        dept_text = f"{dmeta.get('specialization') or ''} {dmeta.get('subcategory') or ''} {dmeta.get('department') or ''} {department or ''}"
        inferred_has_session = _infer_has_session(dept_text)

        consultation_fee = t.get("consultation_fee") or dmeta.get("consultation_fee")
        session_fee = t.get("session_fee") if inferred_has_session else None
        if session_fee is None and inferred_has_session:
            session_fee = dmeta.get("session_fee")

        # Normalize numeric values
        try:
            consultation_fee = float(consultation_fee) if consultation_fee is not None else None
        except Exception:
            consultation_fee = None
        try:
            session_fee = float(session_fee) if session_fee is not None else None
        except Exception:
            session_fee = None

        total_fee = None
        if consultation_fee is not None and consultation_fee > 0:
            total_fee = consultation_fee + (session_fee or 0) if inferred_has_session and session_fee else consultation_fee

        status_raw = t.get("status")
        status_val = str(getattr(status_raw, "value", status_raw) or status_raw or "").lower()

        # Match POS/reception expected response shape
        items.append(
            {
                "patient_name": patient_name,
                "doctor_name": t.get("doctor_name") or dmeta.get("name"),
                "department": department,
                "consultation_fee": consultation_fee,
                "session_fee": session_fee,
                "total_fee": total_fee,
            }
        )

    # Stable ordering by token number if possible
    def _tok_num(it: Dict[str, Any]) -> int:
        try:
            return int(it.get("token_number") or 0)
        except Exception:
            return 0

    items.sort(key=_tok_num)

    start = (int(page) - 1) * int(page_size)
    end = start + int(page_size)
    page_items = items[start:end]

    return ok(
        data=page_items,
        meta={"page": page, "page_size": page_size, "total": len(items)},
    )


@router.get("/tokens", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_tokens(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    day: Optional[str] = Query(None, description="DD-MM-YYYY (optional filter)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Receptionist view of slot bookings.

    GET /api/reception/tokens
    Returns: day, time, doctor_id, patient_name (and helpful fields).
    """
    db = get_db()
    ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)
    if doctor_id:
        ref = ref.where("doctor_id", "==", doctor_id)

    docs = [d.to_dict() for d in ref.limit(5000).stream()]
    items: List[Dict[str, Any]] = []
    for t in docs:
        if day and str(t.get("day") or "").strip() != str(day).strip():
            continue
        items.append(
            {
                "token_id": t.get("id") or t.get("token_id"),
                "doctor_id": t.get("doctor_id"),
                "doctor_name": t.get("doctor_name"),
                "patient_name": t.get("patient_name"),
                "day": t.get("day"),
                "time": t.get("time"),
                "appointment_date": t.get("appointment_date"),
                "status": t.get("status"),
            }
        )

    # Sort by day/time then token_number if present
    def _k(x: Dict[str, Any]):
        return (
            str(x.get("day") or ""),
            str(x.get("time") or ""),
            int(x.get("token_number") or 0) if str(x.get("token_number") or "").isdigit() else 0,
        )

    items.sort(key=_k)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return ok(data=items[start:end], meta={"page": page, "page_size": page_size, "total": total})

