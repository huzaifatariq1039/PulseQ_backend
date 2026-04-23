# db_automation/__init__.py
# Package exports — clean imports for all models and services

from db_automation.database import get_db, get_async_db, init_db, Base

from db_automation.models import (
    User,
    Hospital,
    Department,
    Doctor,
    Token,
    Queue,
    Payment,
    Refund,
    Wallet,
    MedicalRecord,
    ActivityLog,
    SupportTicket,
    QuickAction,
    IdempotencyRecord,
    HospitalSequence,
    PharmacyMedicine,
    PharmacySale,
)

from db_automation.services import (
    # Sync services
    UserService,
    HospitalService,
    DepartmentService,
    DoctorService,
    TokenService,
    QueueService,
    PaymentService,
    RefundService,
    WalletService,
    MedicalRecordService,
    ActivityLogService,
    SupportTicketService,
    QuickActionService,
    IdempotencyService,
    HospitalSequenceService,
    PharmacyMedicineService,
    PharmacySaleService,
    # Async services
    AsyncUserService,
    AsyncTokenService,
    AsyncPaymentService,
    AsyncActivityLogService,
)

__all__ = [
    # Database
    "get_db", "get_async_db", "init_db", "Base",
    # Models
    "User", "Hospital", "Department", "Doctor", "Token", "Queue",
    "Payment", "Refund", "Wallet", "MedicalRecord", "ActivityLog",
    "SupportTicket", "QuickAction", "IdempotencyRecord",
    "HospitalSequence", "PharmacyMedicine", "PharmacySale",
    # Sync Services
    "UserService", "HospitalService", "DepartmentService", "DoctorService",
    "TokenService", "QueueService", "PaymentService", "RefundService",
    "WalletService", "MedicalRecordService", "ActivityLogService",
    "SupportTicketService", "QuickActionService", "IdempotencyService",
    "HospitalSequenceService", "PharmacyMedicineService", "PharmacySaleService",
    # Async Services
    "AsyncUserService", "AsyncTokenService", "AsyncPaymentService",
    "AsyncActivityLogService",
]
