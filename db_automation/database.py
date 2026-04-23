# db_automation/models.py
# SQLAlchemy ORM models matching ALL tables in the PostgreSQL database

from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer, Float, Text
from sqlalchemy.sql import func
import uuid

from db_automation.database import Base


def _uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone = Column(String(20), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="patient", index=True)
    hospital_id = Column(String, nullable=True)
    location_access = Column(Boolean, default=False)
    date_of_birth = Column(String(20), nullable=True)
    gender = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)
    mrn_by_hospital = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<User(id={self.id!r}, name={self.name!r}, role={self.role!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "hospital_id": self.hospital_id,
            "gender": self.gender,
            "date_of_birth": self.date_of_birth,
            "location_access": self.location_access,
            "address": self.address,
            "mrn_by_hospital": self.mrn_by_hospital,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  HOSPITALS
# ═══════════════════════════════════════════════════════════

class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    status = Column(String, nullable=True)
    specializations = Column(JSON, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Hospital(id={self.id!r}, name={self.name!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "phone": self.phone,
            "email": self.email,
            "rating": self.rating,
            "review_count": self.review_count,
            "status": self.status,
            "specializations": self.specializations,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  DEPARTMENTS
# ═══════════════════════════════════════════════════════════

class Department(Base):
    __tablename__ = "departments"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    hospital_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Department(id={self.id!r}, name={self.name!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "hospital_id": self.hospital_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  DOCTORS
# ═══════════════════════════════════════════════════════════

class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)
    hospital_id = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    consultation_fee = Column(Float, nullable=False)
    session_fee = Column(Float, nullable=True)
    has_session = Column(Boolean, nullable=True)
    pricing_type = Column(String, nullable=True)
    status = Column(String, nullable=True)
    available_days = Column(JSON, nullable=True)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    avatar_initials = Column(String, nullable=True)
    patients_per_day = Column(Integer, nullable=True)
    user_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Doctor(id={self.id!r}, name={self.name!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "specialization": self.specialization,
            "subcategory": self.subcategory,
            "hospital_id": self.hospital_id,
            "email": self.email,
            "rating": self.rating,
            "review_count": self.review_count,
            "consultation_fee": self.consultation_fee,
            "session_fee": self.session_fee,
            "has_session": self.has_session,
            "pricing_type": self.pricing_type,
            "status": self.status,
            "available_days": self.available_days,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "avatar_initials": self.avatar_initials,
            "patients_per_day": self.patients_per_day,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  TOKENS (Appointments)
# ═══════════════════════════════════════════════════════════

class Token(Base):
    __tablename__ = "tokens"

    id = Column(String, primary_key=True, default=_uuid)
    patient_id = Column(String, nullable=False, index=True)
    doctor_id = Column(String, nullable=False, index=True)
    hospital_id = Column(String, nullable=False, index=True)
    mrn = Column(String, nullable=True)
    token_number = Column(Integer, nullable=False)
    hex_code = Column(String, nullable=False)
    display_code = Column(String, nullable=True)
    appointment_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=True)
    payment_status = Column(String, nullable=True)
    payment_method = Column(String, nullable=True)
    queue_position = Column(Integer, nullable=True)
    total_queue = Column(Integer, nullable=True)
    estimated_wait_time = Column(Integer, nullable=True)
    consultation_fee = Column(Float, nullable=True)
    session_fee = Column(Float, nullable=True)
    total_fee = Column(Float, nullable=True)
    department = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=True)
    doctor_name = Column(String, nullable=True)
    doctor_specialization = Column(String, nullable=True)
    doctor_avatar_initials = Column(String, nullable=True)
    hospital_name = Column(String, nullable=True)
    patient_name = Column(String, nullable=True)
    patient_phone = Column(String, nullable=True)
    queue_opt_in = Column(Boolean, nullable=True)
    queue_opted_in_at = Column(DateTime(timezone=True), nullable=True)
    confirmed = Column(Boolean, nullable=True)
    confirmation_status = Column(String, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Float, nullable=True)
    patient_age = Column(Integer, nullable=True)
    patient_gender = Column(String, nullable=True)
    reason_for_visit = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Token(id={self.id!r}, token_number={self.token_number!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "hospital_id": self.hospital_id,
            "mrn": self.mrn,
            "token_number": self.token_number,
            "hex_code": self.hex_code,
            "display_code": self.display_code,
            "appointment_date": self.appointment_date.isoformat() if self.appointment_date else None,
            "status": self.status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "queue_position": self.queue_position,
            "total_queue": self.total_queue,
            "estimated_wait_time": self.estimated_wait_time,
            "consultation_fee": self.consultation_fee,
            "session_fee": self.session_fee,
            "total_fee": self.total_fee,
            "department": self.department,
            "doctor_name": self.doctor_name,
            "doctor_specialization": self.doctor_specialization,
            "hospital_name": self.hospital_name,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "queue_opt_in": self.queue_opt_in,
            "confirmed": self.confirmed,
            "confirmation_status": self.confirmation_status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_minutes": self.duration_minutes,
            "patient_age": self.patient_age,
            "patient_gender": self.patient_gender,
            "reason_for_visit": self.reason_for_visit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  QUEUES
# ═══════════════════════════════════════════════════════════

class Queue(Base):
    __tablename__ = "queues"

    id = Column(String, primary_key=True, default=_uuid)
    doctor_id = Column(String, nullable=False, index=True)
    current_token = Column(Integer, nullable=True)
    waiting_patients = Column(Integer, nullable=True)
    estimated_wait_time_minutes = Column(Integer, nullable=True)
    people_ahead = Column(Integer, nullable=True)
    total_queue = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Queue(id={self.id!r}, doctor_id={self.doctor_id!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "current_token": self.current_token,
            "waiting_patients": self.waiting_patients,
            "estimated_wait_time_minutes": self.estimated_wait_time_minutes,
            "people_ahead": self.people_ahead,
            "total_queue": self.total_queue,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  PAYMENTS
# ═══════════════════════════════════════════════════════════

class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=_uuid)
    token_id = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=False)
    status = Column(String, nullable=True)
    transaction_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Payment(id={self.id!r}, amount={self.amount!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "token_id": self.token_id,
            "amount": self.amount,
            "method": self.method,
            "status": self.status,
            "transaction_id": self.transaction_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  REFUNDS
# ═══════════════════════════════════════════════════════════

class Refund(Base):
    __tablename__ = "refunds"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    token_id = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=True)
    method = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    transaction_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Refund(id={self.id!r}, amount={self.amount!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token_id": self.token_id,
            "amount": self.amount,
            "status": self.status,
            "method": self.method,
            "reason": self.reason,
            "transaction_id": self.transaction_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  WALLETS
# ═══════════════════════════════════════════════════════════

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, unique=True, index=True)
    balance = Column(Float, nullable=True, default=0.0)
    currency = Column(String, nullable=True, default="PKR")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Wallet(id={self.id!r}, user_id={self.user_id!r}, balance={self.balance!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "balance": self.balance,
            "currency": self.currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  MEDICAL RECORDS
# ═══════════════════════════════════════════════════════════

class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    record_type = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<MedicalRecord(id={self.id!r}, filename={self.filename!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "record_type": self.record_type,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    activity_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ActivityLog(id={self.id!r}, activity_type={self.activity_type!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "activity_type": self.activity_type,
            "description": self.description,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  SUPPORT TICKETS
# ═══════════════════════════════════════════════════════════

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<SupportTicket(id={self.id!r}, subject={self.subject!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subject": self.subject,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  QUICK ACTIONS
# ═══════════════════════════════════════════════════════════

class QuickAction(Base):
    __tablename__ = "quick_actions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    action_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    route = Column(String, nullable=True)
    is_enabled = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<QuickAction(id={self.id!r}, action_type={self.action_type!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "route": self.route,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  IDEMPOTENCY RECORDS
# ═══════════════════════════════════════════════════════════

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=False, index=True)
    key = Column(String, nullable=False, unique=True)
    action = Column(String, nullable=False)
    token_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<IdempotencyRecord(id={self.id!r}, key={self.key!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "key": self.key,
            "action": self.action,
            "token_id": self.token_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  HOSPITAL SEQUENCES
# ═══════════════════════════════════════════════════════════

class HospitalSequence(Base):
    __tablename__ = "hospital_sequences"

    id = Column(String, primary_key=True, default=_uuid)
    hospital_id = Column(String, nullable=False, unique=True, index=True)
    mrn_seq = Column(Integer, nullable=True, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<HospitalSequence(hospital_id={self.hospital_id!r}, mrn_seq={self.mrn_seq!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hospital_id": self.hospital_id,
            "mrn_seq": self.mrn_seq,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  PHARMACY MEDICINES
# ═══════════════════════════════════════════════════════════

class PharmacyMedicine(Base):
    __tablename__ = "pharmacy_medicines"

    id = Column(String, primary_key=True, default=_uuid)
    product_id = Column(Integer, nullable=False)
    batch_no = Column(String, nullable=False)
    name = Column(String, nullable=False)
    generic_name = Column(String, nullable=True)
    type = Column(String, nullable=True)
    distributor = Column(String, nullable=True)
    purchase_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)
    stock_unit = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True, default=0)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    category = Column(String, nullable=True)
    sub_category = Column(String, nullable=True)
    hospital_id = Column(String, nullable=True, index=True)
    is_deleted = Column(Boolean, nullable=True, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PharmacyMedicine(id={self.id!r}, name={self.name!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "batch_no": self.batch_no,
            "name": self.name,
            "generic_name": self.generic_name,
            "type": self.type,
            "distributor": self.distributor,
            "purchase_price": self.purchase_price,
            "selling_price": self.selling_price,
            "stock_unit": self.stock_unit,
            "quantity": self.quantity,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "category": self.category,
            "sub_category": self.sub_category,
            "hospital_id": self.hospital_id,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ═══════════════════════════════════════════════════════════
#  PHARMACY SALES
# ═══════════════════════════════════════════════════════════

class PharmacySale(Base):
    __tablename__ = "pharmacy_sales"

    id = Column(String, primary_key=True, default=_uuid)
    hospital_id = Column(String, nullable=True, index=True)
    patient_id = Column(String, nullable=True, index=True)
    doctor_id = Column(String, nullable=True)
    medicine_id = Column(Integer, nullable=True)
    medicine_name = Column(String, nullable=True)
    quantity = Column(Integer, nullable=True)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)
    items = Column(JSON, nullable=True)
    payment_status = Column(String, nullable=True)
    sold_at = Column(DateTime(timezone=True), server_default=func.now())
    performed_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PharmacySale(id={self.id!r}, medicine_name={self.medicine_name!r})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hospital_id": self.hospital_id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine_name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "total_amount": self.total_amount,
            "items": self.items,
            "payment_status": self.payment_status,
            "sold_at": self.sold_at.isoformat() if self.sold_at else None,
            "performed_by": self.performed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
