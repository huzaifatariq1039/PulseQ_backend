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
from app.config import TWILIO_AUTH_TOKEN
from app.utils.twilio_security import validate_twilio_request
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/twilio/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db)
):  
    """
    Twilio WhatsApp Webhook to handle YES/NO confirmations.
    """
    signature = request.headers.get("X-Twilio-Signature","")
    body = await request.body()
    
    webhook_url = "https://oyster-app-notep.ondigitalocean.app/api/v1/webhooks/twilio/webhook"
    is_prod = os.getenv("ENVIRONMENT") == "production"
    if is_prod and signature:
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            from urllib.parse import parse_qs
            form_data = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
            
            if not validator.validate(webhook_url, form_data, signature):
                logger.warning("Invalid Twilio signature")
                raise HTTPException(status_code=403, detail="Invalid Twilio Signature")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Signature validation error: {e}")
            pass

    from urllib.parse import parse_qs
    form_data = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
    
    From = form_data.get("From", "")
    Body = form_data.get("Body", "")

    user_number = From.replace("whatsapp:", "").strip()
    message = Body.strip().lower()

    digits = "".join([c for c in user_number if c.isdigit()])
    local_suffix = digits[-10:] if len(digits) >= 10 else digits
    
    full_norm = f"+92{local_suffix}" if not user_number.startswith("+") else user_number
    if not full_norm.startswith("+"):
        full_norm = "+" + digits

    logger.info(f"Incoming Twilio WhatsApp: {user_number} → {message}")

    twiml_response = MessagingResponse()

    # Find the latest active token for this user
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
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    now = datetime.utcnow()

    # ✅ HANDLE ACTIONS
    if message in ["yes", "y"]:
        token.status = "confirmed"
        token.confirmed = True
        token.confirmed_at = now
        token.updated_at = now
        token.confirmation_status = "confirmed"
        # Opt-in logic
        token.queue_opt_in = True
        token.queue_opted_in_at = now
        db.commit()
        
        # Cancel scheduled reminder jobs
        try:
            from app.services.app_scheduler import get_scheduler
            sch = get_scheduler()
            if sch:
                for job_id in [f"confirm_reminder:{token.id}", f"confirm_final:{token.id}"]:
                    try:
                        sch.remove_job(job_id)
                        logger.info(f"Cancelled scheduled job {job_id} after YES reply")
                    except Exception:
                        pass
        except Exception as e:
            pass
        
        # Send initial Queue Update template upon YES
        try:
            from app.services.whatsapp_service import send_template_message
            phone = user_number.replace("whatsapp:", "")
            
            patients_ahead = db.query(Token).filter(
                Token.doctor_id == token.doctor_id,
                Token.hospital_id == token.hospital_id,
                Token.appointment_date == token.appointment_date,
                Token.queue_position < token.queue_position,
                Token.status.in_(["waiting", "confirmed"])
            ).count()

            await send_template_message(
                phone, 
                "queue_update_alert", 
                [
                    token.patient_name or "Patient", 
                    str(patients_ahead), 
                    f"{token.estimated_wait_time or 0} mins", 
                    token.hospital_name or "Clinic", 
                    str(token.token_number)
                ]
            )
            
            # ✅ FIX: Serialize dictionary AND send the is_webhook_trigger flag!
            try:
                from app.services.message_scheduler import schedule_messages
                token_dict = {k: v for k, v in token.__dict__.items() if not k.startswith('_')}
                await schedule_messages(token_dict, is_webhook_trigger=True)
                logger.info(f"Ongoing queue update sequence scheduled for token {token.id}")
            except Exception as e:
                logger.error(f"Failed to schedule ongoing messages for token {token.id}: {e}")

            return Response(content=str(MessagingResponse()), media_type="application/xml")
        except Exception as e:
            logger.error(f"Failed to send queue_update template: {e}")
            twiml_response.message("Your appointment is confirmed. We will keep you updated.")
            return Response(content=str(twiml_response), media_type="application/xml")

    elif message in ["no", "n", "cancel"]:
        token.status = "cancelled"
        token.cancelled_at = now
        token.updated_at = now
        db.commit()
        
        try:
            from app.services.queue_management_service import QueueManagementService
            await QueueManagementService.recalculate_positions(token.doctor_id, token.hospital_id, token.appointment_date)
        except Exception as e:
            pass

        try:
            from app.services.whatsapp_service import send_template_message
            phone = user_number.replace("whatsapp:", "")
            await send_template_message(phone, "cancelled", [token.patient_name or "Patient"])
        except Exception as e:
            twiml_response.message("Your appointment has been cancelled. Thank you.")
            return Response(content=str(twiml_response), media_type="application/xml")

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    else:
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")