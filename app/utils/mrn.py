from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.config import COLLECTIONS


def format_mrn(seq: int) -> str:
    # Frontend format: MRN-0001
    try:
        n = int(seq)
    except Exception:
        n = 0
    return f"MRN-{max(n, 0):04d}"


def get_or_create_patient_mrn(db, hospital_id: str, patient_id: str) -> Optional[str]:

    hid = str(hospital_id or "").strip()
    pid = str(patient_id or "").strip()
    if not hid or not pid:
        return None

    users_ref = db.collection(COLLECTIONS["USERS"]).document(pid)
    counter_ref = db.collection(COLLECTIONS["COUNTERS"]).document(f"mrn_{hid}")

    def _extract_existing(user_doc: Dict[str, Any]) -> Optional[str]:
        try:
            by_h = user_doc.get("mrn_by_hospital") or {}
            if isinstance(by_h, dict):
                val = by_h.get(hid)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        except Exception:
            pass

        # Back-compat legacy fields (not per-hospital)
        for k in ("mrn", "patient_mrn"):
            v = user_doc.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    # Fast path: user doc already has mapping
    try:
        snap = users_ref.get()
        user_doc = snap.to_dict() if getattr(snap, "exists", False) else {}
        existing = _extract_existing(user_doc or {})
        if existing:
            # Ensure mapping exists for this hospital if old global mrn exists
            try:
                by_h = (user_doc or {}).get("mrn_by_hospital")
                if not isinstance(by_h, dict) or not by_h.get(hid):
                    users_ref.set({"mrn_by_hospital": {hid: existing}, "updated_at": datetime.utcnow()}, merge=True)
            except Exception:
                pass
            return existing
    except Exception:
        pass

    # Transactional allocation
    tx_factory = getattr(db, "transaction", None)
    if callable(tx_factory):
        transaction = tx_factory()

        def _txn(txn):
            usnap = users_ref.get(transaction=txn)
            udoc = usnap.to_dict() if getattr(usnap, "exists", False) else {}
            existing2 = _extract_existing(udoc or {})
            if existing2:
                txn.set(users_ref, {"mrn_by_hospital": {hid: existing2}, "updated_at": datetime.utcnow()}, merge=True)
                return existing2

            csnap = counter_ref.get(transaction=txn)
            cdoc = csnap.to_dict() if getattr(csnap, "exists", False) else {}
            try:
                seq = int((cdoc or {}).get("seq") or 0)
            except Exception:
                seq = 0
            new_seq = seq + 1
            mrn_val = format_mrn(new_seq)

            txn.set(counter_ref, {"seq": new_seq, "hospital_id": hid, "updated_at": datetime.utcnow()}, merge=True)
            txn.set(
                users_ref,
                {"mrn_by_hospital": {hid: mrn_val}, "updated_at": datetime.utcnow()},
                merge=True,
            )
            return mrn_val

        try:
            return _txn(transaction)
        except Exception:
            # Fall back to non-transactional best-effort
            pass

    # Fallback (best-effort): not fully race-proof but avoids total failure
    try:
        csnap = counter_ref.get()
        cdoc = csnap.to_dict() if getattr(csnap, "exists", False) else {}
        try:
            seq = int((cdoc or {}).get("seq") or 0)
        except Exception:
            seq = 0
        new_seq = seq + 1
        mrn_val = format_mrn(new_seq)
        counter_ref.set({"seq": new_seq, "hospital_id": hid, "updated_at": datetime.utcnow()}, merge=True)
        users_ref.set({"mrn_by_hospital": {hid: mrn_val}, "updated_at": datetime.utcnow()}, merge=True)
        return mrn_val
    except Exception:
        return None
