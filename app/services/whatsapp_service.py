
from twilio.rest import Client
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
import logging

logger = logging.getLogger(__name__)

def send_queue_message(phone: str, name: str, position: int, wait_time: int, doctor_name: str = "N/A", hospital_name: str = "PulseQ Clinic", room_number: str = "Room 1"):
    """
    Sends a WhatsApp message to the patient using the approved PulseQ template.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp message.")
        return

    try:
        if not phone:
            logger.warning("No phone number provided. Skipping WhatsApp message.")
            return None

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Ensure phone is in the correct format for WhatsApp
        formatted_phone = str(phone)
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        # Construct the message body to EXACTLY match the approved template in the image
        message_body = f"""
Apki appointment book ho chuki h!

Doctor: {doctor_name}
Patient: {name}
Hospital: {hospital_name}
Room Number: {room_number}
Estimated Time: {wait_time}

Reply YES to receive live updates.

PulseQ
"""
        
        # Ensure FROM number is in correct WhatsApp format
        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        message = client.messages.create(
            from_=from_number,
            to=formatted_phone,
            body=message_body.strip()
        )
        logger.info(f"WhatsApp template message sent to {formatted_phone}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {phone}: {e}")
        return None

async def send_template_message(phone: str, template_name: str, params: list):
    """
    Sends a WhatsApp template message using Twilio.
    Note: Twilio handles templates via their Content API or pre-approved messages.
    For simplicity, this function simulates sending a template by constructing a body.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping template message.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        formatted_phone = phone
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        # Ensure FROM number is in correct WhatsApp format
        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        # In a real production environment, you would use Twilio's Content SID.
        # Here we construct the body based on the template name and params.
        body = f"Template: {template_name} | Params: {', '.join(map(str, params))}"
        
        message = client.messages.create(
            from_=from_number,
            to=formatted_phone,
            body=body
        )
        logger.info(f"WhatsApp template message sent to {formatted_phone}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp template message to {phone}: {e}")
        return None
