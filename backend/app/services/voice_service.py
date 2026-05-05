from typing import Optional, Dict
from app.data.mock_voice_data import USERS, DOCTORS, HOSPITALS, QUEUE


class VoiceService:
    """Service layer for voice assistant intents.
    In future, replace mock data usage with real DB queries.
    """

    @staticmethod
    def get_snapshot(user_id: str) -> Optional[Dict]:
        """Return a consolidated snapshot for the authenticated user for 'today'."""
        u = USERS.get(user_id)
        if not u:
            return None
        doctor = DOCTORS.get(u.get("assigned_doctor_id"), {})
        hospital = HOSPITALS.get(u.get("hospital_id"), {})
        token = {
            "token_number": u.get("token_number"),
            "appointment_date": u.get("appointment_date"),
        }
        queue = {
            "people_ahead": u.get("people_ahead"),
            "estimated_wait_minutes": u.get("estimated_wait_minutes"),
            "now_serving": u.get("now_serving"),
            "total_queue": u.get("total_queue"),
        }
        doc = {
            "name": doctor.get("name", "Unknown"),
            "specialization": doctor.get("specialization", "Unknown"),
        }
        hosp = {
            "name": hospital.get("name", "Unknown"),
            "address": hospital.get("address", "Not available"),
            "address_short": hospital.get("address_short", hospital.get("address", "Not available")),
            "maps_link": hospital.get("maps_link", "https://maps.google.com"),
        }
        return {"queue": queue, "token": token, "doctor": doc, "hospital": hosp}

    @staticmethod
    def get_hospital_location() -> Dict:
        hosp = HOSPITALS.get("hosp_1") or {}
        return {
            "name": hosp.get("name", "Unknown"),
            "address": hosp.get("address", "Not available"),
            "address_short": hosp.get("address_short", hosp.get("address", "Not available")),
            "maps_link": hosp.get("maps_link", "https://maps.google.com"),
        }

    @staticmethod
    def get_next_token() -> Dict:
        return {"next_token_number": QUEUE.get("next_token_number", "N/A")}

    # Placeholder for future DB integration
    @staticmethod
    async def resolve_from_db(intent: str, user_id: Optional[str]) -> Optional[Dict]:
        """Future-ready: implement actual DB-backed resolution here."""
        return None
