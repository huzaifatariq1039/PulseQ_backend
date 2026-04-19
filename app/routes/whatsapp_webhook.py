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
from app.utils.twilio_security import validate_twilio_request
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

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
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Twilio WhatsApp Webhook to handle YES/NO confirmations.
    Includes production security validation.
    """
    # 1. Security Validation (Twilio Signature)
    signature = request.headers.get("X-Twilio-Signature")
    url = str(request.url)
    
    # We need the raw body for signature validation
    body = await request.body()
    
    # Validate if in production or if signature is provided
    is_prod = os.getenv("ENVIRONMENT") == "production"
    if is_prod or signature:
        if not signature:
            logger.warning("Missing X-Twilio-Signature in production request")
            raise HTTPException(status_code=403, detail="Missing X-Twilio-Signature")
        validate_twilio_request(request, body, signature, url)

    # 2. Parse Form Data
    from urllib.parse import parse_qs
    form_data = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
    
    From = form_data.get("From", "")
    Body = form_data.get("Body", "")

    user_number = From.replace("whatsapp:", "").strip()
    message = Body.strip().lower()

    # Normalize phone number to find the token
    digits = "".join([c for c in user_number if c.isdigit()])
    
    # Standard Pakistan local suffix is the last 10 digits (e.g., 3314044494)
    local_suffix = digits[-10:] if len(digits) >= 10 else digits
    
    # Also try to match with +92 prefix if not present
    full_norm = f"+92{local_suffix}" if not user_number.startswith("+") else user_number
    if not full_norm.startswith("+"):
        full_norm = "+" + digits

    logger.info(f"Incoming Twilio WhatsApp: {user_number} → {message}")
    logger.debug(f"Search Criteria: local_suffix={local_suffix}, digits={digits}, full_norm={full_norm}")

    twiml_response = MessagingResponse()

    # Find the latest active token for this user
    # We search by patient_phone in Token table OR by User.phone via relationship
    query = db.query(Token).outerjoin(User, Token.patient_id == User.id).filter(
        or_(
            Token.patient_phone.like(f"%{local_suffix}"),
            Token.patient_phone.like(f"%{digits}"),
            User.phone.like(f"%{local_suffix}"),
            User.phone.like(f"%{digits}")
        )
    ).filter(
        ~Token.status.in_(["cancelled", "completed"])
    ).order_by(Token.created_at.desc())
    
    token = query.first()

    if not token:
        # Let's see what tokens DO exist for this number regardless of status
        any_token = db.query(Token).outerjoin(User, Token.patient_id == User.id).filter(
            or_(
                Token.patient_phone.like(f"%{local_suffix}"),
                Token.patient_phone.like(f"%{digits}"),
                User.phone.like(f"%{local_suffix}"),
                User.phone.like(f"%{digits}")
            )
        ).first()
        
        if any_token:
            logger.info(f"Token found but excluded. ID: {any_token.id}, Status: {any_token.status}")
        else:
            logger.info(f"No tokens found at all for this phone search: {local_suffix}")
            # Let's check if the user even exists
            user_exists = db.query(User).filter(
                or_(
                    User.phone.like(f"%{local_suffix}"),
                    User.phone.like(f"%{digits}")
                )
            ).first()
            if user_exists:
                logger.info(f"User exists with ID {user_exists.id} but has no tokens.")
            else:
                logger.info(f"No user found with phone matching {local_suffix} or {digits}.")
            
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    logger.info(f"Found active token: {token.id}, Status: {token.status}, Patient: {token.patient_name or 'N/A'}")

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
            from app.services.queue_management_service import QueueManagementService
            await QueueManagementService.recalculate_positions(token.doctor_id, token.hospital_id, token.appointment_date)
        except Exception as e:
            logger.error(f"Error recalculating queue positions: {e}")

        twiml_response.message("Your appointment has been cancelled. Thank you.")

    else:
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")
