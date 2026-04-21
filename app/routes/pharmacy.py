from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
import logging
import io
import uuid
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case, literal_column
from app.db_models import PharmacyMedicine, PharmacySale

from app.security import get_current_active_user
from app.database import get_db
from app.models import TokenData
from app.security import require_roles
from app.utils.responses import ok
from app.services.go_pos_service import go_pos_service
from app.services.cache_service import CacheService, cached

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
    generic_name: Optional[str] = None
    type: Optional[str] = None
    distributor: Optional[str] = None
    purchase_price: float = Field(..., gt=0)
    selling_price: float = Field(..., gt=0)
    stock_unit: Optional[str] = None
    quantity: int = Field(..., ge=0)
    expiration_date: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
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

@router.get("/dashboard/stats", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_pharmacy_dashboard_stats(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
):
    """Get summary statistics for the pharmacy dashboard - single SQL query."""
    now = datetime.utcnow()

    # Single query: all stats computed in one round-trip
    query = db.query(
        func.count(PharmacyMedicine.id).label('total'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity > 0, 1), else_=0
        )), 0).label('in_stock'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity < 10, 1), else_=0
        )), 0).label('low_stock'),
        func.coalesce(func.sum(
            PharmacyMedicine.quantity * PharmacyMedicine.selling_price
        ), 0).label('inventory_value'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.expiration_date <= now, 1), else_=0
        )), 0).label('expired'),
        func.coalesce(func.sum(case(
            (PharmacyMedicine.quantity > 0, case(
                (or_(PharmacyMedicine.expiration_date.is_(None),
                     PharmacyMedicine.expiration_date > now), 1),
                else_=0
            )), else_=0
        )), 0).label('active'),
    ).filter(PharmacyMedicine.is_deleted.isnot(True))

    if hospital_id:
        query = query.filter(PharmacyMedicine.hospital_id == hospital_id)

    stats = query.first()

    return ok(data={
        "total_medicines": int(stats.total or 0),
        "active_medicines": int(stats.active or 0),
        "low_stock_items": int(stats.low_stock or 0),
        "expired_items": int(stats.expired or 0),
        "inventory_value": round(float(stats.inventory_value or 0), 2)
    })

@router.get("/reports/sales-summary", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_pharmacy_sales_summary(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
):
    """Get summary of sales and revenue - OPTIMIZED with SQL aggregation"""

    def _sum_sales(start: datetime, end: datetime) -> float:
        """Helper to get total sales between two dates."""
        q = db.query(
            func.coalesce(func.sum(PharmacySale.total_price), 0)
        ).filter(PharmacySale.sold_at >= start, PharmacySale.sold_at < end)
        if hospital_id:
            q = q.filter(PharmacySale.hospital_id == hospital_id)
        return float(q.scalar() or 0)

    def _count_sales(start: datetime, end: datetime) -> int:
        """Helper to get total sale count between two dates."""
        q = db.query(func.count(PharmacySale.id)).filter(
            PharmacySale.sold_at >= start, PharmacySale.sold_at < end
        )
        if hospital_id:
            q = q.filter(PharmacySale.hospital_id == hospital_id)
        return int(q.scalar() or 0)

    def _pct_change(current: float, previous: float) -> float:
        """Calculate percentage change. Returns 0 if no previous data."""
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    # --- Total revenue (all time) ---
    total_query = db.query(
        func.coalesce(func.sum(PharmacySale.total_price), 0).label('total_revenue'),
        func.count(PharmacySale.id).label('total_count')
    )
    if hospital_id:
        total_query = total_query.filter(PharmacySale.hospital_id == hospital_id)
    totals = total_query.first()

    now = datetime.utcnow()

    # --- Today ---
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    daily_revenue = _sum_sales(today_start, today_end)
    daily_count = _count_sales(today_start, today_end)

    # --- This week vs last week ---
    # Week starts on Monday (weekday() == 0)
    days_since_monday = now.weekday()
    this_week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = this_week_start - timedelta(days=7)

    this_week_revenue = _sum_sales(this_week_start, now)
    last_week_revenue = _sum_sales(last_week_start, this_week_start)
    weekly_pct_change = _pct_change(this_week_revenue, last_week_revenue)

    # --- This month vs last month ---
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Last month start
    if this_month_start.month == 1:
        last_month_start = this_month_start.replace(year=this_month_start.year - 1, month=12)
    else:
        last_month_start = this_month_start.replace(month=this_month_start.month - 1)

    this_month_revenue = _sum_sales(this_month_start, now)
    last_month_revenue = _sum_sales(last_month_start, this_month_start)
    monthly_pct_change = _pct_change(this_month_revenue, last_month_revenue)

    return ok(data={
        "total_revenue": round(float(totals.total_revenue or 0), 2),
        "total_sales_count": totals.total_count or 0,
        "daily_revenue": round(daily_revenue, 2),
        "daily_sales_count": daily_count,
        "weekly_revenue": round(this_week_revenue, 2),
        "weekly_pct_change": weekly_pct_change,
        "weekly_trend": "up" if weekly_pct_change > 0 else ("down" if weekly_pct_change < 0 else "neutral"),
        "monthly_revenue": round(this_month_revenue, 2),
        "monthly_pct_change": monthly_pct_change,
        "monthly_trend": "up" if monthly_pct_change > 0 else ("down" if monthly_pct_change < 0 else "neutral"),
    })

@router.get("/reports/revenue-chart", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_revenue_chart_data(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=30)
):
    """Get revenue data for chart (last N days) - OPTIMIZED"""
    now = datetime.utcnow()
    start_date = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Fetch only needed data with aggregation
    query = db.query(
        func.date(PharmacySale.sold_at).label('sale_date'),
        func.coalesce(func.sum(PharmacySale.total_price), 0).label('day_revenue'),
        func.count(PharmacySale.id).label('sales_count')
    ).filter(PharmacySale.sold_at >= start_date)
    
    if hospital_id:
        query = query.filter(PharmacySale.hospital_id == hospital_id)
    
    # Group by date
    query = query.group_by(func.date(PharmacySale.sold_at))
    aggregated_sales = query.all()
    
    # Build date map
    sales_map = {row.sale_date: {'revenue': float(row.day_revenue), 'count': row.sales_count} for row in aggregated_sales}
    
    # Fill in all days (even with no sales)
    chart_data = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        day_date = day.date()
        day_stats = sales_map.get(day_date, {'revenue': 0.0, 'count': 0})
        
        chart_data.append({
            "date": day.strftime("%Y-%m-%d"),
            "revenue": round(day_stats['revenue'], 2),
            "sales_count": day_stats['count']
        })
    
    return ok(data=chart_data)

@router.get("/sales/history", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def get_sales_history(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Get list of all sales transactions - OPTIMIZED with pagination"""
    query = db.query(PharmacySale)
    if hospital_id:
        query = query.filter(PharmacySale.hospital_id == hospital_id)
    
    total = query.count()
    sales = query.order_by(PharmacySale.sold_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    
    results = []
    for s in sales:
        results.append({
            "id": s.id,
            "medicine_name": s.medicine_name,
            "quantity": s.quantity,
            "unit_price": s.unit_price,
            "total_price": s.total_price,
            "sold_at": s.sold_at.isoformat(),
            "payment_status": s.payment_status
        })
        
    return ok(data=results, meta={"total": total, "page": page, "page_size": page_size})

@public_router.get("/search-medicine")
async def search_medicine(
    q: str = Query(..., description="Search by medicine name or generic name"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    # Split search into terms
    terms = [t for t in q.strip().split() if t]
    
    query = db.query(PharmacyMedicine).filter(PharmacyMedicine.is_deleted.isnot(True))
    
    for term in terms:
        like_term = f"%{term}%"
        query = query.filter(
            or_(
                PharmacyMedicine.name.ilike(like_term),
                PharmacyMedicine.generic_name.ilike(like_term)
            )
        )
        
    medicines = query.all()

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

@public_router.post("/add-medicine")
async def public_add_medicine(
    payload: AddMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Add medicine (public router alias for frontend compatibility)."""
    existing = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == payload.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Medicine with this product ID already exists")

    exp_iso = _normalize_date_str(payload.expiration_date)
    exp_dt = None
    if exp_iso:
        try:
            exp_dt = datetime.fromisoformat(exp_iso)
        except (ValueError, TypeError):
            pass

    new_med = PharmacyMedicine(
        id=str(uuid.uuid4()),
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
        hospital_id=payload.hospital_id or getattr(current, 'hospital_id', None),
        created_at=datetime.utcnow()
    )
    db.add(new_med)
    db.commit()
    return ok(message="Medicine added successfully", data={"id": new_med.id, "product_id": new_med.product_id})

async def _sync_medicines_internal(db: Session, hospital_id: Optional[str] = None) -> Dict[str, int]:
    """Internal function to migrate medicines from Firebase to PostgreSQL."""
    from app.services.pharmacy_inventory_service import list_medicines as list_legacy
    
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
    page_size: int = Query(100, ge=1, le=500),  
) -> Dict[str, Any]:
    """Get medicines list - optimized with column-level SELECT."""
    # Column-level SELECT: only fetch needed columns, skip ORM hydration
    cols = (
        PharmacyMedicine.id, PharmacyMedicine.product_id, PharmacyMedicine.batch_no,
        PharmacyMedicine.name, PharmacyMedicine.generic_name, PharmacyMedicine.type,
        PharmacyMedicine.distributor, PharmacyMedicine.purchase_price,
        PharmacyMedicine.selling_price, PharmacyMedicine.stock_unit,
        PharmacyMedicine.quantity, PharmacyMedicine.expiration_date,
        PharmacyMedicine.category, PharmacyMedicine.sub_category,
        PharmacyMedicine.hospital_id, PharmacyMedicine.created_at,
        PharmacyMedicine.updated_at,
    )
    base = db.query(*cols).filter(PharmacyMedicine.is_deleted.isnot(True))
    if hospital_id:
        base = base.filter(PharmacyMedicine.hospital_id == hospital_id)

    total = base.count()
    rows = base.order_by(PharmacyMedicine.name).offset((page-1)*page_size).limit(page_size).all()

    results = [
        {
            "id": r.id, "product_id": r.product_id, "batch_no": r.batch_no,
            "name": r.name, "generic_name": r.generic_name, "type": r.type,
            "distributor": r.distributor,
            "purchase_price": float(r.purchase_price or 0),
            "selling_price": float(r.selling_price or 0),
            "stock_unit": r.stock_unit,
            "quantity": int(r.quantity or 0),
            "low_stock": (r.quantity or 0) < 5,
            "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
            "category": r.category, "sub_category": r.sub_category,
            "hospital_id": r.hospital_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]

    return ok(
        data=results,
        meta={
            "total": total, "page": page, "page_size": page_size,
            "hospital_id": hospital_id,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1
        }
    )

@router.post("/dispense-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def dispense_medicine(
    payload: DispenseMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
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
                hospital_id=current.hospital_id, # Link sale to hospital
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

@router.post("/add-medicine", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def add_medicine(
    payload: AddMedicineRequest,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    existing = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == payload.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Medicine already exists")

    exp_iso = _normalize_date_str(payload.expiration_date)
    exp_dt = datetime.fromisoformat(exp_iso) if exp_iso else None

    new_med = PharmacyMedicine(
        id=str(uuid.uuid4()),
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
    search_param: Optional[str] = Query(None, alias="search"),
    is_deleted: Optional[bool] = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> Any:
    """List pharmacy inventory items - optimized with column-level SELECT."""
    cols = (
        PharmacyMedicine.id, PharmacyMedicine.product_id, PharmacyMedicine.batch_no,
        PharmacyMedicine.name, PharmacyMedicine.generic_name, PharmacyMedicine.type,
        PharmacyMedicine.distributor, PharmacyMedicine.purchase_price,
        PharmacyMedicine.selling_price, PharmacyMedicine.stock_unit,
        PharmacyMedicine.quantity, PharmacyMedicine.expiration_date,
        PharmacyMedicine.category, PharmacyMedicine.sub_category,
        PharmacyMedicine.hospital_id, PharmacyMedicine.created_at,
        PharmacyMedicine.updated_at,
    )
    
    base = db.query(*cols)
    if is_deleted:
        base = base.filter(PharmacyMedicine.is_deleted == True)
    else:
        base = base.filter(PharmacyMedicine.is_deleted.isnot(True))

    if hospital_id:
        base = base.filter(PharmacyMedicine.hospital_id == hospital_id)
        
    search_term = q or search_param
    if search_term:
        # Split search into terms (e.g., "panadol 500" -> ["panadol", "500"])
        terms = [t for t in search_term.strip().split() if t]
        for term in terms:
            like_term = f"%{term}%"
            # Must match ALL terms in at least one of the fields (AND logic between terms, OR logic within a term)
            base = base.filter(
                or_(
                    PharmacyMedicine.name.ilike(like_term),
                    PharmacyMedicine.generic_name.ilike(like_term),
                    PharmacyMedicine.batch_no.ilike(like_term)
                )
            )

    total = base.count()
    rows = base.order_by(PharmacyMedicine.updated_at.desc()).offset((page-1)*page_size).limit(page_size).all()

    results = [
        {
            "id": r.id, "product_id": r.product_id, "batch_no": r.batch_no,
            "name": r.name, "generic_name": r.generic_name, "type": r.type,
            "distributor": r.distributor,
            "purchase_price": float(r.purchase_price or 0),
            "selling_price": float(r.selling_price or 0),
            "stock_unit": r.stock_unit,
            "quantity": int(r.quantity or 0),
            "low_stock": (r.quantity or 0) < 5,
            "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None,
            "category": r.category, "sub_category": r.sub_category,
            "hospital_id": r.hospital_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]

    return ok(data=results, meta={
        "page": page, "page_size": page_size, "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "has_next": page * page_size < total,
        "has_prev": page > 1
    })

# Rest of the functions follow similar pattern: db.query(Model).filter(...)...
# I'll implement the most critical ones to ensure Firebase patterns are gone.

@router.delete("/items/{item_id}", dependencies=[Depends(require_roles("pharmacy", "admin"))])
async def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Any:
    from app.db_models import PharmacyMedicine
    
    # Try matching by UUID id first, then by product_id
    med = db.query(PharmacyMedicine).filter(PharmacyMedicine.id == item_id).first()
    if not med:
        try:
            med = db.query(PharmacyMedicine).filter(PharmacyMedicine.product_id == int(item_id)).first()
        except (ValueError, TypeError):
            pass
    
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    
    deleted_name = med.name
    deleted_id = med.id
    
    # Soft delete to move to 'trash' instead of hard deleting
    med.is_deleted = True
    med.deleted_at = datetime.utcnow()
    
    db.commit()
    
    return ok(message=f"Medicine '{deleted_name}' deleted successfully", data={"deleted_id": deleted_id})
