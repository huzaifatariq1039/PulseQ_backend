from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from app.models import ActivityType
from app.database import get_db
from app.security import get_current_active_user
from datetime import datetime
from pydantic import BaseModel

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
    current_user = Depends(get_current_active_user)
):
    """Create a new support ticket"""
    db = get_db()
    tickets_ref = db.collection("support_tickets")
    ticket_ref = tickets_ref.document()
    
    ticket_data = {
        "id": ticket_ref.id,
        "user_id": current_user.user_id,
        **ticket.dict(),
        "status": "open",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    ticket_ref.set(ticket_data)
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Support ticket created: {ticket.subject}",
        {"ticket_id": ticket_ref.id, "category": ticket.category}
    )
    
    return SupportTicket(**ticket_data)

@router.get("/tickets", response_model=List[SupportTicket])
async def get_user_tickets(current_user = Depends(get_current_active_user)):
    """Get user's support tickets"""
    db = get_db()
    tickets_ref = db.collection("support_tickets")
    
    # Use simple query to avoid composite index requirement
    query = tickets_ref.where("user_id", "==", current_user.user_id)
    
    tickets = []
    ticket_docs = []
    
    # Get all documents first
    for doc in query.stream():
        ticket_data = doc.to_dict()
        ticket_data["doc_id"] = doc.id
        ticket_docs.append(ticket_data)
    
    # Sort in memory by created_at descending
    ticket_docs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
    
    for ticket_data in ticket_docs:
        tickets.append(SupportTicket(**ticket_data))
    
    return tickets

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
