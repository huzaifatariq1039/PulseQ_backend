from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from app.security import get_current_active_user
from app.routes.tokens import create_token
from app.models import TokenCreateSpec
from app.utils.idempotency import Idempotency
from app.utils.responses import ok, fail
from app.utils.audit import log_action, get_user_role

router = APIRouter()


class HeaderTokenCreate(BaseModel):
    doctor_id: str
    hospital_id: str
    appointment_date: str  # YYYY-MM-DD in clinic local timezone


@router.post("/tokens/create-idempotent")
async def create_token_with_header(payload: HeaderTokenCreate, request: Request, current_user = Depends(get_current_active_user)):
    """Create token using Idempotency-Key header; wraps existing create_token logic.

    Body takes doctor_id, hospital_id, appointment_date.
    Idempotency-Key header is required for idempotent behavior.
    """
    key = request.headers.get(Idempotency.HEADER_NAME)
    if not key:
        return fail("Missing Idempotency-Key header", status_code=status.HTTP_400_BAD_REQUEST)
    key = Idempotency.validate_key(key)

    async def _runner():
        spec = TokenCreateSpec(
            doctor_id=payload.doctor_id,
            hospital_id=payload.hospital_id,
            appointment_date=payload.appointment_date,
            idempotency_key=key,
        )
        # Delegate to original create_token implementation
        return await create_token(spec, current_user)  # type: ignore

    result = await Idempotency.get_or_run_async(current_user.user_id, key, action="tokens_create", ttl_minutes=60, runner_async=_runner)
    try:
        # Audit: CREATE_TOKEN
        role = get_user_role(current_user.user_id)
        token_id = None
        if isinstance(result, dict):
            token_id = result.get("id") or result.get("token_id")
        log_action(current_user.user_id, role, action="CREATE_TOKEN", token_id=token_id, extra={"doctor_id": payload.doctor_id, "hospital_id": payload.hospital_id})
    except Exception:
        pass
    return ok(data=result, message="Token created")
