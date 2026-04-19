import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Form, Response
from twilio.twiml.messaging_response import MessagingResponse

from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db_models import User, Doctor, Hospital, Token
from app.services.whatsapp_service import send_queue_message

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Webhook"])

# PHASE 3: Test Sending Message (Temporary Dummy DB for testing)
patients_db = {
    "whatsapp:+923491394355": {
        "name": "Huzaifa",
        "position": 2,
        "wait_time": 10,
        "status": "waiting"
    }
}


@router.post("/twilio/webhook")
async def twilio_whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Twilio WhatsApp Webhook to handle YES/NO confirmations.
    """
    user_number = From.replace("whatsapp:", "").strip()
    message = Body.strip().lower()

    print(f"Incoming Twilio WhatsApp: {user_number} → {message}")

    twiml_response = MessagingResponse()

    # Normalize phone number to find the token
    digits = "".join([c for c in user_number if c.isdigit()])
    if digits.startswith("92"):
        local_suffix = digits[2:] 
    else:
        local_suffix = digits[-10:]

    # Find the latest active token for this user
    token = db.query(Token).filter(
        or_(
            Token.patient_phone.like(f"%{local_suffix}"),
            Token.patient_phone.like(f"%{digits}")
        )
    ).filter(
        ~Token.status.in_(["cancelled", "completed"])
    ).order_by(Token.created_at.desc()).first()

    if not token:
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    now = datetime.utcnow()

    # ✅ HANDLE ACTIONS
    if message in ["yes", "y"]:
        token.status = "confirmed"
        token.confirmed = True
        token.confirmed_at = now
        token.updated_at = now
        db.commit()
        twiml_response.message("You are confirmed in queue. We’ll notify you soon.")

    elif message in ["no", "n", "cancel"]:
        token.status = "cancelled"
        token.cancelled_at = now
        token.updated_at = now
        db.commit()
        
        # Trigger recalculation for the rest of the queue
        try:
            from app.routes.tokens import _recalculate_token_wait_times
            appt_dt = token.appointment_date
            day_local = appt_dt.date() if appt_dt else now.date()
            _recalculate_token_wait_times(db, token.doctor_id, token.hospital_id, day_local)
        except Exception:
            pass

        twiml_response.message(" Your token has been cancelled.")

    else:
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")
