from typing import Optional, Dict, Any
from datetime import datetime
from app.database import get_db
from app.config import COLLECTIONS

AUDIT_COLLECTION = "audit_logs"


def get_user_role(user_id: str) -> Optional[str]:
    try:
        db = get_db()
        user_doc = db.collection(COLLECTIONS["USERS"]).document(user_id).get()
        if getattr(user_doc, "exists", False):
            return (user_doc.to_dict() or {}).get("role")
    except Exception:
        return None
    return None


def log_action(user_id: str, role: Optional[str], action: str, token_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> None:
    """Write an audit log entry to Firestore.

    Fields stored:
    - id
    - userId
    - role
    - action
    - tokenId
    - timestamp (UTC)
    - extra (optional metadata)
    """
    db = get_db()
    ref = db.collection(AUDIT_COLLECTION).document()
    payload = {
        "id": ref.id,
        "userId": user_id,
        "role": role,
        "action": action,
        "tokenId": token_id,
        "timestamp": datetime.utcnow(),
        "extra": extra or {},
    }
    try:
        ref.set(payload)
    except Exception:
        # Avoid throwing from audit path; keep main flow resilient
        pass
