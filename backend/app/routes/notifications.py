from fastapi import APIRouter, Depends, HTTPException
from app.security import get_current_active_user
from app.services.sms_service import send_sms

router = APIRouter(tags=["Notifications"])

@router.post("/send-sms")
async def send_sms_endpoint(to: str, body: str, current_user = Depends(get_current_active_user)):
    """Send a plain SMS using Twilio Messaging Service.

    Intended for admin/testing. For production flows, prefer the rich token endpoints under `/tokens/*/notify/*`.
    """
    if not to or not body:
        raise HTTPException(status_code=400, detail="Both 'to' and 'body' are required")
    result = send_sms(to, body)
    return result
