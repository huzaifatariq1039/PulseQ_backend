from datetime import datetime
from typing import Any, Dict, Optional, List
import uuid

from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db_models import User, Doctor, Hospital, Token, ActivityLog # Assuming pharmacy models exist

from app.security import get_current_active_user
from app.database import get_db
from app.models import TokenData
from app.security import require_roles
from app.utils.responses import ok

router = APIRouter(prefix="/pos", tags=["POS Integration"])

@router.post("/sales")
async def create_pos_sale(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(require_roles("pharmacist", "admin"))
):
    from app.db_models import PharmacySale # Assuming it exists
    hospital_id = str(payload.get("hospital_id") or "")
    if not hospital_id:
        raise HTTPException(status_code=400, detail="hospital_id required")

    sale_id = str(uuid.uuid4())
    new_sale = PharmacySale(
        id=sale_id,
        hospital_id=hospital_id,
        items=payload.get("items") or [],
        total_amount=float(payload.get("total_amount") or 0.0),
        payment_status=str(payload.get("payment_status") or "paid").lower(),
        created_at=datetime.utcnow(),
        performed_by=current.user_id
    )
    db.add(new_sale)
    db.commit()
    
    return ok(data={"id": sale_id}, message="POS sale created")

@router.get("/medicines")
async def pos_get_medicines(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, alias="search")
) -> Dict[str, Any]:
    from app.db_models import PharmacyMedicine
    if not search: return {"results": []}
    
    qn = f"%{search.strip().lower()}%"
    meds = db.query(PharmacyMedicine).filter(
        or_(
            func.lower(PharmacyMedicine.name).like(qn),
            func.lower(PharmacyMedicine.generic_name).like(qn),
            func.lower(PharmacyMedicine.barcode).like(qn)
        )
    ).limit(20).all()

    results = []
    for m in meds:
        results.append({
            "product_id": m.product_id,
            "name": m.name,
            "generic_name": m.generic_name,
            "barcode": getattr(m, 'barcode', None),
            "selling_price": float(m.selling_price or 0),
            "quantity": int(m.quantity or 0),
            "expiration_date": m.expiration_date.isoformat() if m.expiration_date else None,
        })
    return {"results": results}

@router.get("/medicines/barcode/{barcode}")
async def pos_get_medicine_by_barcode(
    barcode: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    from app.db_models import PharmacyMedicine
    med = db.query(PharmacyMedicine).filter(PharmacyMedicine.barcode == barcode).first()
    if not med: raise HTTPException(status_code=404, detail="Not found")
    
    return ok(data={
        "product_id": med.product_id,
        "name": med.name,
        "selling_price": float(med.selling_price or 0),
        "quantity": int(med.quantity or 0)
    })
