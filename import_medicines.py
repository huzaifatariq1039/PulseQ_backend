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
        # ensure python datetime
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


def load_excel(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    # If sheet is None, default to the first sheet (0)
    sheet_to_read = sheet if sheet is not None else 0
    
    # Based on the screenshot, Row 1 contains 'Inventory Management > Products...'
    # Row 2 contains the actual headers. We skip the first row (index 0).
    df = pd.read_excel(path, sheet_name=sheet_to_read, skiprows=1)
    
    # Normalize column names (trim spaces and handle case)
    df.columns = [str(c).strip() for c in df.columns]

    # Map the columns from the Excel to the internal model
    missing = [col for col in EXCEL_COLUMNS.values() if col not in df.columns]
    if missing:
        print(f"DEBUG: Found columns in Excel: {list(df.columns)}")
        raise ValueError(f"Missing required columns in Excel: {missing}")

    return df


def fetch_existing_product_ids(session) -> Set[int]:
    existing = session.query(PharmacyMedicine.product_id).all()
    return {pid[0] for pid in existing if pid[0] is not None}


def row_to_model(row: pd.Series) -> Optional[PharmacyMedicine]:
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
        created_at=datetime.now(timezone.utc),
    )


def import_medicines(excel_path: str, db_url: str, sheet: Optional[str] = None) -> int:
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        df = load_excel(excel_path, sheet=sheet)
        existing = fetch_existing_product_ids(session)
        seen_in_file: Set[int] = set()

        imported = 0
        for _, row in df.iterrows():
            med = row_to_model(row)
            if not med:
                continue

            pid = med.product_id
            if pid in seen_in_file:
                print(f"Skipping duplicate product_id in file: {pid}")
                continue
            if pid in existing:
                print(f"Skipping existing product_id in database: {pid}")
                continue

            seen_in_file.add(pid)
            session.add(med)
            imported += 1

            if imported % 50 == 0:
                try:
                    session.commit()
                    print(f"Imported {imported} items...")
                except Exception as commit_error:
                    session.rollback()
                    print(f"Commit error at {imported} items: {commit_error}")
                    raise

        session.commit()
        return imported
    except Exception as e:
        session.rollback()
        print(f"Error during import: {e}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Import pharmacy medicines from Excel into PostgreSQL")
    parser.add_argument("--excel", required=True, help="Path to Excel file")
    parser.add_argument("--sheet", required=False, default=None, help="Optional sheet name")
    parser.add_argument(
        "--db-url",
        required=False,
        default=DATABASE_URL,
        help="Database URL. Example: postgresql://postgres:pulseq123@localhost:5432/dbname",
    )

    args = parser.parse_args()

    if not args.db_url:
        print("Error: DATABASE_URL not found in environment or arguments.")
        return

    print(f"Starting import from {args.excel}...")
    count = import_medicines(args.excel, args.db_url, sheet=args.sheet)
    print(f"Successfully imported {count} medicines into pharmacy_medicines table.")


if __name__ == "__main__":
    main()
