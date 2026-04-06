from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query
from app.security import get_current_active_user
from app.database import get_db
from app.config import COLLECTIONS
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
    current_user = Depends(get_current_active_user),
    status: Optional[str] = Query(None, description="Filter by token status (e.g., waiting, confirmed, in_progress)"),
    department: Optional[str] = Query(None, description="Doctor department/specialization"),
    doctor_id: Optional[str] = Query(None, alias="doctorId", description="Filter by doctor id"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Dict[str, Any]:
    db = get_db()

    tokens_ref = db.collection(COLLECTIONS["TOKENS"])  # base collection

    norm_status = _norm_status(status)
    if norm_status:
        tokens_ref = tokens_ref.where("status", "==", norm_status)
    if doctor_id:
        tokens_ref = tokens_ref.where("doctor_id", "==", doctor_id)

    token_docs = list(tokens_ref.stream())
    tokens_list: List[Dict[str, Any]] = [d.to_dict() for d in token_docs]

    if department:
        try:
            docs_ref = db.collection(COLLECTIONS["DOCTORS"]).where("specialization", "==", department)
            doctor_docs = list(docs_ref.stream())
            allowed_doctor_ids = {doc.id for doc in doctor_docs}
            tokens_list = [t for t in tokens_list if t.get("doctor_id") in allowed_doctor_ids]
        except Exception:
            tokens_list = []

    total = len(tokens_list)
    start = (page - 1) * limit
    end = start + limit
    page_items = tokens_list[start:end]

    return ok(
        data=page_items,
        meta={"page": page, "limit": limit, "total": total},
        message="Tokens fetched successfully",
    )
