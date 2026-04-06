from typing import Any, Dict, List, Optional
from datetime import datetime

from app.config import COLLECTIONS
from app.database import get_db
from app.models import PharmacyMedicineCreate, PharmacyMedicineUpdate


def _snap_exists(snap: Any) -> bool:
    try:
        ex = getattr(snap, "exists", None)
        if callable(ex):
            return bool(ex())
        return bool(ex)
    except Exception:
        return False


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


def create_medicine(payload: PharmacyMedicineCreate) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["PHARMACY_MEDICINES"]).document()

    data = payload.model_dump()
    data["id"] = ref.id
    data["created_at"] = datetime.utcnow()

    ref.set(data)
    return data


def update_medicine(medicine_id: str, payload: PharmacyMedicineUpdate) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["PHARMACY_MEDICINES"]).document(medicine_id)
    snap = ref.get()
    if not _snap_exists(snap):
        raise KeyError("Medicine not found")

    updates = payload.model_dump(exclude_unset=True)
    updates["updated_at"] = datetime.utcnow()
    ref.set(updates, merge=True)

    out = ref.get().to_dict() or {}
    out["id"] = out.get("id") or medicine_id
    return out


def delete_medicine(medicine_id: str) -> None:
    db = get_db()
    ref = db.collection(COLLECTIONS["PHARMACY_MEDICINES"]).document(medicine_id)
    snap = ref.get()
    if not _snap_exists(snap):
        raise KeyError("Medicine not found")

    delete_fn = getattr(ref, "delete", None)
    if callable(delete_fn):
        ref.delete()
        return

    ref.set({"deleted_at": datetime.utcnow(), "is_deleted": True}, merge=True)


def get_medicine(medicine_id: str) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["PHARMACY_MEDICINES"]).document(medicine_id)
    snap = ref.get()
    if not _snap_exists(snap):
        raise KeyError("Medicine not found")

    data = snap.to_dict() or {}
    data["id"] = data.get("id") or medicine_id

    exp = _to_dt(data.get("expiration_date"))
    if exp is not None:
        data["expiration_date"] = exp
    created = _to_dt(data.get("created_at"))
    if created is not None:
        data["created_at"] = created

    return data


def list_medicines(
    *,
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    db = get_db()
    q = db.collection(COLLECTIONS["PHARMACY_MEDICINES"])

    docs = [d.to_dict() for d in q.limit(int(limit)).stream()]

    cat_norm = str(category or "").strip().lower()
    sub_norm = str(sub_category or "").strip().lower()
    name_norm = str(name or "").strip().lower()

    out: List[Dict[str, Any]] = []
    for it in docs:
        if not isinstance(it, dict):
            continue
        if it.get("is_deleted"):
            continue
        if cat_norm and str(it.get("category") or "").strip().lower() != cat_norm:
            continue
        if sub_norm and str(it.get("sub_category") or "").strip().lower() != sub_norm:
            continue
        if name_norm:
            nm = str(it.get("name") or "").strip().lower()
            gn = str(it.get("generic_name") or "").strip().lower()
            if name_norm not in nm and name_norm not in gn:
                continue

        exp = _to_dt(it.get("expiration_date"))
        if exp is not None:
            it["expiration_date"] = exp
        created = _to_dt(it.get("created_at"))
        if created is not None:
            it["created_at"] = created

        out.append(it)

    out.sort(key=lambda x: _to_dt(x.get("created_at")) or datetime.min, reverse=True)
    return out
