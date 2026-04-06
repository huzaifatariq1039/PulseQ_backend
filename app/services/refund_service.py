from datetime import datetime
from typing import Dict, Optional
from app.database import get_db
from app.config import COLLECTIONS
from app.models import RefundMethod, RefundStatus, CancellationReason

class RefundService:
    """Service for handling refund calculations and processing"""
    
    @staticmethod
    def calculate_refund(amount_or_token: object, cancellation_reason: CancellationReason) -> Dict:
        """Calculate refund based on either a provided base amount (preferred) or a token_id.

        - If amount_or_token is int/float/str-numeric, use it as original_amount directly.
        - Else treat it as token_id, fetch latest payment and use its amount.
        """
        original_amount = 0.0
        # Case 1: numeric base amount provided
        if isinstance(amount_or_token, (int, float)):
            try:
                original_amount = float(amount_or_token)
            except Exception:
                original_amount = 0.0
        else:
            # Accept numeric-like strings too
            if isinstance(amount_or_token, str):
                s = amount_or_token.strip()
                try:
                    original_amount = float(s)
                except Exception:
                    # Treat as token_id and fetch
                    db = get_db()
                    payments_ref = db.collection("payments")
                    # Prefer a successful or most recent record
                    docs = list(payments_ref.where("token_id", "==", s).stream())
                    if docs:
                        # Choose a doc with amount if available
                        chosen = None
                        for d in docs:
                            data = d.to_dict()
                            amt = data.get("amount") if data.get("amount") is not None else data.get("total_amount")
                            if amt is not None:
                                chosen = data
                                break
                        if not chosen:
                            chosen = docs[0].to_dict()
                        try:
                            original_amount = float(chosen.get("amount", chosen.get("total_amount", 0.0)))
                        except Exception:
                            original_amount = 0.0
                    else:
                        original_amount = 0.0
            else:
                original_amount = 0.0
        
        # Fixed processing fee percentage for all reasons
        processing_fee_percentage = 5.0
        
        processing_fee_amount = (original_amount * processing_fee_percentage) / 100
        refund_amount = original_amount - processing_fee_amount
        
        return {
            "original_amount": original_amount,
            "processing_fee_percentage": processing_fee_percentage,
            "processing_fee_amount": processing_fee_amount,
            "refund_amount": refund_amount,
            "processing_time": "3-5 business days"
        }
    
    @staticmethod
    def create_refund_record(
        token_id: str,
        user_id: str,
        refund_calculation: Dict,
        refund_method: RefundMethod,
        cancellation_reason: CancellationReason
    ) -> str:
        """Create refund record in database"""
        db = get_db()
        refunds_ref = db.collection("refunds")
        refund_ref = refunds_ref.document()
        
        refund_data = {
            "id": refund_ref.id,
            "token_id": token_id,
            "user_id": user_id,
            "original_amount": refund_calculation["original_amount"],
            "processing_fee": refund_calculation["processing_fee_amount"],
            "refund_amount": refund_calculation["refund_amount"],
            "refund_method": refund_method.value,
            "cancellation_reason": cancellation_reason.value,
            "status": RefundStatus.PENDING.value,
            "processing_time": refund_calculation["processing_time"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        refund_ref.set(refund_data)
        return refund_ref.id
    
    @staticmethod
    def get_refund_by_token_id(token_id: str) -> Optional[Dict]:
        """Get refund record by token ID"""
        db = get_db()
        refunds_ref = db.collection("refunds")
        
        query = refunds_ref.where("token_id", "==", token_id).limit(1)
        docs = list(query.stream())
        
        if docs:
            return docs[0].to_dict()
        return None
    
    @staticmethod
    def update_refund_status(refund_id: str, status: RefundStatus, transaction_id: str = None) -> bool:
        """Update refund status"""
        db = get_db()
        refund_ref = db.collection("refunds").document(refund_id)
        
        update_data = {
            "status": status.value,
            "updated_at": datetime.utcnow()
        }
        
        if transaction_id:
            update_data["transaction_id"] = transaction_id
        
        if status == RefundStatus.COMPLETED:
            update_data["completed_at"] = datetime.utcnow()
        
        refund_ref.update(update_data)
        return True
    
    @staticmethod
    def process_wallet_refund(user_id: str, amount: float) -> Dict:
        """Process refund to SmartToken wallet (instant)"""
        db = get_db()
        
        # Get or create user wallet
        wallets_ref = db.collection("wallets")
        wallet_query = wallets_ref.where("user_id", "==", user_id).limit(1)
        wallet_docs = list(wallet_query.stream())
        
        if wallet_docs:
            # Update existing wallet
            wallet_ref = wallets_ref.document(wallet_docs[0].id)
            wallet_data = wallet_docs[0].to_dict()
            new_balance = wallet_data.get("balance", 0) + amount
            
            wallet_ref.update({
                "balance": new_balance,
                "updated_at": datetime.utcnow()
            })
        else:
            # Create new wallet
            wallet_ref = wallets_ref.document()
            wallet_data = {
                "id": wallet_ref.id,
                "user_id": user_id,
                "balance": amount,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            wallet_ref.set(wallet_data)
        
        return {
            "success": True,
            "wallet_id": wallet_ref.id,
            "new_balance": amount if not wallet_docs else new_balance,
            "processing_time": "instant"
        }
