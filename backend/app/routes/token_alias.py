"""
Token alias router for frontend compatibility.
Frontend calls: /api/v1/patients/token/*
This provides those exact endpoints.
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.security import get_current_active_user
from app.routes.tokens import generate_token_by_selection, get_my_active_token, _to_smart_token_response
from app.db_models import Token, Doctor, Hospital
from app.services.token_service import SmartTokenService

# Create router with the exact prefix the frontend expects
token_alias_router = APIRouter()

@token_alias_router.post("/token/generate")
async def token_generate_alias(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    """
    Alias endpoint matching frontend path: /api/v1/patients/token/generate
    Delegates to the actual token generation logic.
    """
    return await generate_token_by_selection(payload, db, current_user)


@token_alias_router.get("/token/my-active")
async def token_my_active_alias(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    """
    Alias endpoint matching frontend path: /api/v1/patients/token/my-active
    Returns the most recent active token for the current user.
    """
    from app.routes.tokens import get_my_active_token
    return await get_my_active_token(db=db, current_user=current_user)


@token_alias_router.get("/token/my-active-details")
async def token_my_active_details_alias(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    """
    Alias endpoint matching frontend path: /api/v1/patients/token/my-active-details
    Returns the most recent active token with full appointment details including doctor, hospital, and queue status.
    """
    from app.routes.tokens import _to_smart_token_response
    from app.db_models import User
    
    # Query for the most recent active token
    token = db.query(Token).filter(
        Token.patient_id == current_user.user_id,
        Token.status.notin_(["cancelled", "completed"])
    ).order_by(Token.created_at.desc()).first()

    if not token:
        raise HTTPException(status_code=404, detail="No active token found")

    # If patient_name or patient_phone is null, fetch from User table
    if not token.patient_name or not token.patient_phone:
        user = db.query(User).filter(User.id == current_user.user_id).first()
        if user:
            if not token.patient_name:
                token.patient_name = user.name
            if not token.patient_phone:
                token.patient_phone = user.phone
            # Optional: Update the token in DB to avoid future lookups
            try:
                db.commit()
            except Exception:
                db.rollback()

    # Get doctor and hospital info
    doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
    hospital = db.query(Hospital).filter(Hospital.id == token.hospital_id).first()

    # Get queue status
    queue = SmartTokenService.get_queue_status(token.doctor_id, token.token_number, token.appointment_date)

    return {
        "token": _to_smart_token_response(token),
        "doctor": {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')} if doctor else {},
        "hospital": {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')} if hospital else {},
        "queue": queue
    }


@token_alias_router.post("/token/cancel")
async def token_cancel_alias(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    """
    Alias endpoint matching frontend path: /api/v1/patients/token/cancel
    Cancels a token and returns cancellation details with refund information.
    """
    from app.routes.tokens import cancel_token_logic
    from app.models import TokenCancellationRequest, CancellationResponse, CancellationReason, RefundMethod
    
    token_id = payload.get("token_id")
    if not token_id:
        raise HTTPException(status_code=400, detail="token_id is required")
    
    # Parse cancellation request
    reason = payload.get("reason", "other_reason")
    refund_method = payload.get("refund_method", "smarttoken_wallet")
    
    try:
        reason_enum = CancellationReason(reason.lower()) if reason else CancellationReason.OTHER_REASON
    except Exception:
        reason_enum = CancellationReason.OTHER_REASON
    
    try:
        refund_method_enum = RefundMethod(refund_method.lower()) if refund_method else RefundMethod.SMARTTOKEN_WALLET
    except Exception:
        refund_method_enum = RefundMethod.SMARTTOKEN_WALLET
    
    cancellation_req = TokenCancellationRequest(
        reason=reason_enum,
        refund_method=refund_method_enum
    )
    
    result = await cancel_token_logic(token_id, cancellation_req, db, current_user)
    
    return {
        "success": True,
        "message": result.get("message", "Token cancelled successfully"),
        "token_id": result.get("token_id"),
        "refund_id": result.get("refund_id"),
        "data": result
    }
