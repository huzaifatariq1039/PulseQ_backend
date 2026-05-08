import uuid
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.config import COLLECTIONS
from app.models import RefundMethod, RefundStatus, CancellationReason
from app.db_models import Refund, Wallet, Payment

def _get_session(passed_db: Optional[Session]) -> Session:
    if passed_db is not None:
        return passed_db
    return SessionLocal()

class RefundService:
    """Service for handling refund calculations and processing"""
    
    @staticmethod
    def calculate_refund(amount_or_token: object, cancellation_reason: CancellationReason, db: Session = None) -> Dict:
        """Calculate refund based on either a provided base amount (preferred) or a token_id."""
        original_amount = 0.0
        session = _get_session(db)
        try:
            if isinstance(amount_or_token, (int, float)):
                try:
                    original_amount = float(amount_or_token)
                except Exception:
                    original_amount = 0.0
            else:
                if isinstance(amount_or_token, str):
                    s = amount_or_token.strip()
                    try:
                        original_amount = float(s)
                    except Exception:
                        payment = session.query(Payment).filter(Payment.token_id == s).order_by(Payment.created_at.desc()).first()
                        if payment:
                            original_amount = payment.amount
                        else:
                            original_amount = 0.0
                else:
                    original_amount = 0.0
        finally:
            if db is None:
                session.close()
        
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
        cancellation_reason: CancellationReason,
        db: Session = None
    ) -> str:
        """Create refund record in database"""
        session = _get_session(db)
        try:
            refund_id = str(uuid.uuid4())
            refund = Refund(
                id=refund_id,
                token_id=token_id,
                user_id=user_id,
                amount=refund_calculation["refund_amount"],
                method=refund_method.value,
                reason=cancellation_reason.value,
                status=RefundStatus.PENDING.value,
            )
            session.add(refund)
            session.commit()
            return refund_id
        finally:
            if db is None:
                session.close()
    
    @staticmethod
    def get_refund_by_token_id(token_id: str, db: Session = None) -> Optional[Dict]:
        """Get refund record by token ID"""
        session = _get_session(db)
        try:
            refund = session.query(Refund).filter(Refund.token_id == token_id).first()
            if refund:
                return {
                    "id": refund.id,
                    "token_id": refund.token_id,
                    "user_id": refund.user_id,
                    "amount": refund.amount,
                    "status": refund.status,
                    "method": refund.method,
                    "reason": refund.reason,
                    "transaction_id": refund.transaction_id,
                    "created_at": refund.created_at,
                    "updated_at": refund.updated_at
                }
            return None
        finally:
            if db is None:
                session.close()
    
    @staticmethod
    def update_refund_status(refund_id: str, status: RefundStatus, transaction_id: str = None, db: Session = None) -> bool:
        """Update refund status"""
        session = _get_session(db)
        try:
            refund = session.query(Refund).filter(Refund.id == refund_id).first()
            if not refund:
                return False
                
            refund.status = status.value
            if transaction_id:
                refund.transaction_id = transaction_id
                
            session.commit()
            return True
        finally:
            if db is None:
                session.close()
    
    @staticmethod
    def process_wallet_refund(user_id: str, amount: float, db: Session = None) -> Dict:
        """Process refund to SmartToken wallet (instant)"""
        session = _get_session(db)
        try:
            wallet = session.query(Wallet).filter(Wallet.user_id == user_id).first()
            
            if wallet:
                wallet.balance += amount
            else:
                wallet = Wallet(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    balance=amount
                )
                session.add(wallet)
                
            session.commit()
            session.refresh(wallet)
            
            return {
                "success": True,
                "wallet_id": wallet.id,
                "new_balance": wallet.balance,
                "processing_time": "instant"
            }
        finally:
            if db is None:
                session.close()
