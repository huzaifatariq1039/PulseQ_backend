from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.models import (
    RefundResponse, RefundStatus, RefundMethod, ActivityType
)
from app.database import get_db
from app.config import COLLECTIONS
from app.security import get_current_active_user
from app.services.refund_service import RefundService
from datetime import datetime

router = APIRouter(prefix="/refunds", tags=["Refunds"])

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs"""
    db = get_db()
    activities_ref = db.collection("activities")
    
    activity_ref = activities_ref.document()
    activity_data = {
        "id": activity_ref.id,
        "user_id": user_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.utcnow()
    }
    
    activity_ref.set(activity_data)

@router.get("/", response_model=List[RefundResponse])
async def get_user_refunds(current_user = Depends(get_current_active_user)):
    """Get all refunds for the current user"""
    db = get_db()
    refunds_ref = db.collection("refunds")
    
    # Use simple query to avoid composite index requirement
    query = refunds_ref.where("user_id", "==", current_user.user_id)
    
    refunds = []
    refund_docs = []
    
    # Get all documents first
    for doc in query.stream():
        refund_data = doc.to_dict()
        refund_data["doc_id"] = doc.id
        refund_docs.append(refund_data)
    
    # Sort in memory by created_at descending
    refund_docs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
    
    for refund_data in refund_docs:
        refunds.append(RefundResponse(**refund_data))
    
    return refunds

@router.get("/{refund_id}", response_model=RefundResponse)
async def get_refund(
    refund_id: str,
    current_user = Depends(get_current_active_user)
):
    """Get refund details by ID"""
    db = get_db()
    refund_ref = db.collection("refunds").document(refund_id)
    refund_doc = refund_ref.get()
    
    if not refund_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refund not found"
        )
    
    refund_data = refund_doc.to_dict()
    
    # Check if user owns this refund
    if refund_data.get("user_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return RefundResponse(**refund_data)

@router.get("/token/{token_id}")
async def get_refund_by_token(
    token_id: str,
    current_user = Depends(get_current_active_user)
):
    """Get refund information for a specific token"""
    refund_data = RefundService.get_refund_by_token_id(token_id)
    
    if not refund_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No refund found for this token"
        )
    
    # Check if user owns this refund
    if refund_data.get("user_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return RefundResponse(**refund_data)

@router.put("/{refund_id}/status")
async def update_refund_status(
    refund_id: str,
    new_status: RefundStatus,
    transaction_id: str = None,
    current_user = Depends(get_current_active_user)
):
    """Update refund status (for admin use)"""
    # TODO: Add admin role check
    
    success = RefundService.update_refund_status(refund_id, new_status, transaction_id)
    
    if success:
        # Create activity log
        await create_activity_log(
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
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update refund status"
        )

@router.get("/wallet/balance")
async def get_wallet_balance(current_user = Depends(get_current_active_user)):
    """Get user's SmartToken wallet balance"""
    db = get_db()
    wallets_ref = db.collection("wallets")
    
    query = wallets_ref.where("user_id", "==", current_user.user_id).limit(1)
    wallet_docs = list(query.stream())
    
    if wallet_docs:
        wallet_data = wallet_docs[0].to_dict()
        return {
            "wallet_id": wallet_data["id"],
            "balance": wallet_data.get("balance", 0),
            "currency": "PKR",
            "last_updated": wallet_data.get("updated_at")
        }
    else:
        return {
            "wallet_id": None,
            "balance": 0,
            "currency": "PKR",
            "last_updated": None
        }
