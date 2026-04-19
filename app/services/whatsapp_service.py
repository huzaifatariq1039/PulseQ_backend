
from twilio.rest import Client
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
import logging

logger = logging.getLogger(__name__)

def send_queue_message(phone: str, name: str, position: int, wait_time: int):
    """
    Sends a WhatsApp message to the patient using Twilio.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp message.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Ensure phone is in the correct format for WhatsApp
        # Twilio requires the format 'whatsapp:+[country_code][number]'
        formatted_phone = phone
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        message_body = f"""
Hello {name},
Your queue position: {position}
Estimated wait: {wait_time} minutes

Reply YES to confirm
Reply NO to cancel
"""
        
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=formatted_phone,
            body=message_body.strip()
        )
        logger.info(f"WhatsApp message sent to {formatted_phone}: SID {message.sid}")
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

        # In a real production environment, you would use Twilio's Content SID.
        # Here we construct the body based on the template name and params.
        body = f"Template: {template_name} | Params: {', '.join(map(str, params))}"
        
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=formatted_phone,
            body=body
        )
        logger.info(f"WhatsApp template message sent to {formatted_phone}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp template message to {phone}: {e}")
        return None
