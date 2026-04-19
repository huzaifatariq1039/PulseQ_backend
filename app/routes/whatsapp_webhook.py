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

    # Normalize phone number to find the token
    digits = "".join([c for c in user_number if c.isdigit()])
    
    # Standard Pakistan local suffix is the last 10 digits (e.g., 3314044494)
    local_suffix = digits[-10:] if len(digits) >= 10 else digits
    
    # Also try to match with +92 prefix if not present
    full_norm = f"+92{local_suffix}" if not user_number.startswith("+") else user_number
    if not full_norm.startswith("+"):
        full_norm = "+" + digits

    print(f"Incoming Twilio WhatsApp: {user_number} → {message}")
    print(f"[DEBUG] Search Criteria: local_suffix={local_suffix}, digits={digits}, full_norm={full_norm}")

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
    
    print(f"[DEBUG] SQL Query generated")
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
            print(f"[DEBUG] Token found but excluded. ID: {any_token.id}, Status: {any_token.status}")
        else:
            print(f"[DEBUG] No tokens found at all for this phone search.")
            # Let's check if the user even exists
            user_exists = db.query(User).filter(
                or_(
                    User.phone.like(f"%{local_suffix}"),
                    User.phone.like(f"%{digits}")
                )
            ).first()
            if user_exists:
                print(f"[DEBUG] User exists with ID {user_exists.id} but has no tokens.")
            else:
                print(f"[DEBUG] No user found with phone matching {local_suffix} or {digits}.")
            
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    print(f"[DEBUG] Found active token: {token.id}, Status: {token.status}, Patient: {token.patient_name or 'N/A'}")

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
