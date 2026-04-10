"""SQLAlchemy models for PostgreSQL database"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


# Enums
class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"
    RECEPTIONIST = "receptionist"
    PHARMACY = "pharmacy"


class TokenStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    ONLINE = "online"
    RECEPTION = "reception"


class DoctorStatus(str, enum.Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    ON_LEAVE = "on_leave"


class HospitalStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    MAINTENANCE = "maintenance"


# User Model
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone = Column(String(20), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="patient") # Using string for DB compatibility, validated by UserRole enum
    location_access = Column(Boolean, default=False)
    date_of_birth = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)
    mrn_by_hospital = Column(JSON, default=dict) # Added for MRN tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tokens = relationship("Token", back_populates="patient")
    activities = relationship("ActivityLog", back_populates="user")


# Hospital Model
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, default=0)
    status = Column(String(20), default="open") # Using string for DB compatibility, validated by HospitalStatus enum
    specializations = Column(JSON, default=list)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    doctors = relationship("Doctor", back_populates="hospital")


# Doctor Model
class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    specialization = Column(String(100), nullable=False)
    subcategory = Column(String(100), nullable=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(255), nullable=True)
    experience_years = Column(Integer, default=0)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, default=0)
    consultation_fee = Column(Float, nullable=False)
    session_fee = Column(Float, nullable=True)
    has_session = Column(Boolean, default=False)
    pricing_type = Column(String(20), default="standard")
    status = Column(String(20), default="available") # Using string for DB compatibility, validated by DoctorStatus enum
    available_days = Column(JSON, default=list)
    start_time = Column(String(10), nullable=False)
    end_time = Column(String(10), nullable=False)
    avatar_initials = Column(String(10), nullable=True)
    patients_per_day = Column(Integer, default=10)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    hospital = relationship("Hospital", back_populates="doctors")
    tokens = relationship("Token", back_populates="doctor")


# Token Model
class Token(Base):
    __tablename__ = "tokens"

    id = Column(String, primary_key=True, index=True)
    patient_id = Column(String, ForeignKey("users.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False)
    mrn = Column(String(50), nullable=True)
    token_number = Column(Integer, nullable=False)
    hex_code = Column(String(20), nullable=False)
    display_code = Column(String(20), nullable=True)
    appointment_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="pending") # Using string for DB compatibility, validated by TokenStatus enum
    payment_status = Column(String(20), default="pending") # Using string for DB compatibility, validated by PaymentStatus enum
    payment_method = Column(String(20), nullable=True) # Using string for DB compatibility, validated by PaymentMethod enum
    queue_position = Column(Integer, nullable=True)
    total_queue = Column(Integer, nullable=True)
    estimated_wait_time = Column(Integer, nullable=True)
    consultation_fee = Column(Float, nullable=True)
    session_fee = Column(Float, nullable=True)
    total_fee = Column(Float, nullable=True)
    department = Column(String(100), nullable=True)  # Doctor department/specialization
    idempotency_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Embedded snapshots
    doctor_name = Column(String(100), nullable=True)
    doctor_specialization = Column(String(100), nullable=True)
    doctor_avatar_initials = Column(String(10), nullable=True)
    hospital_name = Column(String(200), nullable=True)
    patient_name = Column(String(100), nullable=True)
    patient_phone = Column(String(20), nullable=True)

    # Status/Confirmation Tracking
    queue_opt_in = Column(Boolean, default=False)
    queue_opted_in_at = Column(DateTime(timezone=True), nullable=True)
    confirmed = Column(Boolean, default=False)
    confirmation_status = Column(String(50), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    patient = relationship("User", back_populates="tokens")
    doctor = relationship("Doctor", back_populates="tokens")
    payments = relationship("Payment", back_populates="token")


# Hospital Sequence for MRN and other numbering
class HospitalSequence(Base):
    __tablename__ = "hospital_sequences"
    
    id = Column(String, primary_key=True, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, unique=True)
    mrn_seq = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# Payment Model
class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, index=True)
    token_id = Column(String, ForeignKey("tokens.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(20), nullable=False) # Using string for DB compatibility, validated by PaymentMethod enum
    status = Column(String(20), default="pending") # Using string for DB compatibility, validated by PaymentStatus enum
    transaction_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    token = relationship("Token", back_populates="payments")


# Activity Log Model
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    activity_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    meta_data = Column(JSON, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy reserved name
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="activities")


# Queue Model
class Queue(Base):
    __tablename__ = "queues"

    id = Column(String, primary_key=True, index=True)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    current_token = Column(Integer, nullable=True)
    waiting_patients = Column(Integer, default=0)
    estimated_wait_time_minutes = Column(Integer, nullable=True)
    people_ahead = Column(Integer, default=0)
    total_queue = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Idempotency Record Model
class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    key = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    token_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Pharmacy Medicine Model
class PharmacyMedicine(Base):
    __tablename__ = "pharmacy_medicines"

    id = Column(String, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False)
    batch_no = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    generic_name = Column(String(200), nullable=True)
    type = Column(String(100), nullable=True)
    distributor = Column(String(200), nullable=True)
    purchase_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)
    stock_unit = Column(String(50), nullable=True)
    quantity = Column(Integer, default=0)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    category = Column(String(100), nullable=True)
    sub_category = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Department Model
class Department(Base):
    __tablename__ = "departments"

    id = Column(String, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Quick Action Model
class QuickAction(Base):
    __tablename__ = "quick_actions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    title = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    icon = Column(String(50), nullable=True)
    route = Column(String(255), nullable=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Medical Record Model
class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    record_type = Column(String(50), default="general")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Wallet Model
class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Float, default=0.0)
    currency = Column(String(10), default="PKR")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Refund Model
class Refund(Base):
    __tablename__ = "refunds"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_id = Column(String, ForeignKey("tokens.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    method = Column(String(50), nullable=False)
    reason = Column(String(255), nullable=True)
    transaction_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Support Ticket Model
class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), default="general")
    priority = Column(String(20), default="medium")
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Pharmacy Sale Model
class PharmacySale(Base):
    __tablename__ = "pharmacy_sales"

    id = Column(String, primary_key=True, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=True)
    patient_id = Column(String, ForeignKey("users.id"), nullable=True)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=True)
    medicine_id = Column(Integer, nullable=True)
    medicine_name = Column(String(200), nullable=True)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)  # Used in POS
    items = Column(JSON, nullable=True)  # Used in POS for multiple items
    payment_status = Column(String(20), default="paid")
    sold_at = Column(DateTime(timezone=True), server_default=func.now())
    performed_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
