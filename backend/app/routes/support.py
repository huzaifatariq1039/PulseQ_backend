from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
from app.models import ActivityType
from app.database import get_db
from sqlalchemy.orm import Session
from app.db_models import User, ActivityLog # Assuming SupportTicket model exists
from app.security import get_current_active_user
from datetime import datetime
from pydantic import BaseModel
import uuid

router = APIRouter(prefix="/support", tags=["Help & Support"])

class SupportTicket(BaseModel):
    id: str
    user_id: str
    subject: str
    description: str
    category: str
    priority: str = "medium"
    status: str = "open"
    created_at: datetime
    updated_at: datetime

class SupportTicketCreate(BaseModel):
    subject: str
    description: str
    category: str = "general"
    priority: str = "medium"

class FAQ(BaseModel):
    id: str
    question: str
    answer: str
    category: str
    helpful_count: int = 0

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

@router.get("/faq")
async def get_faqs():
    """Get frequently asked questions"""
    return {
        "faqs": [
            {
                "id": "1",
                "question": "How do I cancel my appointment?",
                "answer": "You can cancel your appointment by going to your token details and clicking 'Cancel Token'. Refunds will be processed based on the cancellation reason.",
                "category": "appointments"
            },
            {
                "id": "2", 
                "question": "How long does a refund take?",
                "answer": "Refunds to original payment method take 3-5 business days. SmartToken wallet refunds are instant.",
                "category": "payments"
            },
            {
                "id": "3",
                "question": "How do queue notifications work?",
                "answer": "You'll receive WhatsApp and SMS notifications about your queue position and when it's your turn.",
                "category": "notifications"
            },
            {
                "id": "4",
                "question": "What is SmartToken format?",
                "answer": "SmartTokens are formatted as A-XXX (e.g., A-042) for easy identification and queue tracking.",
                "category": "tokens"
            }
        ]
    }

@router.post("/ticket", response_model=SupportTicket)
async def create_support_ticket(
    ticket: SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a new support ticket in PostgreSQL"""
    from app.db_models import SupportTicket as DBSupportTicket
    ticket_id = str(uuid.uuid4())
    
    new_ticket = DBSupportTicket(
        id=ticket_id,
        user_id=current_user.user_id,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status="open",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_ticket)
    db.commit()
    
    # Create activity log
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Support ticket created: {ticket.subject}",
        {"ticket_id": ticket_id, "category": ticket.category}
    )
    
    return SupportTicket(**{k: v for k, v in new_ticket.__dict__.items() if not k.startswith('_')})

@router.get("/tickets", response_model=List[SupportTicket])
async def get_user_tickets(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user's support tickets from PostgreSQL"""
    from app.db_models import SupportTicket as DBSupportTicket
    tickets_objs = db.query(DBSupportTicket).filter(DBSupportTicket.user_id == current_user.user_id).order_by(DBSupportTicket.created_at.desc()).all()
    
    return [SupportTicket(**{k: v for k, v in t.__dict__.items() if not k.startswith('_')}) for t in tickets_objs]

@router.get("/contact-info")
async def get_contact_info():
    """Get support contact information"""
    return {
        "phone": "+92 300 1234567",
        "email": "support@smarttoken.com",
        "whatsapp": "+92 300 1234567",
        "hours": "24/7 Support Available",
        "emergency_contact": "+92 300 9876543"
    }
