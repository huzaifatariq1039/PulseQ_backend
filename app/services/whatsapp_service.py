from typing import List, Dict, Any, Optional

from app.services.notification_service import NotificationService


async def send_template_message(
    to: str,
    template_name: str,
    parameters: Optional[List[str]] = None,
    language_code: str = "en_US",
) -> Dict[str, Any]:
    return await NotificationService.send_whatsapp_template(
        phone_number=to,
        template_name=template_name,
        body_parameters=parameters or [],
        language_code=language_code,
    )
