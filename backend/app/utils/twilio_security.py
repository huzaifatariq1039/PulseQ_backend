import os
from functools import wraps
from fastapi import Request, HTTPException, status
from twilio.request_validator import RequestValidator
from app.config import TWILIO_AUTH_TOKEN

def validate_twilio_request(request: Request, body: bytes, signature: str, url: str):
    """
    Validates that the incoming request is actually from Twilio.
    """
    if not TWILIO_AUTH_TOKEN:
        # If not configured, we allow it (development mode)
        # In production, this should be mandatory
        if os.getenv("ENVIRONMENT") == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Twilio Auth Token not configured in production"
            )
        return True

    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    
    # Twilio's validator needs the parameters from the form body
    # FastAPI's Request.form() provides this, but we need it as a dict
    from urllib.parse import parse_qs
    params = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
    
    if not validator.validate(url, params, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature"
        )
    return True
