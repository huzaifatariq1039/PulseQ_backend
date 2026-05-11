import argparse
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db_models import PharmacyMedicine
from app.config import DATABASE_URL

EXCEL_COLUMNS = {
    "product_id": "Product Id",
    "batch_no": "Batch No",
    "name": "Name",
    "generic_name": "Generic Name",
    "type": "Type",
    "distributor": "Distributor",
    "purchase_price": "Purchase Price",
    "selling_price": "Selling Price",
    "stock_unit": "Stock Unit",
    "quantity": "Quantity",
    "expiration_date": "Expiration Date",
    "category": "Category",
    "sub_category": "Sub Category",
}


def _is_empty_row(row: pd.Series) -> bool:
    try:
        for _, col in EXCEL_COLUMNS.items():
            v = row.get(col)
            if v is None:
                continue
            if isinstance(v, float) and pd.isna(v):
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return False
        return True
    except Exception:
        return False


def _to_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return int(float(v))
    except Exception:
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return float(v)
    except Exception:
        return None


def _to_dt(v: Any) -> Optional[datetime]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.to_pydatetime()
    except Exception:
        return None


def _to_str(v: Any) -> Optional[str]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        s = str(v)
        s = s.strip()
        return s or None
    except Exception:
        return None


def load_file(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    is_csv = path.lower().endswith(".csv")
    
    if is_csv:
        try:
            df = pd.read_csv(path, skiprows=1)
        except Exception:
            df = pd.read_csv(path, skiprows=1, sep=";")
    else:
        sheet_to_read = sheet if sheet is not None else 0
        df = pd.read_excel(path, sheet_name=sheet_to_read, skiprows=1)
    
    df.columns = [str(c).strip() for c in df.columns]

    missing = [col for col in EXCEL_COLUMNS.values() if col not in df.columns]
    if missing:
        print(f"DEBUG: Found columns in file: {list(df.columns)}")
        raise ValueError(f"Missing required columns in file: {missing}")

    return df


def row_to_model(row: pd.Series, hospital_id: Optional[str] = None) -> Optional[PharmacyMedicine]:
    if _is_empty_row(row):
        return None

    product_id = _to_int(row.get(EXCEL_COLUMNS["product_id"]))
    if product_id is None:
        return None

    purchase_price = _to_float(row.get(EXCEL_COLUMNS["purchase_price"]))
    selling_price = _to_float(row.get(EXCEL_COLUMNS["selling_price"]))
    quantity = _to_int(row.get(EXCEL_COLUMNS["quantity"]))

    return PharmacyMedicine(
        id=str(uuid.uuid4()),
        product_id=product_id,
        batch_no=_to_str(row.get(EXCEL_COLUMNS["batch_no"])) or "",
        name=_to_str(row.get(EXCEL_COLUMNS["name"])) or "",
        generic_name=_to_str(row.get(EXCEL_COLUMNS["generic_name"])),
        type=_to_str(row.get(EXCEL_COLUMNS["type"])),
        distributor=_to_str(row.get(EXCEL_COLUMNS["distributor"])),
        purchase_price=float(purchase_price or 0.0),
        selling_price=float(selling_price or 0.0),
        stock_unit=_to_str(row.get(EXCEL_COLUMNS["stock_unit"])),
        quantity=int(quantity or 0),
        expiration_date=_to_dt(row.get(EXCEL_COLUMNS["expiration_date"])),
        category=_to_str(row.get(EXCEL_COLUMNS["category"])),
        sub_category=_to_str(row.get(EXCEL_COLUMNS["sub_category"])),
        hospital_id=hospital_id,
        created_at=datetime.now(timezone.utc),
    )


def import_medicines(file_path: str, db_url: str, hospital_id: Optional[str] = None, sheet: Optional[str] = None) -> int:
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        df = load_file(file_path, sheet=sheet)
        
        # =========================================================
        # THE FIX: Pre-fetch all medicines for this hospital ONCE
        # =========================================================
        print(f"Pre-fetching existing inventory for hospital {hospital_id} from database...")
        # Notice we are NOT filtering by is_deleted. We want to fetch ghosts too!
        existing_records = session.query(PharmacyMedicine).filter(
            PharmacyMedicine.hospital_id == hospital_id
        ).all()
        
        # Turn the list into a Python Dictionary for instant O(1) lookups
        # Format: { product_id: PharmacyMedicine_Object }
        db_inventory_map = {med.product_id: med for med in existing_records}
        # =========================================================

        imported = 0
        updated = 0

        for _, row in df.iterrows():
            med = row_to_model(row, hospital_id=hospital_id)
            if not med:
                continue

            pid = med.product_id

            # FAST LOCAL CHECK: Does it exist in our Python dictionary?
            if pid in db_inventory_map:
                existing_med = db_inventory_map[pid]
                
                # Update the existing object directly in memory
                existing_med.batch_no = med.batch_no
                existing_med.name = med.name
                existing_med.generic_name = med.generic_name
                existing_med.type = med.type
                existing_med.distributor = med.distributor
                existing_med.purchase_price = med.purchase_price
                existing_med.selling_price = med.selling_price
                existing_med.stock_unit = med.stock_unit
                existing_med.quantity = med.quantity
                existing_med.expiration_date = med.expiration_date
                existing_med.category = med.category
                existing_med.sub_category = med.sub_category
                
                # Revive it if it was a soft-deleted ghost!
                existing_med.is_deleted = False 
                existing_med.updated_at = datetime.now(timezone.utc)
                
                updated += 1
            else:
                # INSERT new medicine
                session.add(med)
                # Add it to our local dictionary so we catch duplicates inside the Excel sheet itself!
                db_inventory_map[pid] = med 
                imported += 1

        # Push ALL changes to the database in ONE massive bulk transaction
        print(f"Pushing {imported} new and {updated} updated records to database...")
        session.commit()
        
        print(f"Import complete: {imported} new, {updated} updated")
        return imported + updated

    except Exception as e:
        session.rollback()
        print(f"Error during import: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import medicines from CSV/Excel into PostgreSQL")
    parser.add_argument("file_path", help="Path to the CSV or Excel file")
    parser.add_argument("--hospital_id", help="Assign medicines to this hospital ID", required=True)
    parser.add_argument("--sheet", help="Excel sheet name (optional)")
    parser.add_argument("--db_url", help="Database URL (defaults to config)", default=DATABASE_URL)

    args = parser.parse_args()

    # Handle postgres:// vs postgresql://
    db_url = args.db_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    print(f"Starting import from {args.file_path}...")
    count = import_medicines(args.file_path, db_url, hospital_id=args.hospital_id, sheet=args.sheet)
    print(f"Successfully imported {count} medicines.")