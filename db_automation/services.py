# db_automation/services.py
# CRUD service layer for ALL tables — sync + async, with error handling, logging, pagination, filtering

import logging
from typing import Optional, Dict, List, Any

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from db_automation.models import (
    User, Hospital, Department, Doctor, Token, Queue,
    Payment, Refund, Wallet, MedicalRecord, ActivityLog,
    SupportTicket, QuickAction, IdempotencyRecord,
    HospitalSequence, PharmacyMedicine, PharmacySale,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def _paginate(query, page: int, per_page: int):
    """Apply pagination to a query and return (query, offset, per_page)."""
    per_page = min(per_page, 100)
    offset = (page - 1) * per_page
    return query, offset, per_page


def _pages(total: int, per_page: int) -> int:
    return (total + per_page - 1) // per_page if per_page else 1


def _pagination_envelope(items, total, page, per_page) -> Dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": _pages(total, per_page),
    }


# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════

class UserService:
    """Synchronous CRUD for the users table."""

    @staticmethod
    def create_user(db: Session, name: str, password_hash: str,
                    email: str = None, role: str = "patient", phone: str = None) -> User:
        if not name:
            raise ValueError("Name is required")
        try:
            user = User(name=name, password_hash=password_hash, email=email, role=role, phone=phone)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"✅ Created user: {user.id} ({user.name})")
            return user
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create user '{name}': {e}")
            raise

    @staticmethod
    def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                logger.info(f"📋 Found user: {user.id}")
            else:
                logger.warning(f"⚠️ User not found: {user_id}")
            return user
        except Exception as e:
            logger.error(f"❌ Failed to fetch user {user_id}: {e}")
            raise

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        try:
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch user by email {email}: {e}")
            raise

    @staticmethod
    def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
        try:
            return db.query(User).filter(User.phone == phone).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch user by phone {phone}: {e}")
            raise

    @staticmethod
    def get_all_users(db: Session, page: int = 1, per_page: int = 20,
                      role: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(User)
            if role:
                query = query.filter(User.role == role.lower())
            total = query.count()
            users = query.order_by(User.created_at.desc()).offset(offset).limit(per_page).all()
            logger.info(f"📋 Fetched {len(users)} users (page {page}, role={role or 'all'})")
            return _pagination_envelope([u.to_dict() for u in users], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch users: {e}")
            raise

    @staticmethod
    def update_user(db: Session, user_id: str, updated_data: Dict[str, Any]) -> Optional[User]:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"⚠️ Cannot update — user not found: {user_id}")
                return None
            allowed = {"name", "email", "password_hash", "role", "phone", "gender",
                       "date_of_birth", "address", "hospital_id", "location_access", "mrn_by_hospital"}
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(user, k, v)
            db.commit()
            db.refresh(user)
            logger.info(f"✅ Updated user: {user.id}")
            return user
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update user {user_id}: {e}")
            raise

    @staticmethod
    def delete_user(db: Session, user_id: str) -> bool:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.warning(f"⚠️ Cannot delete — user not found: {user_id}")
                return False
            db.delete(user)
            db.commit()
            logger.info(f"🗑️ Deleted user: {user_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete user {user_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  HOSPITALS
# ═══════════════════════════════════════════════════════════

class HospitalService:
    """Synchronous CRUD for the hospitals table."""

    @staticmethod
    def create_hospital(db: Session, name: str, address: str, city: str, state: str,
                        phone: str, email: str = None, status: str = "active",
                        specializations: list = None, latitude: float = None,
                        longitude: float = None) -> Hospital:
        try:
            hospital = Hospital(
                name=name, address=address, city=city, state=state,
                phone=phone, email=email, status=status,
                specializations=specializations or [], latitude=latitude, longitude=longitude,
            )
            db.add(hospital)
            db.commit()
            db.refresh(hospital)
            logger.info(f"✅ Created hospital: {hospital.id} ({hospital.name})")
            return hospital
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create hospital '{name}': {e}")
            raise

    @staticmethod
    def get_hospital_by_id(db: Session, hospital_id: str) -> Optional[Hospital]:
        try:
            h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
            if not h:
                logger.warning(f"⚠️ Hospital not found: {hospital_id}")
            return h
        except Exception as e:
            logger.error(f"❌ Failed to fetch hospital {hospital_id}: {e}")
            raise

    @staticmethod
    def get_all_hospitals(db: Session, page: int = 1, per_page: int = 20,
                          city: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Hospital)
            if city:
                query = query.filter(Hospital.city.ilike(f"%{city}%"))
            if status:
                query = query.filter(Hospital.status == status)
            total = query.count()
            hospitals = query.order_by(Hospital.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([h.to_dict() for h in hospitals], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch hospitals: {e}")
            raise

    @staticmethod
    def update_hospital(db: Session, hospital_id: str, updated_data: Dict[str, Any]) -> Optional[Hospital]:
        try:
            h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
            if not h:
                return None
            allowed = {"name", "address", "city", "state", "phone", "email", "status",
                       "specializations", "latitude", "longitude", "rating", "review_count"}
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(h, k, v)
            db.commit()
            db.refresh(h)
            logger.info(f"✅ Updated hospital: {hospital_id}")
            return h
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update hospital {hospital_id}: {e}")
            raise

    @staticmethod
    def delete_hospital(db: Session, hospital_id: str) -> bool:
        try:
            h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
            if not h:
                return False
            db.delete(h)
            db.commit()
            logger.info(f"🗑️ Deleted hospital: {hospital_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete hospital {hospital_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  DEPARTMENTS
# ═══════════════════════════════════════════════════════════

class DepartmentService:
    """Synchronous CRUD for the departments table."""

    @staticmethod
    def create_department(db: Session, name: str, hospital_id: str) -> Department:
        try:
            dept = Department(name=name, hospital_id=hospital_id)
            db.add(dept)
            db.commit()
            db.refresh(dept)
            logger.info(f"✅ Created department: {dept.id} ({dept.name})")
            return dept
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create department '{name}': {e}")
            raise

    @staticmethod
    def get_department_by_id(db: Session, dept_id: str) -> Optional[Department]:
        try:
            return db.query(Department).filter(Department.id == dept_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch department {dept_id}: {e}")
            raise

    @staticmethod
    def get_departments_by_hospital(db: Session, hospital_id: str,
                                    page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Department).filter(Department.hospital_id == hospital_id)
            total = query.count()
            depts = query.order_by(Department.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([d.to_dict() for d in depts], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch departments for hospital {hospital_id}: {e}")
            raise

    @staticmethod
    def update_department(db: Session, dept_id: str, updated_data: Dict[str, Any]) -> Optional[Department]:
        try:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            if not dept:
                return None
            for k, v in updated_data.items():
                if k in {"name", "hospital_id"}:
                    setattr(dept, k, v)
            db.commit()
            db.refresh(dept)
            return dept
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update department {dept_id}: {e}")
            raise

    @staticmethod
    def delete_department(db: Session, dept_id: str) -> bool:
        try:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            if not dept:
                return False
            db.delete(dept)
            db.commit()
            logger.info(f"🗑️ Deleted department: {dept_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete department {dept_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  DOCTORS
# ═══════════════════════════════════════════════════════════

class DoctorService:
    """Synchronous CRUD for the doctors table."""

    @staticmethod
    def create_doctor(db: Session, name: str, specialization: str, hospital_id: str,
                      consultation_fee: float, start_time: str, end_time: str,
                      **kwargs) -> Doctor:
        try:
            doctor = Doctor(
                name=name, specialization=specialization, hospital_id=hospital_id,
                consultation_fee=consultation_fee, start_time=start_time, end_time=end_time,
                **{k: v for k, v in kwargs.items() if hasattr(Doctor, k)},
            )
            db.add(doctor)
            db.commit()
            db.refresh(doctor)
            logger.info(f"✅ Created doctor: {doctor.id} ({doctor.name})")
            return doctor
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create doctor '{name}': {e}")
            raise

    @staticmethod
    def get_doctor_by_id(db: Session, doctor_id: str) -> Optional[Doctor]:
        try:
            return db.query(Doctor).filter(Doctor.id == doctor_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch doctor {doctor_id}: {e}")
            raise

    @staticmethod
    def get_all_doctors(db: Session, page: int = 1, per_page: int = 20,
                        hospital_id: Optional[str] = None,
                        specialization: Optional[str] = None,
                        status: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Doctor)
            if hospital_id:
                query = query.filter(Doctor.hospital_id == hospital_id)
            if specialization:
                query = query.filter(Doctor.specialization.ilike(f"%{specialization}%"))
            if status:
                query = query.filter(Doctor.status == status)
            total = query.count()
            doctors = query.order_by(Doctor.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([d.to_dict() for d in doctors], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch doctors: {e}")
            raise

    @staticmethod
    def update_doctor(db: Session, doctor_id: str, updated_data: Dict[str, Any]) -> Optional[Doctor]:
        try:
            doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
            if not doctor:
                return None
            allowed = {"name", "specialization", "subcategory", "hospital_id", "email", "rating",
                       "review_count", "consultation_fee", "session_fee", "has_session",
                       "pricing_type", "status", "available_days", "start_time", "end_time",
                       "avatar_initials", "patients_per_day", "user_id"}
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(doctor, k, v)
            db.commit()
            db.refresh(doctor)
            logger.info(f"✅ Updated doctor: {doctor_id}")
            return doctor
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update doctor {doctor_id}: {e}")
            raise

    @staticmethod
    def delete_doctor(db: Session, doctor_id: str) -> bool:
        try:
            doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
            if not doctor:
                return False
            db.delete(doctor)
            db.commit()
            logger.info(f"🗑️ Deleted doctor: {doctor_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete doctor {doctor_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  TOKENS (Appointments)
# ═══════════════════════════════════════════════════════════

class TokenService:
    """Synchronous CRUD for the tokens table."""

    @staticmethod
    def create_token(db: Session, patient_id: str, doctor_id: str, hospital_id: str,
                     token_number: int, hex_code: str, appointment_date,
                     **kwargs) -> Token:
        try:
            token = Token(
                patient_id=patient_id, doctor_id=doctor_id, hospital_id=hospital_id,
                token_number=token_number, hex_code=hex_code, appointment_date=appointment_date,
                **{k: v for k, v in kwargs.items() if hasattr(Token, k)},
            )
            db.add(token)
            db.commit()
            db.refresh(token)
            logger.info(f"✅ Created token: {token.id} (#{token.token_number})")
            return token
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create token: {e}")
            raise

    @staticmethod
    def get_token_by_id(db: Session, token_id: str) -> Optional[Token]:
        try:
            return db.query(Token).filter(Token.id == token_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch token {token_id}: {e}")
            raise

    @staticmethod
    def get_token_by_hex(db: Session, hex_code: str) -> Optional[Token]:
        try:
            return db.query(Token).filter(Token.hex_code == hex_code).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch token by hex {hex_code}: {e}")
            raise

    @staticmethod
    def get_all_tokens(db: Session, page: int = 1, per_page: int = 20,
                       patient_id: Optional[str] = None,
                       doctor_id: Optional[str] = None,
                       hospital_id: Optional[str] = None,
                       status: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Token)
            if patient_id:
                query = query.filter(Token.patient_id == patient_id)
            if doctor_id:
                query = query.filter(Token.doctor_id == doctor_id)
            if hospital_id:
                query = query.filter(Token.hospital_id == hospital_id)
            if status:
                query = query.filter(Token.status == status)
            total = query.count()
            tokens = query.order_by(Token.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([t.to_dict() for t in tokens], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch tokens: {e}")
            raise

    @staticmethod
    def update_token(db: Session, token_id: str, updated_data: Dict[str, Any]) -> Optional[Token]:
        try:
            token = db.query(Token).filter(Token.id == token_id).first()
            if not token:
                return None
            allowed = {
                "status", "payment_status", "payment_method", "queue_position", "total_queue",
                "estimated_wait_time", "consultation_fee", "session_fee", "total_fee",
                "queue_opt_in", "queue_opted_in_at", "confirmed", "confirmation_status",
                "confirmed_at", "cancelled_at", "started_at", "completed_at",
                "duration_minutes", "reason_for_visit", "mrn", "display_code",
            }
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(token, k, v)
            db.commit()
            db.refresh(token)
            logger.info(f"✅ Updated token: {token_id}")
            return token
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update token {token_id}: {e}")
            raise

    @staticmethod
    def delete_token(db: Session, token_id: str) -> bool:
        try:
            token = db.query(Token).filter(Token.id == token_id).first()
            if not token:
                return False
            db.delete(token)
            db.commit()
            logger.info(f"🗑️ Deleted token: {token_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete token {token_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  QUEUES
# ═══════════════════════════════════════════════════════════

class QueueService:
    """Synchronous CRUD for the queues table."""

    @staticmethod
    def create_or_update_queue(db: Session, doctor_id: str, **kwargs) -> Queue:
        """Upsert: create if not exists, else update."""
        try:
            queue = db.query(Queue).filter(Queue.doctor_id == doctor_id).first()
            if queue:
                for k, v in kwargs.items():
                    if hasattr(queue, k):
                        setattr(queue, k, v)
            else:
                queue = Queue(doctor_id=doctor_id, **{k: v for k, v in kwargs.items() if hasattr(Queue, k)})
                db.add(queue)
            db.commit()
            db.refresh(queue)
            logger.info(f"✅ Upserted queue for doctor: {doctor_id}")
            return queue
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to upsert queue for doctor {doctor_id}: {e}")
            raise

    @staticmethod
    def get_queue_by_doctor(db: Session, doctor_id: str) -> Optional[Queue]:
        try:
            return db.query(Queue).filter(Queue.doctor_id == doctor_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch queue for doctor {doctor_id}: {e}")
            raise

    @staticmethod
    def get_all_queues(db: Session, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            total = db.query(Queue).count()
            queues = db.query(Queue).offset(offset).limit(per_page).all()
            return _pagination_envelope([q.to_dict() for q in queues], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch queues: {e}")
            raise

    @staticmethod
    def delete_queue(db: Session, queue_id: str) -> bool:
        try:
            queue = db.query(Queue).filter(Queue.id == queue_id).first()
            if not queue:
                return False
            db.delete(queue)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete queue {queue_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  PAYMENTS
# ═══════════════════════════════════════════════════════════

class PaymentService:
    """Synchronous CRUD for the payments table."""

    @staticmethod
    def create_payment(db: Session, token_id: str, amount: float, method: str,
                       status: str = "pending", transaction_id: str = None) -> Payment:
        try:
            payment = Payment(token_id=token_id, amount=amount, method=method,
                              status=status, transaction_id=transaction_id)
            db.add(payment)
            db.commit()
            db.refresh(payment)
            logger.info(f"✅ Created payment: {payment.id} (amount={amount})")
            return payment
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create payment for token {token_id}: {e}")
            raise

    @staticmethod
    def get_payment_by_id(db: Session, payment_id: str) -> Optional[Payment]:
        try:
            return db.query(Payment).filter(Payment.id == payment_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch payment {payment_id}: {e}")
            raise

    @staticmethod
    def get_payments_by_token(db: Session, token_id: str) -> List[Payment]:
        try:
            return db.query(Payment).filter(Payment.token_id == token_id).all()
        except Exception as e:
            logger.error(f"❌ Failed to fetch payments for token {token_id}: {e}")
            raise

    @staticmethod
    def get_all_payments(db: Session, page: int = 1, per_page: int = 20,
                         status: Optional[str] = None, method: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Payment)
            if status:
                query = query.filter(Payment.status == status)
            if method:
                query = query.filter(Payment.method == method)
            total = query.count()
            payments = query.order_by(Payment.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([p.to_dict() for p in payments], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch payments: {e}")
            raise

    @staticmethod
    def update_payment(db: Session, payment_id: str, updated_data: Dict[str, Any]) -> Optional[Payment]:
        try:
            payment = db.query(Payment).filter(Payment.id == payment_id).first()
            if not payment:
                return None
            for k, v in updated_data.items():
                if k in {"status", "transaction_id", "amount", "method"}:
                    setattr(payment, k, v)
            db.commit()
            db.refresh(payment)
            return payment
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update payment {payment_id}: {e}")
            raise

    @staticmethod
    def delete_payment(db: Session, payment_id: str) -> bool:
        try:
            payment = db.query(Payment).filter(Payment.id == payment_id).first()
            if not payment:
                return False
            db.delete(payment)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete payment {payment_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  REFUNDS
# ═══════════════════════════════════════════════════════════

class RefundService:
    """Synchronous CRUD for the refunds table."""

    @staticmethod
    def create_refund(db: Session, user_id: str, token_id: str, amount: float,
                      method: str, reason: str = None, status: str = "pending",
                      transaction_id: str = None) -> Refund:
        try:
            refund = Refund(user_id=user_id, token_id=token_id, amount=amount,
                            method=method, reason=reason, status=status,
                            transaction_id=transaction_id)
            db.add(refund)
            db.commit()
            db.refresh(refund)
            logger.info(f"✅ Created refund: {refund.id}")
            return refund
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create refund: {e}")
            raise

    @staticmethod
    def get_refund_by_id(db: Session, refund_id: str) -> Optional[Refund]:
        try:
            return db.query(Refund).filter(Refund.id == refund_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch refund {refund_id}: {e}")
            raise

    @staticmethod
    def get_refunds_by_user(db: Session, user_id: str, page: int = 1,
                            per_page: int = 20) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(Refund).filter(Refund.user_id == user_id)
            total = query.count()
            refunds = query.order_by(Refund.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([r.to_dict() for r in refunds], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch refunds for user {user_id}: {e}")
            raise

    @staticmethod
    def update_refund_status(db: Session, refund_id: str, status: str,
                             transaction_id: str = None) -> Optional[Refund]:
        try:
            refund = db.query(Refund).filter(Refund.id == refund_id).first()
            if not refund:
                return None
            refund.status = status
            if transaction_id:
                refund.transaction_id = transaction_id
            db.commit()
            db.refresh(refund)
            return refund
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update refund {refund_id}: {e}")
            raise

    @staticmethod
    def delete_refund(db: Session, refund_id: str) -> bool:
        try:
            refund = db.query(Refund).filter(Refund.id == refund_id).first()
            if not refund:
                return False
            db.delete(refund)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete refund {refund_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  WALLETS
# ═══════════════════════════════════════════════════════════

class WalletService:
    """Synchronous CRUD for the wallets table."""

    @staticmethod
    def create_wallet(db: Session, user_id: str, currency: str = "PKR") -> Wallet:
        try:
            wallet = Wallet(user_id=user_id, balance=0.0, currency=currency)
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
            logger.info(f"✅ Created wallet for user: {user_id}")
            return wallet
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create wallet for user {user_id}: {e}")
            raise

    @staticmethod
    def get_wallet_by_user(db: Session, user_id: str) -> Optional[Wallet]:
        try:
            return db.query(Wallet).filter(Wallet.user_id == user_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch wallet for user {user_id}: {e}")
            raise

    @staticmethod
    def credit_wallet(db: Session, user_id: str, amount: float) -> Optional[Wallet]:
        """Add funds to wallet."""
        try:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            if not wallet:
                logger.warning(f"⚠️ Wallet not found for user: {user_id}")
                return None
            wallet.balance = (wallet.balance or 0.0) + amount
            db.commit()
            db.refresh(wallet)
            logger.info(f"✅ Credited {amount} to wallet of user: {user_id}")
            return wallet
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to credit wallet for user {user_id}: {e}")
            raise

    @staticmethod
    def debit_wallet(db: Session, user_id: str, amount: float) -> Optional[Wallet]:
        """Deduct funds from wallet; raises ValueError if insufficient balance."""
        try:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            if not wallet:
                return None
            if (wallet.balance or 0.0) < amount:
                raise ValueError(f"Insufficient wallet balance: {wallet.balance} < {amount}")
            wallet.balance = wallet.balance - amount
            db.commit()
            db.refresh(wallet)
            logger.info(f"✅ Debited {amount} from wallet of user: {user_id}")
            return wallet
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to debit wallet for user {user_id}: {e}")
            raise

    @staticmethod
    def delete_wallet(db: Session, user_id: str) -> bool:
        try:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            if not wallet:
                return False
            db.delete(wallet)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete wallet for user {user_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  MEDICAL RECORDS
# ═══════════════════════════════════════════════════════════

class MedicalRecordService:
    """Synchronous CRUD for the medical_records table."""

    @staticmethod
    def create_record(db: Session, user_id: str, filename: str, file_path: str,
                      file_type: str, file_size: int, record_type: str = None,
                      description: str = None) -> MedicalRecord:
        try:
            record = MedicalRecord(
                user_id=user_id, filename=filename, file_path=file_path,
                file_type=file_type, file_size=file_size,
                record_type=record_type, description=description,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            logger.info(f"✅ Created medical record: {record.id}")
            return record
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create medical record: {e}")
            raise

    @staticmethod
    def get_record_by_id(db: Session, record_id: str) -> Optional[MedicalRecord]:
        try:
            return db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch medical record {record_id}: {e}")
            raise

    @staticmethod
    def get_records_by_user(db: Session, user_id: str, page: int = 1, per_page: int = 20,
                            record_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(MedicalRecord).filter(MedicalRecord.user_id == user_id)
            if record_type:
                query = query.filter(MedicalRecord.record_type == record_type)
            total = query.count()
            records = query.order_by(MedicalRecord.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([r.to_dict() for r in records], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch medical records for user {user_id}: {e}")
            raise

    @staticmethod
    def delete_record(db: Session, record_id: str) -> bool:
        try:
            record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
            if not record:
                return False
            db.delete(record)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete medical record {record_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════

class ActivityLogService:
    """Synchronous CRUD for the activity_logs table."""

    @staticmethod
    def log(db: Session, user_id: str, activity_type: str, description: str,
            meta_data: dict = None) -> ActivityLog:
        try:
            log = ActivityLog(
                user_id=user_id, activity_type=activity_type,
                description=description, meta_data=meta_data,
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            logger.info(f"✅ Activity logged: [{activity_type}] for user {user_id}")
            return log
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to log activity for user {user_id}: {e}")
            raise

    @staticmethod
    def get_logs_by_user(db: Session, user_id: str, page: int = 1, per_page: int = 20,
                         activity_type: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(ActivityLog).filter(ActivityLog.user_id == user_id)
            if activity_type:
                query = query.filter(ActivityLog.activity_type == activity_type)
            total = query.count()
            logs = query.order_by(ActivityLog.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([l.to_dict() for l in logs], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch activity logs for user {user_id}: {e}")
            raise

    @staticmethod
    def delete_log(db: Session, log_id: str) -> bool:
        try:
            log = db.query(ActivityLog).filter(ActivityLog.id == log_id).first()
            if not log:
                return False
            db.delete(log)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete activity log {log_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  SUPPORT TICKETS
# ═══════════════════════════════════════════════════════════

class SupportTicketService:
    """Synchronous CRUD for the support_tickets table."""

    @staticmethod
    def create_ticket(db: Session, user_id: str, subject: str, description: str,
                      category: str = None, priority: str = "medium",
                      status: str = "open") -> SupportTicket:
        try:
            ticket = SupportTicket(
                user_id=user_id, subject=subject, description=description,
                category=category, priority=priority, status=status,
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
            logger.info(f"✅ Created support ticket: {ticket.id}")
            return ticket
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create support ticket: {e}")
            raise

    @staticmethod
    def get_ticket_by_id(db: Session, ticket_id: str) -> Optional[SupportTicket]:
        try:
            return db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch ticket {ticket_id}: {e}")
            raise

    @staticmethod
    def get_all_tickets(db: Session, page: int = 1, per_page: int = 20,
                        user_id: Optional[str] = None, status: Optional[str] = None,
                        priority: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(SupportTicket)
            if user_id:
                query = query.filter(SupportTicket.user_id == user_id)
            if status:
                query = query.filter(SupportTicket.status == status)
            if priority:
                query = query.filter(SupportTicket.priority == priority)
            total = query.count()
            tickets = query.order_by(SupportTicket.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([t.to_dict() for t in tickets], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch support tickets: {e}")
            raise

    @staticmethod
    def update_ticket(db: Session, ticket_id: str, updated_data: Dict[str, Any]) -> Optional[SupportTicket]:
        try:
            ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
            if not ticket:
                return None
            for k, v in updated_data.items():
                if k in {"subject", "description", "category", "priority", "status"}:
                    setattr(ticket, k, v)
            db.commit()
            db.refresh(ticket)
            return ticket
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update ticket {ticket_id}: {e}")
            raise

    @staticmethod
    def delete_ticket(db: Session, ticket_id: str) -> bool:
        try:
            ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
            if not ticket:
                return False
            db.delete(ticket)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete ticket {ticket_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  QUICK ACTIONS
# ═══════════════════════════════════════════════════════════

class QuickActionService:
    """Synchronous CRUD for the quick_actions table."""

    @staticmethod
    def create_action(db: Session, user_id: str, action_type: str, title: str,
                      description: str = None, icon: str = None, route: str = None,
                      is_enabled: bool = True) -> QuickAction:
        try:
            action = QuickAction(
                user_id=user_id, action_type=action_type, title=title,
                description=description, icon=icon, route=route, is_enabled=is_enabled,
            )
            db.add(action)
            db.commit()
            db.refresh(action)
            logger.info(f"✅ Created quick action: {action.id}")
            return action
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create quick action: {e}")
            raise

    @staticmethod
    def get_actions_by_user(db: Session, user_id: str,
                            enabled_only: bool = False) -> List[QuickAction]:
        try:
            query = db.query(QuickAction).filter(QuickAction.user_id == user_id)
            if enabled_only:
                query = query.filter(QuickAction.is_enabled == True)
            return query.order_by(QuickAction.created_at).all()
        except Exception as e:
            logger.error(f"❌ Failed to fetch quick actions for user {user_id}: {e}")
            raise

    @staticmethod
    def update_action(db: Session, action_id: str, updated_data: Dict[str, Any]) -> Optional[QuickAction]:
        try:
            action = db.query(QuickAction).filter(QuickAction.id == action_id).first()
            if not action:
                return None
            for k, v in updated_data.items():
                if k in {"action_type", "title", "description", "icon", "route", "is_enabled"}:
                    setattr(action, k, v)
            db.commit()
            db.refresh(action)
            return action
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update quick action {action_id}: {e}")
            raise

    @staticmethod
    def delete_action(db: Session, action_id: str) -> bool:
        try:
            action = db.query(QuickAction).filter(QuickAction.id == action_id).first()
            if not action:
                return False
            db.delete(action)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete quick action {action_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  IDEMPOTENCY RECORDS
# ═══════════════════════════════════════════════════════════

class IdempotencyService:
    """Synchronous CRUD for the idempotency_records table."""

    @staticmethod
    def create(db: Session, user_id: str, key: str, action: str,
               token_id: str = None) -> IdempotencyRecord:
        try:
            record = IdempotencyRecord(user_id=user_id, key=key, action=action, token_id=token_id)
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create idempotency record for key {key}: {e}")
            raise

    @staticmethod
    def get_by_key(db: Session, key: str) -> Optional[IdempotencyRecord]:
        try:
            return db.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch idempotency record {key}: {e}")
            raise

    @staticmethod
    def exists(db: Session, key: str) -> bool:
        try:
            return db.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).count() > 0
        except Exception as e:
            logger.error(f"❌ Failed to check idempotency key {key}: {e}")
            raise

    @staticmethod
    def delete(db: Session, key: str) -> bool:
        try:
            record = db.query(IdempotencyRecord).filter(IdempotencyRecord.key == key).first()
            if not record:
                return False
            db.delete(record)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete idempotency record {key}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  HOSPITAL SEQUENCES
# ═══════════════════════════════════════════════════════════

class HospitalSequenceService:
    """Synchronous CRUD for the hospital_sequences table."""

    @staticmethod
    def get_or_create(db: Session, hospital_id: str) -> HospitalSequence:
        try:
            seq = db.query(HospitalSequence).filter(
                HospitalSequence.hospital_id == hospital_id
            ).first()
            if not seq:
                seq = HospitalSequence(hospital_id=hospital_id, mrn_seq=0)
                db.add(seq)
                db.commit()
                db.refresh(seq)
                logger.info(f"✅ Created hospital sequence for: {hospital_id}")
            return seq
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to get/create sequence for {hospital_id}: {e}")
            raise

    @staticmethod
    def next_mrn(db: Session, hospital_id: str) -> int:
        """Atomically increment and return the next MRN sequence number."""
        try:
            seq = db.query(HospitalSequence).filter(
                HospitalSequence.hospital_id == hospital_id
            ).with_for_update().first()
            if not seq:
                seq = HospitalSequence(hospital_id=hospital_id, mrn_seq=1)
                db.add(seq)
            else:
                seq.mrn_seq = (seq.mrn_seq or 0) + 1
            db.commit()
            db.refresh(seq)
            logger.info(f"✅ Next MRN for {hospital_id}: {seq.mrn_seq}")
            return seq.mrn_seq
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to get next MRN for {hospital_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  PHARMACY MEDICINES
# ═══════════════════════════════════════════════════════════

class PharmacyMedicineService:
    """Synchronous CRUD for the pharmacy_medicines table."""

    @staticmethod
    def create_medicine(db: Session, product_id: int, batch_no: str, name: str,
                        purchase_price: float, selling_price: float, hospital_id: str = None,
                        **kwargs) -> PharmacyMedicine:
        try:
            medicine = PharmacyMedicine(
                product_id=product_id, batch_no=batch_no, name=name,
                purchase_price=purchase_price, selling_price=selling_price,
                hospital_id=hospital_id,
                **{k: v for k, v in kwargs.items() if hasattr(PharmacyMedicine, k)},
            )
            db.add(medicine)
            db.commit()
            db.refresh(medicine)
            logger.info(f"✅ Created medicine: {medicine.id} ({medicine.name})")
            return medicine
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create medicine '{name}': {e}")
            raise

    @staticmethod
    def get_medicine_by_id(db: Session, medicine_id: str) -> Optional[PharmacyMedicine]:
        try:
            return db.query(PharmacyMedicine).filter(
                PharmacyMedicine.id == medicine_id,
                PharmacyMedicine.is_deleted == False,
            ).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch medicine {medicine_id}: {e}")
            raise

    @staticmethod
    def get_all_medicines(db: Session, page: int = 1, per_page: int = 20,
                          hospital_id: Optional[str] = None,
                          category: Optional[str] = None,
                          include_deleted: bool = False) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(PharmacyMedicine)
            if not include_deleted:
                query = query.filter(PharmacyMedicine.is_deleted == False)
            if hospital_id:
                query = query.filter(PharmacyMedicine.hospital_id == hospital_id)
            if category:
                query = query.filter(PharmacyMedicine.category == category)
            total = query.count()
            medicines = query.order_by(PharmacyMedicine.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([m.to_dict() for m in medicines], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch medicines: {e}")
            raise

    @staticmethod
    def update_medicine(db: Session, medicine_id: str, updated_data: Dict[str, Any]) -> Optional[PharmacyMedicine]:
        try:
            medicine = db.query(PharmacyMedicine).filter(PharmacyMedicine.id == medicine_id).first()
            if not medicine:
                return None
            allowed = {"name", "generic_name", "type", "distributor", "purchase_price",
                       "selling_price", "stock_unit", "quantity", "expiration_date",
                       "category", "sub_category", "batch_no"}
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(medicine, k, v)
            db.commit()
            db.refresh(medicine)
            return medicine
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update medicine {medicine_id}: {e}")
            raise

    @staticmethod
    def soft_delete_medicine(db: Session, medicine_id: str) -> bool:
        """Soft-delete: sets is_deleted=True and deleted_at timestamp."""
        from datetime import datetime, timezone
        try:
            medicine = db.query(PharmacyMedicine).filter(PharmacyMedicine.id == medicine_id).first()
            if not medicine:
                return False
            medicine.is_deleted = True
            medicine.deleted_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"🗑️ Soft-deleted medicine: {medicine_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to soft-delete medicine {medicine_id}: {e}")
            raise

    @staticmethod
    def hard_delete_medicine(db: Session, medicine_id: str) -> bool:
        try:
            medicine = db.query(PharmacyMedicine).filter(PharmacyMedicine.id == medicine_id).first()
            if not medicine:
                return False
            db.delete(medicine)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to hard-delete medicine {medicine_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  PHARMACY SALES
# ═══════════════════════════════════════════════════════════

class PharmacySaleService:
    """Synchronous CRUD for the pharmacy_sales table."""

    @staticmethod
    def create_sale(db: Session, hospital_id: str = None, patient_id: str = None,
                    doctor_id: str = None, items: list = None, total_amount: float = None,
                    payment_status: str = "pending", performed_by: str = None,
                    **kwargs) -> PharmacySale:
        try:
            sale = PharmacySale(
                hospital_id=hospital_id, patient_id=patient_id, doctor_id=doctor_id,
                items=items, total_amount=total_amount, payment_status=payment_status,
                performed_by=performed_by,
                **{k: v for k, v in kwargs.items() if hasattr(PharmacySale, k)},
            )
            db.add(sale)
            db.commit()
            db.refresh(sale)
            logger.info(f"✅ Created pharmacy sale: {sale.id}")
            return sale
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to create pharmacy sale: {e}")
            raise

    @staticmethod
    def get_sale_by_id(db: Session, sale_id: str) -> Optional[PharmacySale]:
        try:
            return db.query(PharmacySale).filter(PharmacySale.id == sale_id).first()
        except Exception as e:
            logger.error(f"❌ Failed to fetch sale {sale_id}: {e}")
            raise

    @staticmethod
    def get_all_sales(db: Session, page: int = 1, per_page: int = 20,
                      hospital_id: Optional[str] = None,
                      patient_id: Optional[str] = None,
                      payment_status: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = db.query(PharmacySale)
            if hospital_id:
                query = query.filter(PharmacySale.hospital_id == hospital_id)
            if patient_id:
                query = query.filter(PharmacySale.patient_id == patient_id)
            if payment_status:
                query = query.filter(PharmacySale.payment_status == payment_status)
            total = query.count()
            sales = query.order_by(PharmacySale.created_at.desc()).offset(offset).limit(per_page).all()
            return _pagination_envelope([s.to_dict() for s in sales], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ Failed to fetch pharmacy sales: {e}")
            raise

    @staticmethod
    def update_sale(db: Session, sale_id: str, updated_data: Dict[str, Any]) -> Optional[PharmacySale]:
        try:
            sale = db.query(PharmacySale).filter(PharmacySale.id == sale_id).first()
            if not sale:
                return None
            for k, v in updated_data.items():
                if k in {"payment_status", "total_amount", "items", "performed_by"}:
                    setattr(sale, k, v)
            db.commit()
            db.refresh(sale)
            return sale
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to update pharmacy sale {sale_id}: {e}")
            raise

    @staticmethod
    def delete_sale(db: Session, sale_id: str) -> bool:
        try:
            sale = db.query(PharmacySale).filter(PharmacySale.id == sale_id).first()
            if not sale:
                return False
            db.delete(sale)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to delete sale {sale_id}: {e}")
            raise


# ═══════════════════════════════════════════════════════════
#  ASYNC COUNTERPARTS
# ═══════════════════════════════════════════════════════════

class AsyncUserService:
    """Async CRUD for the users table."""

    @staticmethod
    async def create_user(db: AsyncSession, name: str, password_hash: str,
                          email: str = None, role: str = "patient", phone: str = None) -> User:
        if not name:
            raise ValueError("Name is required")
        try:
            user = User(name=name, password_hash=password_hash, email=email, role=role, phone=phone)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"✅ [ASYNC] Created user: {user.id}")
            return user
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to create user: {e}")
            raise

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        try:
            result = await db.execute(select(User).filter(User.id == user_id))
            return result.scalars().first()
        except Exception as e:
            logger.error(f"❌ [ASYNC] Failed to fetch user {user_id}: {e}")
            raise

    @staticmethod
    async def get_all_users(db: AsyncSession, page: int = 1, per_page: int = 20,
                            role: Optional[str] = None) -> Dict[str, Any]:
        try:
            per_page = min(per_page, 100)
            offset = (page - 1) * per_page
            query = select(User)
            count_query = select(func.count(User.id))
            if role:
                query = query.filter(User.role == role.lower())
                count_query = count_query.filter(User.role == role.lower())
            total = (await db.execute(count_query)).scalar()
            result = await db.execute(query.order_by(User.created_at.desc()).offset(offset).limit(per_page))
            users = result.scalars().all()
            return _pagination_envelope([u.to_dict() for u in users], total, page, per_page)
        except Exception as e:
            logger.error(f"❌ [ASYNC] Failed to fetch users: {e}")
            raise

    @staticmethod
    async def update_user(db: AsyncSession, user_id: str, updated_data: Dict[str, Any]) -> Optional[User]:
        try:
            result = await db.execute(select(User).filter(User.id == user_id))
            user = result.scalars().first()
            if not user:
                return None
            allowed = {"name", "email", "password_hash", "role", "phone", "gender",
                       "date_of_birth", "address", "hospital_id", "location_access", "mrn_by_hospital"}
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(user, k, v)
            await db.commit()
            await db.refresh(user)
            return user
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to update user {user_id}: {e}")
            raise

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: str) -> bool:
        try:
            result = await db.execute(select(User).filter(User.id == user_id))
            user = result.scalars().first()
            if not user:
                return False
            await db.delete(user)
            await db.commit()
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to delete user {user_id}: {e}")
            raise


class AsyncTokenService:
    """Async CRUD for the tokens table."""

    @staticmethod
    async def create_token(db: AsyncSession, patient_id: str, doctor_id: str, hospital_id: str,
                           token_number: int, hex_code: str, appointment_date, **kwargs) -> Token:
        try:
            token = Token(
                patient_id=patient_id, doctor_id=doctor_id, hospital_id=hospital_id,
                token_number=token_number, hex_code=hex_code, appointment_date=appointment_date,
                **{k: v for k, v in kwargs.items() if hasattr(Token, k)},
            )
            db.add(token)
            await db.commit()
            await db.refresh(token)
            logger.info(f"✅ [ASYNC] Created token: {token.id}")
            return token
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to create token: {e}")
            raise

    @staticmethod
    async def get_token_by_id(db: AsyncSession, token_id: str) -> Optional[Token]:
        try:
            result = await db.execute(select(Token).filter(Token.id == token_id))
            return result.scalars().first()
        except Exception as e:
            logger.error(f"❌ [ASYNC] Failed to fetch token {token_id}: {e}")
            raise

    @staticmethod
    async def update_token(db: AsyncSession, token_id: str, updated_data: Dict[str, Any]) -> Optional[Token]:
        try:
            result = await db.execute(select(Token).filter(Token.id == token_id))
            token = result.scalars().first()
            if not token:
                return None
            allowed = {
                "status", "payment_status", "payment_method", "queue_position", "total_queue",
                "estimated_wait_time", "confirmed", "confirmation_status", "confirmed_at",
                "cancelled_at", "started_at", "completed_at", "duration_minutes",
                "reason_for_visit", "mrn", "display_code",
            }
            for k, v in updated_data.items():
                if k in allowed:
                    setattr(token, k, v)
            await db.commit()
            await db.refresh(token)
            return token
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to update token {token_id}: {e}")
            raise


class AsyncPaymentService:
    """Async CRUD for the payments table."""

    @staticmethod
    async def create_payment(db: AsyncSession, token_id: str, amount: float, method: str,
                             status: str = "pending", transaction_id: str = None) -> Payment:
        try:
            payment = Payment(token_id=token_id, amount=amount, method=method,
                              status=status, transaction_id=transaction_id)
            db.add(payment)
            await db.commit()
            await db.refresh(payment)
            logger.info(f"✅ [ASYNC] Created payment: {payment.id}")
            return payment
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to create payment: {e}")
            raise

    @staticmethod
    async def update_payment(db: AsyncSession, payment_id: str, updated_data: Dict[str, Any]) -> Optional[Payment]:
        try:
            result = await db.execute(select(Payment).filter(Payment.id == payment_id))
            payment = result.scalars().first()
            if not payment:
                return None
            for k, v in updated_data.items():
                if k in {"status", "transaction_id", "amount", "method"}:
                    setattr(payment, k, v)
            await db.commit()
            await db.refresh(payment)
            return payment
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to update payment {payment_id}: {e}")
            raise


class AsyncActivityLogService:
    """Async activity logging."""

    @staticmethod
    async def log(db: AsyncSession, user_id: str, activity_type: str,
                  description: str, meta_data: dict = None) -> ActivityLog:
        try:
            log = ActivityLog(user_id=user_id, activity_type=activity_type,
                              description=description, meta_data=meta_data)
            db.add(log)
            await db.commit()
            await db.refresh(log)
            logger.info(f"✅ [ASYNC] Logged activity [{activity_type}] for user {user_id}")
            return log
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ [ASYNC] Failed to log activity: {e}")
            raise
