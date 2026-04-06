import argparse
from datetime import datetime
from typing import Any, Dict, Optional, Set

import pandas as pd

import firebase_admin
from firebase_admin import credentials, firestore


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


def init_firestore(cred_path: str):
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def load_excel(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    # Normalize column names (trim)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [col for col in EXCEL_COLUMNS.values() if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in Excel: {missing}")

    return df


def fetch_existing_product_ids(db) -> Set[int]:
    existing: Set[int] = set()
    ref = db.collection("pharmacy_medicines")
    for doc in ref.stream():
        d = doc.to_dict() or {}
        pid = _to_int(d.get("product_id"))
        if pid is not None:
            existing.add(pid)
    return existing


def row_to_doc(row: pd.Series) -> Optional[Dict[str, Any]]:
    if _is_empty_row(row):
        return None

    product_id = _to_int(row.get(EXCEL_COLUMNS["product_id"]))
    if product_id is None:
        return None

    purchase_price = _to_float(row.get(EXCEL_COLUMNS["purchase_price"]))
    selling_price = _to_float(row.get(EXCEL_COLUMNS["selling_price"]))
    quantity = _to_int(row.get(EXCEL_COLUMNS["quantity"]))

    doc: Dict[str, Any] = {
        "product_id": product_id,
        "batch_no": _to_str(row.get(EXCEL_COLUMNS["batch_no"])) or "",
        "name": _to_str(row.get(EXCEL_COLUMNS["name"])) or "",
        "generic_name": _to_str(row.get(EXCEL_COLUMNS["generic_name"])),
        "type": _to_str(row.get(EXCEL_COLUMNS["type"])),
        "distributor": _to_str(row.get(EXCEL_COLUMNS["distributor"])),
        "purchase_price": float(purchase_price or 0.0),
        "selling_price": float(selling_price or 0.0),
        "stock_unit": _to_str(row.get(EXCEL_COLUMNS["stock_unit"])),
        "quantity": int(quantity or 0),
        "expiration_date": _to_dt(row.get(EXCEL_COLUMNS["expiration_date"])),
        "category": _to_str(row.get(EXCEL_COLUMNS["category"])),
        "sub_category": _to_str(row.get(EXCEL_COLUMNS["sub_category"])),
        "created_at": datetime.utcnow(),
    }

    # Drop None expiration_date to avoid weird Firestore types
    if doc.get("expiration_date") is None:
        doc.pop("expiration_date", None)

    return doc


def import_medicines(excel_path: str, cred_path: str, sheet: Optional[str] = None) -> int:
    db = init_firestore(cred_path)
    df = load_excel(excel_path, sheet=sheet)

    existing = fetch_existing_product_ids(db)
    seen_in_file: Set[int] = set()

    imported = 0
    ref = db.collection("pharmacy_medicines")

    batch = db.batch()
    batch_ops = 0

    for _, row in df.iterrows():
        doc = row_to_doc(row)
        if not doc:
            continue

        pid = int(doc["product_id"])
        if pid in seen_in_file:
            continue
        if pid in existing:
            continue

        seen_in_file.add(pid)

        doc_ref = ref.document()  # generate Firestore ID
        doc["id"] = doc_ref.id

        batch.set(doc_ref, doc)
        batch_ops += 1
        imported += 1

        if batch_ops >= 400:
            batch.commit()
            batch = db.batch()
            batch_ops = 0

    if batch_ops:
        batch.commit()

    return imported


def main():
    parser = argparse.ArgumentParser(description="Import pharmacy medicines from Excel into Firestore")
    parser.add_argument("--excel", required=True, help="Path to Excel file")
    parser.add_argument("--sheet", required=False, default=None, help="Optional sheet name")
    parser.add_argument(
        "--cred",
        required=False,
        default="firebase_key.json",
        help="Path to Firebase service account json (default: firebase_key.json)",
    )

    args = parser.parse_args()

    count = import_medicines(args.excel, args.cred, sheet=args.sheet)
    print(f"Imported {count} medicines into pharmacy_medicines")


if __name__ == "__main__":
    main()
