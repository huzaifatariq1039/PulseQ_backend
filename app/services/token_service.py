import secrets
import string
from datetime import datetime
from typing import Tuple, Dict
from app.database import get_db
from app.config import COLLECTIONS, AVG_CONSULTATION_TIME_MINUTES, TESTING_MODE

class SmartTokenService:
    """Service for managing SmartToken generation and operations"""
    
    @staticmethod
    def generate_hex_code(length: int = 8) -> str:
        """Generate a random hex code"""
        return secrets.token_hex(length // 2)
    
    @staticmethod
    def generate_token_number(doctor_id: str, hospital_id: str, target_date) -> int:
        """Generate next token number starting from 1 each day, scoped per hospital and doctor.

        Behavior:
        - Counter resets every calendar day
        - Separate sequence for each (hospital_id, doctor_id) pair

        Counter key: tokens_{hospitalId}_{doctorId}_{YYYYMMDD}
        Uses Firestore's atomic Increment when available. Falls back to get/set for testing mocks.
        """
        db = get_db()

        # Build counter document id: tokens_{hospitalId}_{doctorId}_{YYYYMMDD} (per-hospital, per-doctor, per-day)
        try:
            day_key = target_date.strftime("%Y%m%d")
        except Exception:
            from datetime import datetime as _dt
            day_key = _dt.utcnow().strftime("%Y%m%d")
        counter_id = f"tokens_{hospital_id}_{doctor_id}_{day_key}"
        doc_ref = db.collection(COLLECTIONS["COUNTERS"]).document(counter_id)

        # Preferred path: Firestore atomic increment
        try:
            try:
                # Try firebase_admin.firestore Increment
                from firebase_admin import firestore as fb_fs  # type: ignore
                inc = fb_fs.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                return int(data.get("seq", 1))
            except Exception:
                # Try google cloud firestore Increment
                from google.cloud import firestore as gcf  # type: ignore
                inc = gcf.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                return int(data.get("seq", 1))
        except Exception:
            # Fallback for TESTING_MODE / MockFirestore without Increment support
            snap = doc_ref.get()
            exists_attr = getattr(snap, "exists", None)
            exists = bool(snap.exists()) if callable(exists_attr) else bool(exists_attr)
            data = snap.to_dict() if exists else {}
            seq = int((data or {}).get("seq", 0)) + 1
            payload = {"seq": seq, "updated_at": datetime.utcnow()}
            try:
                doc_ref.set(payload, merge=True)
            except TypeError:
                doc_ref.set(payload)
            return seq
    
    @staticmethod
    def format_token(token_number: int) -> str:
        """Format token number as A-XXX (e.g., A-042)"""
        return f"A-{token_number:03d}"
    
    @staticmethod
    def generate_display_code() -> str:
        """Generate a globally unique human-readable display code (e.g., T-000123)."""
        db = get_db()
        doc_ref = db.collection(COLLECTIONS["COUNTERS"]).document("global_token_seq")

        # Try atomic increment
        try:
            try:
                from firebase_admin import firestore as fb_fs  # type: ignore
                inc = fb_fs.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                seq = int(data.get("seq", 1))
            except Exception:
                from google.cloud import firestore as gcf  # type: ignore
                inc = gcf.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                seq = int(data.get("seq", 1))
        except Exception:
            # Fallback for mocks
            snap = doc_ref.get()
            exists_attr = getattr(snap, "exists", None)
            exists = bool(snap.exists()) if callable(exists_attr) else bool(exists_attr)
            data = snap.to_dict() if exists else {}
            seq = int((data or {}).get("seq", 0)) + 1
            try:
                doc_ref.set({"seq": seq, "updated_at": datetime.utcnow()}, merge=True)
            except TypeError:
                doc_ref.set({"seq": seq, "updated_at": datetime.utcnow()})

        return f"T-{seq:06d}"
    
    @staticmethod
    def create_smart_token(patient_id: str, doctor_id: str, hospital_id: str, 
                          appointment_date: datetime) -> Tuple[int, str, str]:
        """Create a new SmartToken"""
        # Use atomic per-hospital-per-doctor-per-day counter for numbering (resets daily)
        token_number = SmartTokenService.generate_token_number(doctor_id, hospital_id, appointment_date.date())
        hex_code = SmartTokenService.generate_hex_code()
        formatted_token = SmartTokenService.format_token(token_number)
        
        return token_number, hex_code, formatted_token
    
    @staticmethod
    def save_smart_token(token_data: dict) -> str:
        """Save SmartToken to database"""
        db = get_db()
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document()
        
        token_data["id"] = token_ref.id
        token_data["created_at"] = datetime.utcnow()
        token_data["updated_at"] = datetime.utcnow()
        
        token_ref.set(token_data)
        return token_ref.id
    
    @staticmethod
    def get_token_by_id(token_id: str):
        """Get SmartToken by ID"""
        db = get_db()
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
        token_doc = token_ref.get()
        
        if token_doc.exists:
            return token_doc.to_dict()
        return None
    
    @staticmethod
    def update_payment_status(token_id: str, payment_status: str, payment_method: str = None):
        """Update payment status of a SmartToken"""
        db = get_db()
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
        
        update_data = {
            "payment_status": payment_status,
            "updated_at": datetime.utcnow()
        }
        
        if payment_method:
            update_data["payment_method"] = payment_method
        
        token_ref.update(update_data)
        return True
    
    @staticmethod
    def get_queue_status(doctor_id: str, token_number: int = None, appointment_date: datetime = None) -> Dict:
        """Get queue status for a doctor and specific token position
        
        Args:
            doctor_id: ID of the doctor
            token_number: Optional token number to get position for
            appointment_date: The appointment date to check against current date
            
        Returns:
            Dict containing queue status with keys:
            - current_token: Currently serving token number
            - total_queue: Total active tokens in queue
            - people_ahead: Number of people ahead of specified token
            - estimated_wait_time: Estimated wait time in minutes
            - is_future_appointment: Boolean indicating if appointment is in future
        """
        db = get_db()
        today = datetime.utcnow().date()

        # Doctor leave / pause should hide wait-time to prevent UI confusion.
        doctor_unavailable = False
        try:
            doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
            dsnap = doctor_ref.get()
            d = dsnap.to_dict() if getattr(dsnap, "exists", False) else {}
            status_lower = str(d.get("status") or "").lower()
            if status_lower == "on_leave" or bool(d.get("queue_paused")) or bool(d.get("paused")):
                doctor_unavailable = True
        except Exception:
            doctor_unavailable = False

        # Normalize appointment_date (handle None, Timestamp-like, or string gracefully)
        def _to_date(dt_val):
            """Best-effort conversion of Firestore Timestamp/ISO string/python datetime to date.

            We avoid depending on private Firestore helpers and instead:
            - accept datetime -> date
            - accept date as-is
            - accept Firestore Timestamp objects via their to_datetime() method
            - accept ISO-like strings via fromisoformat
            """
            try:
                from datetime import datetime as _dt, date as _date  # local import to avoid top-level churn
                if dt_val is None:
                    return None
                # Already a python datetime
                if isinstance(dt_val, datetime):
                    return dt_val.date()
                # Already a python date
                if isinstance(dt_val, _date):
                    return dt_val
                # Firestore Timestamp commonly exposes to_datetime()
                to_dt = getattr(dt_val, "to_datetime", None)
                if callable(to_dt):
                    try:
                        return to_dt().date()
                    except Exception:
                        pass
                # Fallback: try ISO string
                try:
                    return _dt.fromisoformat(str(dt_val)).date()
                except Exception:
                    return None
            except Exception:
                return None

        appt_date_only = _to_date(appointment_date)
        # Determine which calendar date to use for queue grouping. If a specific
        # appointment_date is provided, we must group by that date to avoid
        # timezone drift and midnight boundary issues. Otherwise, fall back to UTC today.
        target_date = appt_date_only or today

        # If appointment is in the future, treat as future regardless of server TZ
        if appt_date_only and appt_date_only > today:
            return {
                "current_token": 0,
                "total_queue": 0,
                "people_ahead": 0,
                "estimated_wait_time": None if doctor_unavailable else 0,
                "is_future_appointment": True,
                "doctor_unavailable": doctor_unavailable,
            }

        # Get all tokens for this doctor (limit keeps memory bounded)
        tokens_ref = db.collection(COLLECTIONS["TOKENS"])
        query = tokens_ref.where("doctor_id", "==", doctor_id).limit(500)

        # Filter for target_date's non-cancelled/non-completed tokens in memory
        # Only include tokens that opted-in for live queue updates.
        tokens = []
        for doc in query.stream():
            token_data = doc.to_dict() or {}
            # Ignore non-opted-in tokens
            if not bool(token_data.get("queue_opt_in")):
                continue
            # Normalize appointment_date
            appt = token_data.get("appointment_date")
            appt_date = None
            try:
                if isinstance(appt, datetime):
                    appt_date = appt.date()
                else:
                    to_dt = getattr(appt, "to_datetime", None)
                    if callable(to_dt):
                        appt_date = to_dt().date()
                    else:
                        from datetime import datetime as _dt
                        appt_date = _dt.fromisoformat(str(appt)).date()
            except Exception:
                appt_date = None
            if appt_date != target_date:
                continue

            # Normalize status to a lowercase string value
            raw_status = token_data.get("status")
            status_val = str(getattr(raw_status, "value", raw_status) or "").lower()

            # Skip non-queue tokens
            if status_val in ["cancelled", "completed", "rescheduled"]:
                continue
            tokens.append(token_data)

        # Stable ordering by token number
        try:
            tokens.sort(key=lambda x: int(x.get("token_number") or 0))
        except Exception:
            pass

        total_queue = len(tokens)
        people_ahead = 0
        estimated_wait_time = 0

        if total_queue > 0:
            # Current serving token = first active in today's list
            current_token = int(tokens[0].get("token_number", 0))

            # If specific token number provided, compute position among today's tokens
            if token_number is not None:
                token_found = False
                for i, token in enumerate(tokens):
                    if int(token.get("token_number", -1)) == int(token_number):
                        # i is 0-based index relative to current serving position
                        people_ahead = max(0, i)
                        estimated_wait_time = people_ahead * int(AVG_CONSULTATION_TIME_MINUTES or 5)
                        token_found = True
                        break

                # If the requested token isn't in today's active queue, keep defaults (0)
                if not token_found:
                    people_ahead = 0
                    estimated_wait_time = 0

        # Derive a 1-based queue_position for UI clarity.
        # Only assign when we actually matched a token_number; otherwise 0.
        queue_position = 0
        try:
            if total_queue > 0 and token_number is not None:
                # If people_ahead is derived from a matched token, it's >= 0; else keep 0
                queue_position = int(people_ahead) + 1 if people_ahead > 0 or any(
                    int(t.get("token_number", -1)) == int(token_number) for t in tokens
                ) else 0
        except Exception:
            queue_position = 0

        if doctor_unavailable:
            current_token = 0
            people_ahead = 0
            queue_position = 0
            estimated_wait_time = None

        return {
            "current_token": current_token,
            "total_queue": total_queue,
            "people_ahead": people_ahead,
            "queue_position": queue_position,
            "estimated_wait_time": None if doctor_unavailable else estimated_wait_time,
            "is_future_appointment": False,
            "doctor_unavailable": doctor_unavailable,
        }
    
    @staticmethod
    def cancel_token(token_id: str, reason: str = None) -> bool:
        """Cancel a SmartToken"""
        db = get_db()
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
        
        update_data = {
            "status": "cancelled",
            "cancellation_reason": reason,
            "cancelled_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        token_ref.update(update_data)
        return True