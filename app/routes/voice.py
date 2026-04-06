from fastapi import APIRouter, Depends
from app.security import get_current_active_user  # Keep pattern; can be toggled by SKIP_AUTH in future
from app.controllers.voice_controller import VoiceIntentRequest, handle_intent

router = APIRouter(prefix="/voice", tags=["Voice Assistant"])


@router.post("/intent")
async def post_voice_intent(
    payload: VoiceIntentRequest,
    # For development/testing you can temporarily bypass auth. Keep for production readiness.
    current_user = Depends(get_current_active_user)
):
    # Server infers user from JWT (current_user)
    return await handle_intent(payload, current_user)
