import secrets
import string
from datetime import datetime, timezone
from typing import Tuple, Dict
from sqlalchemy.orm import Session
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
        """Generate next token number starting from 1 each day, scoped per hospital and doctor."""
        db = get_db()

        try:
            day_key = target_date.strftime("%Y%m%d")
        except Exception:
            from datetime import datetime as _dt
            day_key = _dt.utcnow().strftime("%Y%m%d")
        counter_id = f"tokens_{hospital_id}_{doctor_id}_{day_key}"
        doc_ref = db.collection(COLLECTIONS["COUNTERS"]).document(counter_id)

        try:
            try:
                from firebase_admin import firestore as fb_fs
                inc = fb_fs.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                return int(data.get("seq", 1))
            except Exception:
                from google.cloud import firestore as gcf
                inc = gcf.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                return int(data.get("seq", 1))
        except Exception:
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

        try:
            try:
                from firebase_admin import firestore as fb_fs
                inc = fb_fs.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                seq = int(data.get("seq", 1))
            except Exception:
                from google.cloud import firestore as gcf
                inc = gcf.Increment(1)
                doc_ref.set({"seq": inc, "updated_at": datetime.utcnow()}, merge=True)
                snap = doc_ref.get()
                data = snap.to_dict() or {}
                seq = int(data.get("seq", 1))
        except Exception:
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
    def get_queue_status(doctor_id: str, token_number: int = None, appointment_date: datetime = None, db: Session = None) -> Dict:
        """Get queue status for a doctor and specific token position using PostgreSQL"""
        from app.database import get_db as get_db_session
        from app.db_models import Token, Doctor
        from sqlalchemy import and_, func

        should_close = False
        if db is None:
            db = next(get_db_session())
            should_close = True

        try:
            today = datetime.now(timezone.utc).date()

            # Check doctor availability
            doctor_unavailable = False
            try:
                doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
                if doctor:
                    status_lower = str(doctor.status.value if hasattr(doctor.status, 'value') else doctor.status or "").lower()
                    if status_lower == "on_leave" or bool(getattr(doctor, "queue_paused", False)) or bool(getattr(doctor, "paused", False)):
                        doctor_unavailable = True
            except Exception:
                doctor_unavailable = False

            # Determine target date
            target_date = today
            if appointment_date:
                if isinstance(appointment_date, datetime):
                    if appointment_date.tzinfo is not None:
                        target_date = appointment_date.astimezone(timezone.utc).date()
                    else:
                        target_date = appointment_date.date()
                else:
                    try:
                        target_date = datetime.fromisoformat(str(appointment_date).replace('Z', '+00:00')).date()
                    except Exception:
                        target_date = today

            # Future appointment
            if target_date > today:
                return {
                    "current_token_serving": 0,
                    "total_queue": 0,
                    "people_ahead": 0,
                    "queue_position": 0,
                    "estimated_wait_time": None if doctor_unavailable else 0,
                    "is_future_appointment": True,
                    "doctor_unavailable": doctor_unavailable,
                }

            # Get currently CALLED token
            called_token = db.query(Token).filter(
                and_(
                    Token.doctor_id == doctor_id,
                    func.date(Token.appointment_date) == target_date,
                    Token.status == "called"
                )
            ).order_by(Token.token_number.asc()).first()

            current_token_serving = int(called_token.token_number) if called_token else 0

            # Get all WAITING tokens
            waiting_tokens = db.query(Token).filter(
                and_(
                    Token.doctor_id == doctor_id,
                    func.date(Token.appointment_date) == target_date,
                    Token.status.in_(["pending", "waiting", "confirmed"])
                )
            ).order_by(Token.token_number.asc()).all()

            total_queue = len(waiting_tokens)
            people_ahead = 0
            estimated_wait_time = 0
            queue_position = 0

            if token_number is not None:
                for i, t in enumerate(waiting_tokens):
                    if int(t.token_number) == int(token_number):
                        people_ahead = i
                        queue_position = i + 1
                        if t.estimated_wait_time and t.estimated_wait_time > 0:
                            estimated_wait_time = t.estimated_wait_time
                        else:
                            estimated_wait_time = people_ahead * int(AVG_CONSULTATION_TIME_MINUTES or 5)
                        break

            if doctor_unavailable:
                current_token_serving = 0
                people_ahead = 0
                queue_position = 0
                estimated_wait_time = None

            return {
                "current_token_serving": current_token_serving,
                "total_queue": total_queue,
                "people_ahead": people_ahead,
                "queue_position": queue_position,
                "estimated_wait_time": None if doctor_unavailable else estimated_wait_time,
                "is_future_appointment": False,
                "doctor_unavailable": doctor_unavailable,
            }
        finally:
            if should_close:
                db.close()

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