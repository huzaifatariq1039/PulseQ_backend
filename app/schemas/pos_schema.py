
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- Authentication & User Sync ---
class VerifyUserRequest(BaseModel):
    user_id: str
    hospital_id: str

class PatientSyncRequest(BaseModel):
    external_id: str
    name: str
    phone: str
    email: Optional[str] = None
    hospital_id: str
    mrn: Optional[str] = None

# --- Prescription Management ---
class PrescriptionItem(BaseModel):
    medicine_id: str
    medicine_name: str
    dosage: str
    frequency: str
    duration: str
    quantity: int

class PrescriptionCreateRequest(BaseModel):
    patient_id: str
    doctor_id: str
    hospital_id: str
    items: List[PrescriptionItem]
    notes: Optional[str] = None

# --- Inventory & Stock ---
class StockReservationRequest(BaseModel):
    hospital_id: str
    items: List[Dict[str, Any]] # [{"item_id": "...", "quantity": 1}]

class StockReleaseRequest(BaseModel):
    reservation_id: str

# --- Order Processing ---
class OrderCreateRequest(BaseModel):
    prescription_id: str
    hospital_id: str
    payment_method: str = "cash"

class OrderPaymentRequest(BaseModel):
    amount: float
    method: str
    transaction_id: Optional[str] = None

# --- Billing & Insurance ---
class InvoiceInsuranceRequest(BaseModel):
    order_id: str
    insurance_provider: str
    policy_number: str
    coverage_amount: float

# --- Webhooks ---
class WebhookPayload(BaseModel):
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
