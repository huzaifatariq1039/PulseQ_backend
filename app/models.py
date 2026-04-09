from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Literal
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Enums
class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PaymentMethod(str, Enum):
    ONLINE = "online"
    RECEPTION = "reception"

class PaymentType(str, Enum):
    CREDIT_DEBIT_CARD = "credit_debit_card"
    EASYPAISA = "easypaisa"

class UserRole(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    PHARMACY = "pharmacy"

class AuthMethod(str, Enum):
    PHONE = "phone"
    EMAIL = "email"

class ActivityType(str, Enum):
    TOKEN_GENERATED = "token_generated"
    TOKEN_CANCELLED = "token_cancelled"
    PAYMENT_MADE = "payment_made"
    REFUND_PROCESSED = "refund_processed"
    APPOINTMENT_BOOKED = "appointment_booked"
    APPOINTMENT_COMPLETED = "appointment_completed"
    NOTIFICATION_SENT = "notification_sent"
    QUEUE_ADVANCED = "queue_advanced"
    PROFILE_UPDATED = "profile_updated"
    LOGIN = "login"

class HospitalStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MAINTENANCE = "maintenance"

class DoctorStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    ON_LEAVE = "on_leave"

class NotificationType(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"

class TokenStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"

class CancellationReason(str, Enum):
    MEDICAL_EMERGENCY = "medical_emergency"
    SCHEDULE_CONFLICT = "schedule_conflict"
    FEELING_BETTER = "feeling_better"
    WANT_DIFFERENT_DOCTOR = "want_different_doctor"
    COST_CONCERNS = "cost_concerns"
    OTHER_REASON = "other_reason"

class RefundMethod(str, Enum):
    ORIGINAL_PAYMENT = "original_payment"
    SMARTTOKEN_WALLET = "smarttoken_wallet"

class RefundStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# Base Models
class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = None
    role: UserRole = UserRole.PATIENT
    location_access: bool = False

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    auth_method: AuthMethod = AuthMethod.PHONE
    # Optional profile details at signup
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    # Aliases accepted from some clients
    birthday: Optional[str] = None
    location: Optional[str] = None
    
    @model_validator(mode='after')
    @classmethod
    def validate_auth_method(cls, values):
        if values.auth_method == AuthMethod.EMAIL and not values.email:
            raise ValueError('Email is required when using email authentication')
        if values.auth_method == AuthMethod.PHONE and not values.phone:
            raise ValueError('Phone is required when using phone authentication')
        return values

class UserResponse(UserBase):
    id: str
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    # Compatibility aliases for frontend fields
    birthday: Optional[str] = None
    location: Optional[str] = None
    membership_type: str = "Premium Member"
    avatar_initials: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Phone number or email")
    password: str
    auth_method: AuthMethod = AuthMethod.PHONE
    location_access: bool = False

class LocationUpdate(BaseModel):
    location_access: bool

# Authentication Models
class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None

# Dashboard Models
class UserStatistics(BaseModel):
    total_tokens: int = 0
    active_tokens: int = 0
    completed_appointments: int = 0
    total_payments: int = 0
    pending_payments: int = 0

class ActivityLog(BaseModel):
    id: str
    user_id: str
    activity_type: ActivityType
    description: str
    metadata: Optional[dict] = None
    created_at: datetime

class ActivityLogCreate(BaseModel):
    activity_type: ActivityType
    description: str
    metadata: Optional[dict] = None

class QuickAction(BaseModel):
    id: str
    user_id: str
    action_type: str
    title: str
    description: str
    icon: str
    route: str
    is_enabled: bool = True
    created_at: datetime

class QuickActionCreate(BaseModel):
    action_type: str
    title: str
    description: str
    icon: str
    route: str
    is_enabled: bool = True

class DashboardData(BaseModel):
    user: UserResponse
    statistics: UserStatistics
    recent_activities: List[ActivityLog]
    quick_actions: List[QuickAction]
    recent_tokens: List[dict]  # Will be SmartTokenResponse

# Hospital Models
class HospitalBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    address: str
    city: str
    state: str
    phone: str
    email: Optional[str] = None
    rating: Optional[float] = Field(None, ge=0, le=5)
    review_count: int = 0
    status: HospitalStatus = HospitalStatus.OPEN
    specializations: List[str] = []
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    estimated_time_minutes: Optional[int] = None

class HospitalCreate(HospitalBase):
    pass

class HospitalResponse(HospitalBase):
    id: str
    created_at: datetime
    updated_at: datetime
    # UI contracts for search pages
    is_open: Optional[bool] = None
    is_database: bool = True
    source: str = "db"  # db | database | firestore
    doctors_count: Optional[int] = None
    has_doctors: Optional[bool] = None
    is_nearby: Optional[bool] = None

# Lightweight public-facing hospital item for unified search (DB + external)
class HospitalLite(BaseModel):
    id: str
    name: str
    address: Optional[str] = None  # For external sources we may only have a string
    city: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    estimated_time_minutes: Optional[int] = None
    rating: Optional[float] = None
    review_count: Optional[int] = 0
    status: Optional[HospitalStatus] = HospitalStatus.OPEN
    # Enrichment fields for UI logic
    source: str = "db"  # db | osm_overpass | osm_nominatim
    is_nearby: bool = False
    is_database: bool = True

# Doctor Models
class DoctorBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    name: str = Field(..., min_length=2, max_length=100)
    # Firestore field in your DB is `department`. We keep internal field name
    # `specialization` for backward compatibility with existing code.
    # This alias lets the app accept `department` when reading/writing doctors.
    specialization: str = Field(..., alias="department")
    subcategory: Optional[str] = None  # e.g., "Pediatric Cardiology"
    hospital_id: str
    phone: str
    email: Optional[str] = None
    experience_years: int = Field(..., ge=0)
    rating: Optional[float] = Field(None, ge=0, le=5)
    review_count: int = 0
    consultation_fee: float = Field(..., gt=0)
    # Dynamic pricing for session-based departments (Psychology/Psychiatry/Physiotherapy, etc.)
    session_fee: Optional[float] = Field(None, gt=0)
    has_session: bool = False
    pricing_type: Literal["standard", "session_based"] = "standard"
    status: DoctorStatus = DoctorStatus.AVAILABLE
    available_days: List[str] = []
    start_time: str
    end_time: str
    avatar_initials: Optional[str] = None
    patients_per_day: int = Field(10, ge=1, description="Maximum number of patients per day for FCFS slotting")

    @model_validator(mode="after")
    def apply_session_pricing_rules(self):
        """Infer session-based pricing from the doctor's department fields.

        If specialization/subcategory includes:
        - psychology
        - psychiatry
        - physiotherapist / physiotherapy / physio
        then the doctor supports session-based fees.
        """
        dept_text = f"{self.specialization or ''} {self.subcategory or ''}".lower().strip()
        inferred = any(
            kw in dept_text
            for kw in (
                "psychology",
                "psychiatry",
                "physiotherapist",
                "physiotherapy",
                "physio",
            )
        )

        # If session-based, infer has_session and pricing_type.
        # NOTE: We do not hard-fail here when session_fee is missing because
        # existing Firestore documents may not have the new field yet.
        # Enforcement is done in token-creation and admin create/update routes.
        if inferred:
            self.has_session = True
            self.pricing_type = "session_based"
            if self.session_fee is not None and self.session_fee <= 0:
                raise ValueError("session_fee must be > 0 when provided")
        else:
            self.has_session = False
            self.session_fee = None
            self.pricing_type = "standard"

        return self

class DoctorCreate(DoctorBase):
    pass

class DoctorResponse(DoctorBase):
    id: str
    created_at: datetime
    updated_at: datetime


# Queue Models
class QueueStatus(BaseModel):
    doctor_id: str
    current_token: Optional[int] = None
    waiting_patients: int
    estimated_wait_time_minutes: Optional[int] = None
    people_ahead: int = 0
    total_queue: int = 0

class QueueResponse(BaseModel):
    doctor_id: str
    current_token: int = Field(..., ge=0)
    total_patients: int = Field(..., ge=0)
    # When the doctor is unavailable (e.g. emergency leave), the frontend should hide wait time.
    estimated_wait_time: Optional[int] = None  # in minutes
    people_ahead: int = Field(..., ge=0)
    total_queue: int = Field(..., ge=0)
    is_future_appointment: bool = False
    doctor_unavailable: bool = False
    id: str
    updated_at: datetime

class TokenCancellationRequest(BaseModel):
    reason: CancellationReason
    custom_reason: Optional[str] = None  # For OTHER_REASON
    refund_method: RefundMethod = RefundMethod.ORIGINAL_PAYMENT

    @field_validator('refund_method', mode='before')
    @classmethod
    def normalize_refund_method(cls, v):
        if isinstance(v, RefundMethod):
            return v
        if v is None:
            return RefundMethod.ORIGINAL_PAYMENT
        s = str(v).strip().lower().replace('-', '_').replace(' ', '_')
        # Common aliases from various clients
        aliases = {
            'original_payment_method': RefundMethod.ORIGINAL_PAYMENT,
            'original_payment': RefundMethod.ORIGINAL_PAYMENT,
            'original': RefundMethod.ORIGINAL_PAYMENT,
            'card': RefundMethod.ORIGINAL_PAYMENT,
            'bank': RefundMethod.ORIGINAL_PAYMENT,
            'wallet': RefundMethod.SMARTTOKEN_WALLET,
            'smarttoken_wallet': RefundMethod.SMARTTOKEN_WALLET,
            'smart_token_wallet': RefundMethod.SMARTTOKEN_WALLET,
        }
        try:
            return aliases.get(s, RefundMethod(s))
        except Exception:
            return RefundMethod.ORIGINAL_PAYMENT

    @field_validator('reason', mode='before')
    @classmethod
    def normalize_reason(cls, v):
        if isinstance(v, CancellationReason):
            return v
        if v is None:
            return CancellationReason.SCHEDULE_CONFLICT
        s = str(v).strip()
        # Normalize common patterns
        s_simple = s.replace('-', ' ').replace('_', ' ').lower()
        s_simple = ' '.join(s_simple.split())
        aliases = {
            'medical emergency': CancellationReason.MEDICAL_EMERGENCY,
            'medical_emergency': CancellationReason.MEDICAL_EMERGENCY,
            'medicalemergency': CancellationReason.MEDICAL_EMERGENCY,
            'schedule conflict': CancellationReason.SCHEDULE_CONFLICT,
            'schedule_conflict': CancellationReason.SCHEDULE_CONFLICT,
            'scheduleconflict': CancellationReason.SCHEDULE_CONFLICT,
            'feeling better': CancellationReason.FEELING_BETTER,
            'feeling_better': CancellationReason.FEELING_BETTER,
            'feelingbetter': CancellationReason.FEELING_BETTER,
            'want different doctor': CancellationReason.WANT_DIFFERENT_DOCTOR,
            'want_different_doctor': CancellationReason.WANT_DIFFERENT_DOCTOR,
            'wantdifferentdoctor': CancellationReason.WANT_DIFFERENT_DOCTOR,
            'cost concerns': CancellationReason.COST_CONCERNS,
            'cost_concerns': CancellationReason.COST_CONCERNS,
            'costconcerns': CancellationReason.COST_CONCERNS,
            'other reason': CancellationReason.OTHER_REASON,
            'other_reason': CancellationReason.OTHER_REASON,
            'otherreason': CancellationReason.OTHER_REASON,
        }
        # Try alias map first
        if s_simple in aliases:
            return aliases[s_simple]
        # Fallback: try direct enum by replacing spaces with underscores
        try:
            key = s_simple.replace(' ', '_')
            return CancellationReason(key)
        except Exception:
            return CancellationReason.SCHEDULE_CONFLICT

class NotificationRequest(BaseModel):
    token_id: str
    notification_types: List[NotificationType]
    message: str
    phone_number: str

class RefundCalculation(BaseModel):
    original_amount: float
    processing_fee_percentage: float = 5.0
    processing_fee_amount: float
    refund_amount: float
    refund_method: RefundMethod
    processing_time_days: str = "3-5 business days"

class RefundResponse(BaseModel):
    id: str
    token_id: str
    original_amount: float
    processing_fee: float
    refund_amount: float
    refund_method: RefundMethod
    status: RefundStatus
    processing_time: str
    created_at: datetime
    updated_at: datetime

class CancellationResponse(BaseModel):
    message: str
    token_id: str
    cancellation_reason: CancellationReason
    refund_info: RefundCalculation
    refund_id: Optional[str] = None

# Doctor with Queue Info
class DoctorWithQueue(BaseModel):
    doctor: DoctorResponse
    queue: QueueStatus

# SmartToken Models
class SmartTokenCreate(BaseModel):
    patient_id: str
    doctor_id: str
    hospital_id: str
    appointment_date: datetime
    department: Optional[str] = None

class SmartTokenGenerateRequest(BaseModel):
    doctor_id: str
    hospital_id: str
    appointment_date: Optional[datetime] = None
    department: Optional[str] = None

class SmartTokenResponse(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    hospital_id: str
    mrn: Optional[str] = None
    token_number: int
    hex_code: str
    formatted_token: Optional[str] = None  # Deprecated: legacy A-042 format; not exposed in new clients
    display_code: Optional[str] = None  # Optional globally unique human-friendly code
    appointment_date: datetime
    status: TokenStatus = TokenStatus.PENDING
    payment_status: PaymentStatus = PaymentStatus.PENDING
    payment_method: Optional[PaymentMethod] = None
    queue_position: Optional[int] = None
    total_queue: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # in minutes
    consultation_fee: Optional[float] = None
    session_fee: Optional[float] = None
    total_fee: Optional[float] = None
    department: Optional[str] = None  # Doctor department/specialization
    created_at: datetime
    updated_at: datetime
    # Convenience flag for UI filtering; true unless status is cancelled or completed
    is_active: Optional[bool] = None
    # Embedded snapshots for resilient UI display (optional)
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None
    doctor_avatar_initials: Optional[str] = None
    hospital_name: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    queue_opt_in: bool = False
    queue_opted_in_at: Optional[datetime] = None
    confirmed: bool = False
    confirmation_status: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

# Payment Models
class PaymentProcess(BaseModel):
    token_id: str
    amount: float
    method: PaymentMethod

class PaymentResponse(BaseModel):
    id: str
    token_id: str
    amount: float
    method: PaymentMethod
    status: PaymentStatus
    transaction_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class PaymentCreate(BaseModel):
    token_id: str
    amount: float
    payment_method: PaymentMethod
    status: PaymentStatus = PaymentStatus.PENDING
    transaction_id: Optional[str] = None

# Payment Method Models
class PaymentMethodRequest(BaseModel):
    method: PaymentMethod
    payment_type: Optional[PaymentType] = None

class CardPaymentRequest(BaseModel):
    card_number: str = Field(..., min_length=13, max_length=19)
    expiry_month: str = Field(..., min_length=2, max_length=2)
    expiry_year: str = Field(..., min_length=2, max_length=2)
    cvv: str = Field(..., min_length=3, max_length=4)
    cardholder_name: str = Field(..., min_length=2, max_length=100)
    # Optional: selected issuing bank info from the bank list
    bank_code: Optional[str] = None
    bank_name: Optional[str] = None

class EasyPaisaPaymentRequest(BaseModel):
    phone_number: str = Field(..., min_length=11, max_length=15)
    otp: Optional[str] = None

# Appointment Summary Models
class AppointmentSummary(BaseModel):
    doctor: DoctorResponse
    hospital: HospitalResponse
    consultation_fee: float
    total_amount: float
    appointment_date: datetime

class PaymentConfirmationRequest(BaseModel):
    token_id: str
    payment_method: PaymentMethod
    payment_type: Optional[PaymentType] = None
    card_details: Optional[CardPaymentRequest] = None
    easypaisa_details: Optional[EasyPaisaPaymentRequest] = None
    # Optional per-transaction notification override (WhatsApp/SMS)
    notification_types: Optional[List[NotificationType]] = None

class PaymentConfirmationResponse(BaseModel):
    token_id: str
    payment_id: str
    status: PaymentStatus
    transaction_id: Optional[str] = None
    message: str
    appointment_summary: AppointmentSummary

# Profile Models
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    address: Optional[str] = None
    # Accept alternate field names from some clients
    birthday: Optional[str] = None
    location: Optional[str] = None

class AppointmentHistory(BaseModel):
    id: str
    doctor_name: str
    doctor_specialization: str
    hospital_name: str
    appointment_date: datetime
    status: str  # completed, cancelled
    rating: Optional[int] = None
    token_number: str

class NotificationSettings(BaseModel):
    queue_updates: bool = True
    appointment_reminders: bool = True
    emergency_alerts: bool = True
    promotions: bool = False
    whatsapp_notifications: bool = True
    whatsapp_queue_updates: bool = True
    sms_notifications: bool = True
    sms_queue_updates: bool = True
    sms_appointment_reminders: bool = True

# Notification Models
class NotificationPreference(BaseModel):
    whatsapp_enabled: bool = True
    sms_enabled: bool = True
    phone_number: str = Field(..., min_length=11, max_length=15)

class NotificationPreferenceUpdate(BaseModel):
    whatsapp_enabled: bool = True
    sms_enabled: bool = True

class NotificationPreferenceResponse(BaseModel):
    id: str
    user_id: str
    whatsapp_enabled: bool
    sms_enabled: bool
    phone_number: str
    settings: NotificationSettings
    created_at: datetime
    updated_at: datetime

class PaymentMethodInfo(BaseModel):
    id: str
    user_id: str
    method_type: str  # card, easypaisa, wallet
    display_name: str  # "**** 1234", "EasyPaisa Account"
    is_default: bool = False
    created_at: datetime

class SecuritySettings(BaseModel):
    two_factor_enabled: bool = False
    biometric_enabled: bool = False
    login_notifications: bool = True
    password_last_changed: Optional[datetime] = None

# Search Models
class SearchRequest(BaseModel):
    query: Optional[str] = None
    location: Optional[str] = None
    specialization: Optional[str] = None
    hospital_id: Optional[str] = None
    category: Optional[str] = None

class SearchResult(BaseModel):
    hospitals: List[HospitalResponse] = []
    doctors: List[DoctorResponse] = []
    total_results: int

# Hospital Search Response
class HospitalSearchResponse(BaseModel):
    hospitals: List[HospitalResponse]
    total_found: int
    search_query: Optional[str] = None

# Unified search response for HospitalLite items
class HospitalUnifiedSearchResponse(BaseModel):
    hospitals: List[HospitalLite]
    total_found: int
    search_query: Optional[str] = None

# Doctor Search Response
class DoctorSearchResponse(BaseModel):
    doctors: List[DoctorWithQueue]
    total_found: int
    hospital_id: str
    category: Optional[str] = None 
    subcategories: List[str] = []

# Pharmacy Models
class PharmacyMedicineBase(BaseModel):
    product_id: int = Field(..., ge=0)
    batch_no: str
    name: str
    generic_name: Optional[str] = None
    type: Optional[str] = None
    distributor: Optional[str] = None
    purchase_price: float = Field(..., ge=0)
    selling_price: float = Field(..., ge=0)
    stock_unit: Optional[str] = None
    quantity: int = Field(..., ge=0)
    expiration_date: Optional[datetime] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None

class PharmacyMedicineCreate(PharmacyMedicineBase):
    pass

class PharmacyMedicineUpdate(BaseModel):
    product_id: Optional[int] = Field(None, ge=0)
    batch_no: Optional[str] = None
    name: Optional[str] = None
    generic_name: Optional[str] = None
    type: Optional[str] = None
    distributor: Optional[str] = None
    purchase_price: Optional[float] = Field(None, ge=0)
    selling_price: Optional[float] = Field(None, ge=0)
    stock_unit: Optional[str] = None
    quantity: Optional[int] = Field(None, ge=0)
    expiration_date: Optional[datetime] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None

class PharmacyMedicineResponse(PharmacyMedicineBase):
    id: str
    created_at: Optional[datetime] = None

# Queue Token Status Update Model
class QueueTokenStatusUpdate(BaseModel):
    status: str

# Token Create Spec Model (for idempotent token creation)
class TokenCreateSpec(BaseModel):
    doctor_id: str
    hospital_id: str
    appointment_date: str  # YYYY-MM-DD in clinic local timezone
    idempotency_key: str
    department: Optional[str] = None