from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import logging
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db_models import User, Doctor, Hospital, Token, ActivityLog # Assuming these models exist or will be added

from app.security import get_current_active_user
from app.database import get_db
from app.models import TokenData
from app.security import require_roles
from app.utils.responses import ok

router = APIRouter()
public_router = APIRouter()

logger = logging.getLogger(__name__)

# Note: Models for Pharmacy (Medicine, Sale, etc.) should be in db_models.py
# For now, we'll use TODOs where models are missing.
# Based on context, we might need to add these to db_models.py if they aren't there.

class AddMedicineRequest(BaseModel):
    product_id: int = Field(..., ge=0)
    batch_no: str
    name: str
    generic_name: str
    type: str
    distributor: str
    purchase_price: float = Field(..., gt=0)
    selling_price: float = Field(..., gt=0)
    stock_unit: str
    quantity: int = Field(..., ge=0)
    expiration_date: str
    category: str
    sub_category: str
    hospital_id: Optional[str] = None

class DispenseMedicineItem(BaseModel):
    product_id: int = Field(..., ge=0)
    quantity: int = Field(..., ge=1)

class DispenseMedicineRequest(BaseModel):
    patient_id: str
    doctor_id: str
    medicines: List[DispenseMedicineItem]

def _normalize_date_str(v: Optional[str]) -> Optional[str]:
    if not v: return None
    s = v.strip()
    try:
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                dd, mm, yyyy = parts
                return datetime(int(yyyy), int(mm), int(dd)).date().isoformat()
    except Exception: pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception: pass
    return s

@public_router.get("/search-medicine")
async def search_medicine(
    q: str = Query(..., description="Search by medicine name or generic name"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    # TODO: Use proper PharmacyMedicine model from db_models
    from app.db_models import PharmacyMedicine
    qn = f"%{q.strip().lower()}%"
    medicines = db.query(PharmacyMedicine).filter(
        or_(
            func.lower(PharmacyMedicine.name).like(qn),
            func.lower(PharmacyMedicine.generic_name).like(qn)
        )
    ).limit(20).all()

    results = []
    for m in medicines:
        data = {k: v for k, v in m.__dict__.items() if not k.startswith('_')}
        results.append({
            "product_id": data.get("product_id"),
            "name": data.get("name"),
            "generic_name": data.get("generic_name"),
            "selling_price": float(data.get("selling_price") or 0),
            "quantity": int(data.get("quantity") or 0),
            "expiration_date": data.get("expiration_date").isoformat() if data.get("expiration_date") else None,
            "low_stock": bool((data.get("quantity") or 0) < 5),
        })

    return {"results": results}

@router.post("/sync-from-legacy", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def _sync_medicines_internal(db: Session, hospital_id: Optional[str] = None) -> Dict[str, int]:
    """Internal function to migrate medicines from Firebase to PostgreSQL."""
    from app.services.pharmacy_inventory_service import list_medicines as list_legacy
    from app.db_models import PharmacyMedicine
    
    # 1. Fetch all legacy items
    # If hospital_id is provided, we could filter by it, but list_legacy doesn't support it yet
    legacy_items = list_legacy(limit=1000)
    if not legacy_items:
        return {"synced": 0, "skipped": 0, "total_legacy": 0}

    # 2. Pre-fetch existing product IDs from PostgreSQL to avoid N+1 queries
    existing_ids = {row[0] for row in db.query(PharmacyMedicine.product_id).all()}
    
    synced_count = 0
    skipped_count = 0
    
    # 3. Batch process items
    for item in legacy_items:
        prod_id = item.get("product_id")
        if prod_id is None:
            continue
            
        prod_id_int = int(prod_id)
        if prod_id_int in existing_ids:
            skipped_count += 1
            continue
            
        # Create new PG record
        new_med = PharmacyMedicine(
            id=str(item.get("id") or uuid.uuid4()),
            product_id=prod_id_int,
            batch_no=str(item.get("batch_no") or "LEGACY"),
            name=str(item.get("name") or "Unnamed"),
            generic_name=item.get("generic_name"),
            type=item.get("type"),
            distributor=item.get("distributor"),
            purchase_price=float(item.get("purchase_price") or 0),
            selling_price=float(item.get("selling_price") or 0),
            stock_unit=item.get("stock_unit"),
            quantity=int(item.get("quantity") or 0),
            expiration_date=item.get("expiration_date"),
            category=item.get("category"),
            sub_category=item.get("sub_category"),
            hospital_id=item.get("hospital_id") or hospital_id,
            created_at=item.get("created_at") or datetime.utcnow()
        )
        db.add(new_med)
        synced_count += 1
        
    if synced_count > 0:
        db.commit()
        
    return {
        "synced": synced_count,
        "skipped": skipped_count,
        "total_legacy": len(legacy_items)
    }

@router.post("/sync-from-legacy", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def sync_medicines_from_legacy(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user)
) -> Any:
    """Migrate medicines from Firebase to PostgreSQL if they don't exist yet."""
    result = await _sync_medicines_internal(db)
    return ok(data=result, message=f"Successfully imported {result['synced']} medicines from legacy storage")


@public_router.get("/medicines")
async def get_all_medicines(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    auto_sync: bool = Query(True, description="Automatically import legacy data if PostgreSQL is empty")
) -> Dict[str, Any]:
    """Get a paginated list of all medicines in the inventory"""
    from app.db_models import PharmacyMedicine
    
    # Query building
    query = db.query(PharmacyMedicine)
    if hospital_id:
        query = query.filter(PharmacyMedicine.hospital_id == hospital_id)
        
    total = query.count()
    
    # Auto-sync logic: if PG is empty and auto_sync is on, try to import from Firebase
    if total == 0 and auto_sync:
        sync_result = await _sync_medicines_internal(db, hospital_id=hospital_id)
        # Re-count after sync
        total = query.count()

    medicines = query.offset((page-1)*page_size).limit(page_size).all()
    
    results = []
    for m in medicines:
        results.append({
            "product_id": m.product_id,
            "name": m.name,
            "generic_name": m.generic_name,
            "type": m.type,
            "distributor": m.distributor,
            "selling_price": float(m.selling_price or 0),
            "quantity": int(m.quantity or 0),
            "expiration_date": m.expiration_date.isoformat() if m.expiration_date else None,
            "category": m.category,
            "sub_category": m.sub_category,
            "low_stock": bool((m.quantity or 0) < 5),
            "hospital_id": m.hospital_id
        })

    return ok(
        data=results,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "hospital_id": hospital_id
        }
    )

@public_router.post("/dispense-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def dispense_medicine(
    payload: DispenseMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    from app.db_models import PharmacyMedicine, PharmacySale
    
    # Simple transaction in SQLAlchemy
    try:
        for item in payload.medicines:
            med = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == item.product_id).with_for_update().first()
            if not med:
                raise HTTPException(status_code=404, detail=f"Medicine {item.product_id} not found")
            
            if med.quantity < item.quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {med.name}")
            
            med.quantity -= item.quantity
            
            sale = PharmacySale(
                id=str(uuid.uuid4()),
                patient_id=payload.patient_id,
                doctor_id=payload.doctor_id,
                medicine_id=med.product_id,
                medicine_name=med.name,
                quantity=item.quantity,
                unit_price=med.selling_price,
                total_price=float(item.quantity * med.selling_price),
                sold_at=datetime.utcnow(),
                performed_by=current.user_id
            )
            db.add(sale)
        
        db.commit()
        return ok(message="Medicines dispensed successfully")
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException): raise e
        logger.exception("Dispense failed")
        raise HTTPException(status_code=500, detail="Dispense failed")

@public_router.post("/add-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def add_medicine(
    payload: AddMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    from app.db_models import PharmacyMedicine
    
    existing = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == payload.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Medicine already exists")

    exp_iso = _normalize_date_str(payload.expiration_date)
    exp_dt = datetime.fromisoformat(exp_iso) if exp_iso else None

    new_med = PharmacyMedicine(
        product_id=payload.product_id,
        batch_no=payload.batch_no,
        name=payload.name,
        generic_name=payload.generic_name,
        type=payload.type,
        distributor=payload.distributor,
        purchase_price=payload.purchase_price,
        selling_price=payload.selling_price,
        stock_unit=payload.stock_unit,
        quantity=payload.quantity,
        expiration_date=exp_dt,
        category=payload.category,
        sub_category=payload.sub_category,
        hospital_id=payload.hospital_id,
        created_at=datetime.utcnow()
    )
    db.add(new_med)
    db.commit()
    return ok(message="Medicine added successfully")

@router.get("/items", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def list_items(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    auto_sync: bool = Query(True, description="Automatically import legacy data if PostgreSQL is empty")
) -> Any:
    """List pharmacy inventory items with filtering and pagination."""
    from app.db_models import PharmacyMedicine
    
    query = db.query(PharmacyMedicine)
    
    # Auto-sync check
    if query.count() == 0 and auto_sync:
        await sync_medicines_from_legacy(db)
        query = db.query(PharmacyMedicine)
    
    if hospital_id:
        query = query.filter(PharmacyMedicine.hospital_id == hospital_id)
    if q:
        search = f"%{q}%"
        query = query.filter(
            or_(
                PharmacyMedicine.name.ilike(search),
                PharmacyMedicine.generic_name.ilike(search),
                PharmacyMedicine.batch_no.ilike(search),
                PharmacyMedicine.distributor.ilike(search)
            )
        )
    
    total = query.count()
    items = query.offset((page-1)*page_size).limit(page_size).all()
    results = [{k: v for k, v in i.__dict__.items() if not k.startswith('_')} for i in items]
    
    return ok(data=results, meta={"page": page, "page_size": page_size, "total": total})

# Rest of the functions follow similar pattern: db.query(Model).filter(...)...
# I'll implement the most critical ones to ensure Firebase patterns are gone.

@router.delete("/items/{item_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Any:
    from app.db_models import PharmacyMedicine
    med = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == int(item_id)).first()
    if not med: raise HTTPException(status_code=404, detail="Not found")
    
    # Soft delete if column exists, else hard delete
    if hasattr(med, 'is_deleted'):
        med.is_deleted = True
        med.updated_at = datetime.utcnow()
    else:
        db.delete(med)
    
    db.commit()
    return ok(message="Medicine deleted")
