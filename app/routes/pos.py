from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query, status, Depends

from app.security import get_current_active_user
from app.database import get_db
from app.config import COLLECTIONS
from app.models import TokenData
from app.security import require_roles
from app.utils.responses import ok
from app.routes.pharmacy import _normalize_str, _to_datetime, _prefix_query


router = APIRouter(prefix="/pos", tags=["POS Integration"])

#pos sale creation endpoint
@router.post("/sales")
async def create_pos_sale(
    payload: Dict[str, Any],
    current: TokenData = Depends(require_roles("pharmacist", "admin"))
):
    db = get_db()
    sales_ref = db.collection(COLLECTIONS.get("PHARMACY_SALES") or "pharmacy_sales")

    hospital_id = _normalize_str(str(payload.get("hospital_id") or ""))
    if not hospital_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hospital_id is required"
        )

    now = datetime.utcnow()

    sale_doc = sales_ref.document()
    data: Dict[str, Any] = {
        "id": sale_doc.id,
        "hospital_id": hospital_id,
        "items": payload.get("items") or [],
        "total_amount": float(payload.get("total_amount") or 0.0),
        "payment_status": _normalize_str(str(payload.get("payment_status") or "paid")).lower(),
        "external_reference": payload.get("external_reference"),
        "meta": payload.get("meta") or {},
        "created_at": now,
        "updated_at": now,
        "created_by": getattr(current, "user_id", None),
    }
    sale_doc.set(data)

    return ok(data=data, message="POS sale created")


#pos sale get endpoint
@router.get("/sales/{sale_id}")
async def get_pos_sale(
    sale_id: str,
    current: TokenData = Depends(require_roles("pharmacist", "admin"))
):
    db = get_db()
    ref = db.collection(COLLECTIONS.get("PHARMACY_SALES") or "pharmacy_sales").document(sale_id)
    snap = ref.get()

    if not getattr(snap, "exists", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    data = snap.to_dict() or {}
    return ok(data=data, message="POS sale details")


#medicine search
@router.get("/medicines")
async def pos_get_medicines(search: Optional[str] = Query(None, alias="search")) -> Dict[str, Any]:
    db = get_db()
    medicines_ref = db.collection(COLLECTIONS.get("PHARMACY_MEDICINES") or "pharmacy_medicines")

    q_raw = search or ""
    qn = _normalize_str(q_raw)

    if not qn:
        return {"results": []}

    by_name = _prefix_query(medicines_ref, "name", qn, limit=20)
    by_generic = _prefix_query(medicines_ref, "generic_name", qn, limit=20)

    merged: List[Dict[str, Any]] = []
    seen: set = set()

    for it in (by_name + by_generic):
        key = str(it.get("product_id") or it.get("id") or it.get("doc_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(it)
        if len(merged) >= 20:
            break

    results: List[Dict[str, Any]] = []

    for it in merged:
        try:
            qty = int(it.get("quantity") or 0)
        except Exception:
            qty = 0

        try:
            price = float(it.get("selling_price") or 0.0)
        except Exception:
            price = 0.0

        exp = _to_datetime(it.get("expiration_date"))

        results.append({
            "product_id": it.get("product_id"),
            "name": it.get("name"),
            "generic_name": it.get("generic_name"),
            "barcode": it.get("barcode"),
            "selling_price": price,
            "quantity": qty,
            "expiration_date": exp.isoformat() + "Z" if exp else None,
        })

    return {"results": results}

# barcode check
@router.get("/medicines/barcode/{barcode}")
async def pos_get_medicine_by_barcode(barcode: str) -> Dict[str, Any]:
    db = get_db()
    medicines_ref = db.collection(COLLECTIONS.get("PHARMACY_MEDICINES") or "pharmacy_medicines")

    bc = _normalize_str(barcode)
    if not bc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid barcode"
        )

    query = medicines_ref.where("barcode", "==", bc).limit(1)
    docs = list(query.stream())

    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medicine not found"
        )

    doc = docs[0]
    it = doc.to_dict() or {}

    exp = _to_datetime(it.get("expiration_date"))

    try:
        qty = int(it.get("quantity") or 0)
    except Exception:
        qty = 0

    try:
        price = float(it.get("selling_price") or 0.0)
    except Exception:
        price = 0.0

    data = {
        "product_id": it.get("product_id"),
        "name": it.get("name"),
        "generic_name": it.get("generic_name"),
        "barcode": it.get("barcode"),
        "selling_price": price,
        "quantity": qty,
        "expiration_date": exp.isoformat() + "Z" if exp else None,
    }

    return ok(data=data, message="Medicine found")

#inventory check
@router.get("/medicines/{product_id}/stock")
async def pos_get_medicine_stock(product_id: str) -> Dict[str, Any]:
    db = get_db()
    meds_ref = db.collection(COLLECTIONS.get("PHARMACY_MEDICINES") or "pharmacy_medicines")

    pid = _normalize_str(product_id)
    if not pid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid product id"
        )

    snap = meds_ref.document(pid).get()

    if not getattr(snap, "exists", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medicine not found"
        )

    it = snap.to_dict() or {}

    try:
        qty = int(it.get("quantity") or 0)
    except Exception:
        qty = 0

    exp = _to_datetime(it.get("expiration_date"))
    low_stock = bool(qty < 5)

    data = {
        "product_id": it.get("product_id") or pid,
        "name": it.get("name"),
        "generic_name": it.get("generic_name"),
        "quantity": qty,
        "low_stock": low_stock,
        "expiration_date": exp.isoformat() + "Z" if exp else None,
    }

    return ok(data=data, message="Stock checked")

#payment callback
@router.post("/payment-callback")
async def pos_payment_callback(
    payload: Dict[str, Any],
    current: TokenData = Depends(require_roles("pharmacist", "admin"))
):
    db = get_db()

    sale_id = _normalize_str(str(payload.get("sale_id") or ""))
    if not sale_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sale_id is required"
        )

    ref = db.collection(COLLECTIONS.get("PHARMACY_SALES") or "pharmacy_sales").document(sale_id)
    snap = ref.get()

    if not getattr(snap, "exists", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale not found"
        )

    status_norm = _normalize_str(str(payload.get("payment_status") or "paid")).lower()

    if status_norm not in {"paid", "pending", "failed", "refunded"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payment_status is invalid"
        )

    now = datetime.utcnow()

    updates: Dict[str, Any] = {
        "payment_status": status_norm,
        "transaction_id": payload.get("transaction_id"),
        "payment_meta": payload.get("meta") or {},
        "updated_at": now,
    }

    ref.set(updates, merge=True)

    return ok(data={"sale_id": sale_id, "payment_status": status_norm}, message="Payment callback processed")