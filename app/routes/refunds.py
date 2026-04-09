from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any
from app.models import (
    RefundResponse, RefundStatus, RefundMethod, ActivityType
)
from app.database import get_db
from sqlalchemy.orm import Session
from app.db_models import User, Token, ActivityLog # Assuming Refund and Wallet models exist
from app.security import get_current_active_user
from app.services.refund_service import RefundService
from datetime import datetime
import uuid

router = APIRouter(prefix="/refunds", tags=["Refunds"])

async def create_activity_log(db: Session, user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs in PostgreSQL"""
    activity = ActivityLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        activity_type=activity_type.value if hasattr(activity_type, 'value') else str(activity_type),
        description=description,
        metadata=metadata or {},
        created_at=datetime.utcnow()
    )
    db.add(activity)
    db.commit()

@router.get("/", response_model=List[RefundResponse])
async def get_user_refunds(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get all refunds for the current user from PostgreSQL"""
    from app.db_models import Refund
    refunds_objs = db.query(Refund).filter(Refund.user_id == current_user.user_id).order_by(Refund.created_at.desc()).all()
    
    return [RefundResponse(**{k: v for k, v in r.__dict__.items() if not k.startswith('_')}) for r in refunds_objs]

@router.get("/{refund_id}", response_model=RefundResponse)
async def get_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get refund details by ID from PostgreSQL"""
    from app.db_models import Refund
    refund = db.query(Refund).filter(Refund.id == refund_id).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return RefundResponse(**{k: v for k, v in refund.__dict__.items() if not k.startswith('_')})

@router.get("/token/{token_id}")
async def get_refund_by_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get refund information for a specific token from PostgreSQL"""
    from app.db_models import Refund
    refund = db.query(Refund).filter(Refund.token_id == token_id).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="No refund found for this token")
    
    if refund.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return RefundResponse(**{k: v for k, v in refund.__dict__.items() if not k.startswith('_')})

@router.put("/{refund_id}/status")
async def update_refund_status(
    refund_id: str,
    new_status: RefundStatus,
    transaction_id: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Update refund status (for admin use) in PostgreSQL"""
    # TODO: Add admin role check
    from app.db_models import Refund
    refund = db.query(Refund).filter(Refund.id == refund_id).first()
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")

    refund.status = new_status.value
    if transaction_id:
        refund.transaction_id = transaction_id
    refund.updated_at = datetime.utcnow()
    db.commit()
    
    # Create activity log
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.REFUND_PROCESSED,
        f"Refund status updated to {new_status.value}",
        {
            "refund_id": refund_id,
            "new_status": new_status.value,
            "transaction_id": transaction_id
        }
    )
    
    return {"message": "Refund status updated successfully"}

@router.get("/wallet/balance")
async def get_wallet_balance(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user's SmartToken wallet balance from PostgreSQL"""
    from app.db_models import Wallet
    wallet = db.query(Wallet).filter(Wallet.user_id == current_user.user_id).first()
    
    if wallet:
        return {
            "wallet_id": wallet.id,
            "balance": wallet.balance,
            "currency": "PKR",
            "last_updated": wallet.updated_at
        }
    else:
        return {
            "wallet_id": None,
            "balance": 0,
            "currency": "PKR",
            "last_updated": None
        }
