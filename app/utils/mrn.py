from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.db_models import User, HospitalSequence
import uuid

def format_mrn(seq: int) -> str:
    # Frontend format: MRN-0001
    try:
        n = int(seq)
    except Exception:
        n = 0
    return f"MRN-{max(n, 0):04d}"


def get_or_create_patient_mrn(db: Session, patient_id: str, hospital_id: str) -> Optional[str]:
    """
    Get or create a patient MRN for a specific hospital.
    The order of arguments (db, patient_id, hospital_id) matches what's used in routes/tokens.py.
    """
    hid = str(hospital_id or "").strip()
    pid = str(patient_id or "").strip()
    if not hid or not pid:
        return None

    # Get user
    user = db.query(User).filter(User.id == pid).first()
    if not user:
        return None

    # Check if user already has an MRN for this hospital
    mrn_by_hospital = user.mrn_by_hospital or {}
    if hid in mrn_by_hospital:
        return mrn_by_hospital[hid]

    # Need to generate a new MRN
    # Use HospitalSequence for atomic counting (simplified)
    seq_record = db.query(HospitalSequence).filter(HospitalSequence.hospital_id == hid).with_for_update().first()
    if not seq_record:
        # Create a new sequence record for this hospital if it doesn't exist
        seq_record = HospitalSequence(
            id=str(uuid.uuid4()),
            hospital_id=hid,
            mrn_seq=0
        )
        db.add(seq_record)
        db.flush() # Ensure it's in the DB for the current transaction

    seq_record.mrn_seq += 1
    new_seq = seq_record.mrn_seq
    mrn_val = format_mrn(new_seq)

    # Update user's MRN map
    # Create a new dict for mrn_by_hospital to ensure SQLAlchemy detects the change
    new_mrn_map = dict(user.mrn_by_hospital or {})
    new_mrn_map[hid] = mrn_val
    user.mrn_by_hospital = new_mrn_map
    user.updated_at = datetime.utcnow()

    # Commit is handled by the caller (routes)
    return mrn_val
