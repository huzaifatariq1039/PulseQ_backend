"""
Token generation alias router for frontend compatibility.
Frontend calls: /api/v1/patients/token/generate
This provides that exact endpoint.
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from app.database import get_db
from app.security import get_current_active_user
from app.routes.tokens import generate_token_by_selection

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
