import os
from typing import Any, Dict, Optional

import httpx


NOTIFICATION_SERVICE_BASE_URL = os.getenv("NOTIFICATION_SERVICE_BASE_URL", "http://127.0.0.1:5055").rstrip("/")


async def _post(path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best-effort POST to Node notification service. Never raises to callers."""
    url = f"{NOTIFICATION_SERVICE_BASE_URL}{path}"
    timeout = float(os.getenv("NOTIFICATION_SERVICE_TIMEOUT_SECONDS", "3"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            # We don't want this to break main flows; just return structured info.
            return {
                "ok": 200 <= resp.status_code < 300,
                "status_code": resp.status_code,
                "data": resp.json() if resp.content else None,
            }
    except Exception:
        return None


async def schedule_token_messages(token: Dict[str, Any]) -> None:
    """Notify Node service to schedule WhatsApp messages for a token."""
    # payload contract expected by /schedule/token in node-notification-service
    payload = {
        "token_id": token.get("id") or token.get("token_id"),
        "patient_id": token.get("patient_id"),
        "phone": token.get("patient_phone") or token.get("phone"),
        "appointment_time": (token.get("appointment_date") or token.get("appointment_time")),
        "queue_position": token.get("queue_position"),
    }
    # Fire and forget
    await _post("/schedule/token", payload)


async def send_queue_alert(token: Dict[str, Any]) -> None:
    """Immediate queue alert: queue_position<=4 OR wait_time<=15."""
    payload = {
        "token_id": token.get("id") or token.get("token_id"),
        "patient_id": token.get("patient_id"),
        "phone": token.get("patient_phone") or token.get("phone"),
    }
    await _post("/events/queue-alert", payload)


async def send_final_call(token: Dict[str, Any]) -> None:
    """Immediate final call: patient is being called to doctor."""
    payload = {
        "token_id": token.get("id") or token.get("token_id"),
        "patient_id": token.get("patient_id"),
        "phone": token.get("patient_phone") or token.get("phone"),
    }
    await _post("/events/final-call", payload)

