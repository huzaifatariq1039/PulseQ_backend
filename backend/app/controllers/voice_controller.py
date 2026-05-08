from fastapi import HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.voice_service import VoiceService


SUPPORTED_INTENTS = {"queue_status", "doctor_info", "hospital_location", "next_token"}


class VoiceIntentRequest(BaseModel):
    intent: str
    locale: Optional[str] = None  # e.g., "ur-PK" or default English


def _tts_language(locale: Optional[str]) -> str:
    return "ur-PK" if (locale or "").lower() == "ur-pk" else "en-US"


def _format_message(intent: str, data: Dict[str, Any], locale: Optional[str]) -> str:
    is_urdu = (locale or "").lower() == "ur-pk"
    if intent == "queue_status":
        if is_urdu:
            return f"آپ سے پہلے {data['queue']['people_ahead']} افراد ہیں۔ اندازاً انتظار {data['queue']['estimated_wait_minutes']} منٹ ہے۔"
        return (
            f"There are {data['queue']['people_ahead']} people ahead of you. "
            f"Estimated wait is {data['queue']['estimated_wait_minutes']} minutes."
        )
    if intent == "doctor_info":
        if is_urdu:
            return f"آپ کے ڈاکٹر {data['doctor']['name']} ہیں، {data['doctor']['specialization']}."
        return f"Your doctor is {data['doctor']['name']}, {data['doctor']['specialization']}."
    if intent == "hospital_location":
        if is_urdu:
            return f"آپ کا ہسپتال {data['hospital']['name']} ہے، پتہ: {data['hospital']['address_short']}."
        return f"Your hospital is {data['hospital']['name']}, address: {data['hospital']['address_short']}."
    if intent == "next_token":
        if is_urdu:
            return f"اس وقت {data['queue']['now_serving']} چل رہا ہے۔ آپ کا ٹوکن {data['token']['token_number']} ہے۔"
        return f"Now serving {data['queue']['now_serving']}. Your token is {data['token']['token_number']}."
    return ""


def _no_active_token_message(locale: Optional[str]) -> str:
    return "آج کا کوئی ایکٹو ٹوکن موجود نہیں۔" if (locale or "").lower() == "ur-pk" else "No active token for today."


def _bad_intent_message(locale: Optional[str]) -> str:
    return "Invalid or unsupported intent."  # Same in both for now


async def handle_intent(payload: VoiceIntentRequest, current_user) -> Dict[str, Any]:
    # Validate intent
    if not payload.intent or payload.intent not in SUPPORTED_INTENTS:
        raise HTTPException(status_code=400, detail={"success": False, "message": _bad_intent_message(payload.locale)})

    intent = payload.intent
    locale = payload.locale or "en-US"
    tts = _tts_language(locale)

    # Future: try DB-backed resolver first
    db_result = await VoiceService.resolve_from_db(intent, getattr(current_user, "user_id", None))
    snapshot = None
    if db_result:
        snapshot = db_result
    else:
        # Fallback to mock snapshot for authenticated user
        user_id = getattr(current_user, "user_id", None)
        if intent in {"queue_status", "doctor_info", "next_token"}:
            snapshot = VoiceService.get_snapshot(user_id) if user_id else None
            if not snapshot or not snapshot.get("token", {}).get("token_number"):
                # No active token today
                raise HTTPException(status_code=404, detail={"success": False, "message": _no_active_token_message(locale)})
        elif intent == "hospital_location":
            hosp = VoiceService.get_hospital_location()
            snapshot = {"hospital": hosp}

    # Build message
    message = _format_message(intent, snapshot, locale)

    # Build success response shape
    resp: Dict[str, Any] = {
        "success": True,
        "message": message,
        "tts_language": tts,
        "data": snapshot,
    }
    return resp
