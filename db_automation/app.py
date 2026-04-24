# db_automation/app.py
# Full usage examples for ALL tables — sync CRUD operations

import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

from db_automation.database import init_db, get_db
from db_automation.services import (
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
)
from sqlalchemy import or_
from db_automation.models import (
    User, Wallet, Queue, HospitalSequence, Department,
    ActivityLog, QuickAction, PharmacySale, SupportTicket,
    MedicalRecord, Refund, Token, Doctor, Payment
)

def section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def step(label: str):
    print(f"\n  ── {label}")


# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════

def run_users(db):
    section("USERS")

    step("CREATE")

    patient = db.query(User).filter(User.email == "ali@example.com").first()
    if not patient:
        patient = UserService.create_user(
            db, name="Ali Hassan", password_hash="hashed_pw_001",
            role="patient", phone="+923001112222", email="ali@example.com",
        )

    doctor_user = db.query(User).filter(User.email == "doctor@example.com").first()
    if not doctor_user:
        doctor_user = UserService.create_user(
            db, name="Dr. Smith", password_hash="hashed_pw_002",
            role="doctor", phone="+923001112223", email="doctor@example.com",
        )

    admin = db.query(User).filter(User.email == "admin@example.com").first()
    if not admin:
        admin = UserService.create_user(
            db, name="Admin User", password_hash="hashed_pw_003",
            role="admin", phone="+923001112224", email="admin@example.com",
        )

    print(f"    Created/Fetched: {patient.name} ({patient.role})")
    print(f"    Created/Fetched: {doctor_user.name} ({doctor_user.role})")
    print(f"    Created/Fetched: {admin.name} ({admin.role})")

    step("READ by ID")
    fetched = UserService.get_user_by_id(db, patient.id)
    print(f"    Fetched: {fetched.name} | email={fetched.email}")

    step("READ by email")
    by_email = UserService.get_user_by_email(db, "admin@pulseq.com")
    print(f"    Found by email: {by_email.name}")

    step("READ by phone")
    by_phone = UserService.get_user_by_phone(db, "+923001112222")
    print(f"    Found by phone: {by_phone.name}")

    step("READ ALL (paginated)")
    result = UserService.get_all_users(db, page=1, per_page=10)
    print(f"    Total users: {result['total']} | Pages: {result['total_pages']}")
    for u in result["items"]:
        print(f"      - {u['name']} ({u['role']})")

    step("READ ALL filtered by role=doctor")
    doctors = UserService.get_all_users(db, role="doctor")
    print(f"    Doctors found: {doctors['total']}")

    step("UPDATE")
    updated = UserService.update_user(db, patient.id, {
        "name": "Ali Hassan (Updated)",
        "gender": "male",
        "date_of_birth": "1995-06-15",
        "address": "123 Main St, Lahore",
    })
    print(f"    Updated: {updated.name} | gender={updated.gender}")

    return patient, doctor_user, admin


# ═══════════════════════════════════════════════════════════
#  HOSPITALS
# ═══════════════════════════════════════════════════════════

def run_hospitals(db):
    section("HOSPITALS")

    step("CREATE")
    hospital = HospitalService.create_hospital(
        db,
        name="PulseQ General Hospital",
        address="45 Medical Avenue",
        city="Lahore",
        state="Punjab",
        phone="+924235678900",
        email="info@pulseq-hospital.com",
        status="active",
        specializations=["Cardiology", "Neurology", "Orthopedics"],
        latitude=31.5204,
        longitude=74.3587,
    )
    print(f"    Created: {hospital.name} | city={hospital.city}")

    step("READ by ID")
    fetched = HospitalService.get_hospital_by_id(db, hospital.id)
    print(f"    Fetched: {fetched.name} | status={fetched.status}")

    step("READ ALL filtered by city")
    result = HospitalService.get_all_hospitals(db, city="Lahore")
    print(f"    Hospitals in Lahore: {result['total']}")

    step("UPDATE")
    updated = HospitalService.update_hospital(db, hospital.id, {
        "rating": 4.7,
        "review_count": 320,
        "status": "active",
    })
    print(f"    Updated: {updated.name} | rating={updated.rating}")

    return hospital


# ═══════════════════════════════════════════════════════════
#  DEPARTMENTS
# ═══════════════════════════════════════════════════════════

def run_departments(db, hospital):
    section("DEPARTMENTS")

    step("CREATE")
    cardiology = DepartmentService.create_department(db, "Cardiology", hospital.id)
    neurology = DepartmentService.create_department(db, "Neurology", hospital.id)
    pharmacy_dept = DepartmentService.create_department(db, "Pharmacy", hospital.id)
    print(f"    Created: {cardiology.name}, {neurology.name}, {pharmacy_dept.name}")

    step("READ by hospital")
    result = DepartmentService.get_departments_by_hospital(db, hospital.id)
    print(f"    Departments for hospital: {result['total']}")
    for d in result["items"]:
        print(f"      - {d['name']}")

    step("UPDATE")
    updated = DepartmentService.update_department(db, cardiology.id, {"name": "Cardiology & Heart Surgery"})
    print(f"    Updated dept: {updated.name}")

    return cardiology, neurology


# ═══════════════════════════════════════════════════════════
#  DOCTORS
# ═══════════════════════════════════════════════════════════

def run_doctors(db, hospital, doctor_user):
    section("DOCTORS")

    step("CREATE")
    doctor = DoctorService.create_doctor(
        db,
        name="Dr. Sarah Khan",
        specialization="Cardiology",
        hospital_id=hospital.id,
        consultation_fee=1500.0,
        session_fee=2000.0,
        start_time="09:00",
        end_time="17:00",
        status="active",
        available_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        patients_per_day=20,
        has_session=True,
        pricing_type="fixed",
        avatar_initials="SK",
        user_id=doctor_user.id,
    )
    print(f"    Created: {doctor.name} | spec={doctor.specialization} | fee={doctor.consultation_fee}")

    step("READ by ID")
    fetched = DoctorService.get_doctor_by_id(db, doctor.id)
    print(f"    Fetched: {fetched.name} | hospital={fetched.hospital_id}")

    step("READ ALL filtered by hospital + specialization")
    result = DoctorService.get_all_doctors(db, hospital_id=hospital.id, specialization="Cardiology")
    print(f"    Cardiologists at hospital: {result['total']}")

    step("UPDATE")
    updated = DoctorService.update_doctor(db, doctor.id, {
        "rating": 4.8,
        "review_count": 150,
        "patients_per_day": 25,
    })
    print(f"    Updated: {updated.name} | rating={updated.rating}")

    return doctor


# ═══════════════════════════════════════════════════════════
#  HOSPITAL SEQUENCES (MRN)
# ═══════════════════════════════════════════════════════════

def run_sequences(db, hospital):
    section("HOSPITAL SEQUENCES (MRN)")

    step("GET or CREATE sequence")
    seq = HospitalSequenceService.get_or_create(db, hospital.id)
    print(f"    Sequence for hospital: mrn_seq={seq.mrn_seq}")

    step("NEXT MRN (atomic increment)")
    mrn1 = HospitalSequenceService.next_mrn(db, hospital.id)
    mrn2 = HospitalSequenceService.next_mrn(db, hospital.id)
    mrn3 = HospitalSequenceService.next_mrn(db, hospital.id)
    print(f"    MRN #1={mrn1}, #2={mrn2}, #3={mrn3}")

    return mrn1


# ═══════════════════════════════════════════════════════════
#  TOKENS (Appointments)
# ═══════════════════════════════════════════════════════════

def run_tokens(db, patient, doctor, hospital, mrn_num):
    section("TOKENS (APPOINTMENTS)")

    step("CREATE")
    token = TokenService.create_token(
        db,
        patient_id=patient.id,
        doctor_id=doctor.id,
        hospital_id=hospital.id,
        token_number=1,
        hex_code="A1B2C3",
        display_code="PQ-001",
        appointment_date=datetime.now(timezone.utc) + timedelta(days=1),
        status="pending",
        payment_status="unpaid",
        consultation_fee=doctor.consultation_fee,
        session_fee=doctor.session_fee,
        total_fee=doctor.consultation_fee + (doctor.session_fee or 0),
        department="Cardiology",
        doctor_name=doctor.name,
        doctor_specialization=doctor.specialization,
        doctor_avatar_initials=doctor.avatar_initials,
        hospital_name=hospital.name,
        patient_name=patient.name,
        patient_phone=patient.phone,
        mrn=f"MRN-{hospital.id[:4].upper()}-{mrn_num:04d}",
        reason_for_visit="Chest pain and shortness of breath",
        patient_age=29,
        patient_gender="male",
        queue_position=1,
        total_queue=5,
        estimated_wait_time=15,
    )
    print(f"    Created token: #{token.token_number} | code={token.display_code} | status={token.status}")

    step("READ by ID")
    fetched = TokenService.get_token_by_id(db, token.id)
    print(f"    Fetched: {fetched.display_code} | patient={fetched.patient_name}")

    step("READ by hex code")
    by_hex = TokenService.get_token_by_hex(db, "A1B2C3")
    print(f"    Found by hex: {by_hex.display_code}")

    step("READ ALL filtered by patient")
    result = TokenService.get_all_tokens(db, patient_id=patient.id)
    print(f"    Tokens for patient: {result['total']}")

    step("UPDATE — confirm token")
    updated = TokenService.update_token(db, token.id, {
        "confirmation_status": "confirmed",
        "confirmed": True,
        "confirmed_at": datetime.now(timezone.utc),
        "payment_status": "paid",
    })
    print(f"    Updated: confirmed={updated.confirmed} | payment={updated.payment_status}")

    return token


# ═══════════════════════════════════════════════════════════
#  QUEUES
# ═══════════════════════════════════════════════════════════

def run_queues(db, doctor):
    section("QUEUES")

    step("CREATE / UPSERT queue for doctor")
    queue = QueueService.create_or_update_queue(
        db,
        doctor_id=doctor.id,
        current_token=1,
        waiting_patients=4,
        estimated_wait_time_minutes=20,
        people_ahead=0,
        total_queue=5,
    )
    print(f"    Queue: doctor={doctor.name} | waiting={queue.waiting_patients} | est_wait={queue.estimated_wait_time_minutes}m")

    step("READ queue by doctor")
    fetched = QueueService.get_queue_by_doctor(db, doctor.id)
    print(f"    Fetched queue: current_token={fetched.current_token}")

    step("UPDATE — advance queue")
    updated = QueueService.create_or_update_queue(
        db, doctor_id=doctor.id, current_token=2, waiting_patients=3,
    )
    print(f"    Advanced queue: current_token={updated.current_token} | waiting={updated.waiting_patients}")

    step("READ ALL queues")
    result = QueueService.get_all_queues(db)
    print(f"    Total active queues: {result['total']}")

    return queue


# ═══════════════════════════════════════════════════════════
#  PAYMENTS
# ═══════════════════════════════════════════════════════════

def run_payments(db, token):
    section("PAYMENTS")

    step("CREATE")
    payment = PaymentService.create_payment(
        db,
        token_id=token.id,
        amount=token.total_fee or 3500.0,
        method="easypaisa",
        status="completed",
        transaction_id="TXN-EP-20240001",
    )
    print(f"    Created: amount={payment.amount} | method={payment.method} | status={payment.status}")

    step("READ by ID")
    fetched = PaymentService.get_payment_by_id(db, payment.id)
    print(f"    Fetched: {fetched.id} | txn={fetched.transaction_id}")

    step("READ by token")
    by_token = PaymentService.get_payments_by_token(db, token.id)
    print(f"    Payments for token: {len(by_token)}")

    step("READ ALL filtered by method")
    result = PaymentService.get_all_payments(db, method="easypaisa")
    print(f"    Easypaisa payments: {result['total']}")

    step("UPDATE — mark refunded")
    updated = PaymentService.update_payment(db, payment.id, {"status": "refunded"})
    print(f"    Updated payment status: {updated.status}")

    return payment


# ═══════════════════════════════════════════════════════════
#  REFUNDS
# ═══════════════════════════════════════════════════════════

def run_refunds(db, patient, token, payment):
    section("REFUNDS")

    step("CREATE")
    refund = RefundService.create_refund(
        db,
        user_id=patient.id,
        token_id=token.id,
        amount=payment.amount,
        method="easypaisa",
        reason="Appointment cancelled by patient",
        status="pending",
    )
    print(f"    Created: amount={refund.amount} | reason={refund.reason}")

    step("READ by ID")
    fetched = RefundService.get_refund_by_id(db, refund.id)
    print(f"    Fetched: status={fetched.status}")

    step("READ by user")
    result = RefundService.get_refunds_by_user(db, patient.id)
    print(f"    Refunds for user: {result['total']}")

    step("UPDATE status to processed")
    updated = RefundService.update_refund_status(db, refund.id, "processed", "TXN-REF-001")
    print(f"    Updated: status={updated.status} | txn={updated.transaction_id}")

    return refund


# ═══════════════════════════════════════════════════════════
#  WALLETS
# ═══════════════════════════════════════════════════════════

def run_wallets(db, patient):
    section("WALLETS")

    step("CREATE")
    wallet = db.query(Wallet).filter(Wallet.user_id == patient.id).first()
    if not wallet:
        wallet = WalletService.create_wallet(db, user_id=patient.id, currency="PKR")
        print(f"    Created wallet: balance={wallet.balance} {wallet.currency}")
    else:
        print(f"    Wallet already exists: balance={wallet.balance} {wallet.currency}")

    step("CREDIT")
    wallet = WalletService.credit_wallet(db, patient.id, 5000.0)
    print(f"    After credit (+5000): balance={wallet.balance}")

    step("DEBIT")
    wallet = WalletService.debit_wallet(db, patient.id, 1500.0)
    print(f"    After debit (-1500): balance={wallet.balance}")

    step("READ by user")
    fetched = WalletService.get_wallet_by_user(db, patient.id)
    print(f"    Current balance: {fetched.balance} {fetched.currency}")

    step("INSUFFICIENT BALANCE test")
    try:
        WalletService.debit_wallet(db, patient.id, 99999.0)
    except ValueError as e:
        print(f"    ✅ Caught expected error: {e}")

    return wallet


# ═══════════════════════════════════════════════════════════
#  MEDICAL RECORDS
# ═══════════════════════════════════════════════════════════

def run_medical_records(db, patient):
    section("MEDICAL RECORDS")

    step("CREATE")
    record = MedicalRecordService.create_record(
        db,
        user_id=patient.id,
        filename="blood_test_report.pdf",
        file_path="/uploads/medical/blood_test_report.pdf",
        file_type="application/pdf",
        file_size=204800,
        record_type="lab_report",
        description="Complete blood count — March 2024",
    )
    print(f"    Created: {record.filename} | type={record.record_type}")

    step("CREATE second record")
    xray = MedicalRecordService.create_record(
        db,
        user_id=patient.id,
        filename="chest_xray.jpg",
        file_path="/uploads/medical/chest_xray.jpg",
        file_type="image/jpeg",
        file_size=512000,
        record_type="imaging",
        description="Chest X-Ray — frontal view",
    )
    print(f"    Created: {xray.filename} | type={xray.record_type}")

    step("READ by user (filtered by type)")
    result = MedicalRecordService.get_records_by_user(db, patient.id, record_type="lab_report")
    print(f"    Lab reports for patient: {result['total']}")

    step("READ all records for user")
    all_records = MedicalRecordService.get_records_by_user(db, patient.id)
    print(f"    Total records for patient: {all_records['total']}")

    return record


# ═══════════════════════════════════════════════════════════
#  ACTIVITY LOGS
# ═══════════════════════════════════════════════════════════

def run_activity_logs(db, patient, token, payment):
    section("ACTIVITY LOGS")

    step("LOG: login")
    ActivityLogService.log(db, patient.id, "login", "User logged in",
                           meta_data={"ip": "192.168.1.1", "device": "mobile"})

    step("LOG: appointment booked")
    ActivityLogService.log(db, patient.id, "appointment_booked",
                           f"Booked appointment token #{token.token_number}",
                           meta_data={"token_id": token.id, "doctor": token.doctor_name})

    step("LOG: payment made")
    ActivityLogService.log(db, patient.id, "payment",
                           f"Payment of {payment.amount} via {payment.method}",
                           meta_data={"payment_id": payment.id, "txn": payment.transaction_id})

    step("READ logs by user")
    result = ActivityLogService.get_logs_by_user(db, patient.id)
    print(f"    Total activity logs: {result['total']}")
    for log in result["items"]:
        print(f"      [{log['activity_type']}] {log['description']}")

    step("READ filtered by type")
    login_logs = ActivityLogService.get_logs_by_user(db, patient.id, activity_type="login")
    print(f"    Login events: {login_logs['total']}")


# ═══════════════════════════════════════════════════════════
#  SUPPORT TICKETS
# ═══════════════════════════════════════════════════════════

def run_support_tickets(db, patient):
    section("SUPPORT TICKETS")

    step("CREATE")
    ticket = SupportTicketService.create_ticket(
        db,
        user_id=patient.id,
        subject="Payment deducted but token not confirmed",
        description="I paid via Easypaisa but my appointment token still shows as pending.",
        category="billing",
        priority="high",
        status="open",
    )
    print(f"    Created ticket: [{ticket.priority}] {ticket.subject}")

    step("READ by ID")
    fetched = SupportTicketService.get_ticket_by_id(db, ticket.id)
    print(f"    Fetched: status={fetched.status} | category={fetched.category}")

    step("READ ALL filtered by priority=high")
    result = SupportTicketService.get_all_tickets(db, priority="high")
    print(f"    High priority tickets: {result['total']}")

    step("READ ALL open tickets for user")
    user_tickets = SupportTicketService.get_all_tickets(db, user_id=patient.id, status="open")
    print(f"    Open tickets for user: {user_tickets['total']}")

    step("UPDATE — resolve ticket")
    resolved = SupportTicketService.update_ticket(db, ticket.id, {"status": "resolved"})
    print(f"    Updated: status={resolved.status}")

    return ticket


# ═══════════════════════════════════════════════════════════
#  QUICK ACTIONS
# ═══════════════════════════════════════════════════════════

def run_quick_actions(db, patient):
    section("QUICK ACTIONS")

    step("CREATE")
    actions_data = [
        ("book_appointment", "Book Appointment", "Schedule a new doctor visit", "calendar", "/book"),
        ("view_records", "Medical Records", "View your health documents", "folder", "/records"),
        ("wallet_topup", "Top Up Wallet", "Add funds to your wallet", "wallet", "/wallet"),
    ]
    created_actions = []
    for action_type, title, desc, icon, route in actions_data:
        action = QuickActionService.create_action(
            db, user_id=patient.id, action_type=action_type,
            title=title, description=desc, icon=icon, route=route,
        )
        created_actions.append(action)
        print(f"    Created: [{action.action_type}] {action.title}")

    step("READ all (enabled only)")
    actions = QuickActionService.get_actions_by_user(db, patient.id, enabled_only=True)
    print(f"    Enabled actions for user: {len(actions)}")

    step("UPDATE — disable one")
    disabled = QuickActionService.update_action(db, created_actions[2].id, {"is_enabled": False})
    print(f"    Disabled: {disabled.title} | is_enabled={disabled.is_enabled}")

    step("READ enabled only (should be 2 now)")
    enabled = QuickActionService.get_actions_by_user(db, patient.id, enabled_only=True)
    print(f"    Enabled actions after disable: {len(enabled)}")


# ═══════════════════════════════════════════════════════════
#  IDEMPOTENCY RECORDS
# ═══════════════════════════════════════════════════════════

def run_idempotency(db, patient, token):
    section("IDEMPOTENCY RECORDS")

    idempotency_key = f"book-appt-{patient.id}-{token.id}"

    step("CHECK — does key exist?")
    exists = IdempotencyService.exists(db, idempotency_key)
    print(f"    Key exists before create: {exists}")

    step("CREATE record")
    record = IdempotencyService.create(
        db, user_id=patient.id, key=idempotency_key,
        action="book_appointment", token_id=token.id,
    )
    print(f"    Created idempotency record: key={record.key}")

    step("CHECK — key should now exist")
    exists = IdempotencyService.exists(db, idempotency_key)
    print(f"    Key exists after create: {exists}")

    step("GET by key")
    fetched = IdempotencyService.get_by_key(db, idempotency_key)
    print(f"    Fetched: action={fetched.action} | token_id={fetched.token_id}")

    step("DELETE")
    deleted = IdempotencyService.delete(db, idempotency_key)
    print(f"    Deleted: {deleted}")
    print(f"    Exists after delete: {IdempotencyService.exists(db, idempotency_key)}")


# ═══════════════════════════════════════════════════════════
#  PHARMACY MEDICINES
# ═══════════════════════════════════════════════════════════

def run_pharmacy_medicines(db, hospital):
    section("PHARMACY MEDICINES")

    step("CREATE")
    paracetamol = PharmacyMedicineService.create_medicine(
        db,
        product_id=1001,
        batch_no="BATCH-2024-001",
        name="Paracetamol 500mg",
        generic_name="Paracetamol",
        type="tablet",
        distributor="PharmaCo Ltd",
        purchase_price=50.0,
        selling_price=80.0,
        quantity=500,
        stock_unit="tablets",
        category="analgesics",
        sub_category="OTC",
        hospital_id=hospital.id,
        expiration_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    amoxicillin = PharmacyMedicineService.create_medicine(
        db,
        product_id=1002,
        batch_no="BATCH-2024-002",
        name="Amoxicillin 250mg",
        generic_name="Amoxicillin",
        type="capsule",
        distributor="MediSupply Co",
        purchase_price=120.0,
        selling_price=200.0,
        quantity=200,
        stock_unit="capsules",
        category="antibiotics",
        sub_category="prescription",
        hospital_id=hospital.id,
    )
    print(f"    Created: {paracetamol.name} | qty={paracetamol.quantity} | price={paracetamol.selling_price}")
    print(f"    Created: {amoxicillin.name} | qty={amoxicillin.quantity} | price={amoxicillin.selling_price}")

    step("READ by ID")
    fetched = PharmacyMedicineService.get_medicine_by_id(db, paracetamol.id)
    print(f"    Fetched: {fetched.name} | batch={fetched.batch_no}")

    step("READ ALL filtered by hospital + category")
    result = PharmacyMedicineService.get_all_medicines(db, hospital_id=hospital.id, category="antibiotics")
    print(f"    Antibiotics in stock: {result['total']}")

    step("READ ALL (no deleted filter)")
    all_meds = PharmacyMedicineService.get_all_medicines(db, hospital_id=hospital.id)
    print(f"    Total medicines (active): {all_meds['total']}")

    step("UPDATE — restock")
    updated = PharmacyMedicineService.update_medicine(db, paracetamol.id, {
        "quantity": 750,
        "selling_price": 85.0,
    })
    print(f"    Updated: {updated.name} | new qty={updated.quantity} | new price={updated.selling_price}")

    step("SOFT DELETE")
    deleted = PharmacyMedicineService.soft_delete_medicine(db, amoxicillin.id)
    print(f"    Soft-deleted Amoxicillin: {deleted}")

    step("Verify soft-deleted is hidden from normal queries")
    active_meds = PharmacyMedicineService.get_all_medicines(db, hospital_id=hospital.id)
    print(f"    Active medicines (should exclude deleted): {active_meds['total']}")

    step("Verify soft-deleted appears with include_deleted=True")
    all_including_deleted = PharmacyMedicineService.get_all_medicines(
        db, hospital_id=hospital.id, include_deleted=True
    )
    print(f"    All medicines including deleted: {all_including_deleted['total']}")

    return paracetamol


# ═══════════════════════════════════════════════════════════
#  PHARMACY SALES
# ═══════════════════════════════════════════════════════════

def run_pharmacy_sales(db, patient, doctor, doctor_user, hospital, medicine):
    section("PHARMACY SALES")

    step("CREATE")
    sale = PharmacySaleService.create_sale(
        db,
        hospital_id=hospital.id,
        patient_id=patient.id,
        doctor_id=doctor.id,
        medicine_id=medicine.product_id,
        medicine_name=medicine.name,
        quantity=10,
        unit_price=medicine.selling_price,
        total_price=medicine.selling_price * 10,
        total_amount=medicine.selling_price * 10,
        items=[{
            "medicine_id": medicine.product_id,
            "name": medicine.name,
            "qty": 10,
            "unit_price": medicine.selling_price,
            "total": medicine.selling_price * 10,
        }],
        payment_status="paid",
        performed_by=str(doctor_user.id),  # ✅ use doctor's real ID from users table
    )
    print(f"    Sale: {sale.medicine_name} x{sale.quantity} | total={sale.total_amount} | status={sale.payment_status}")

    step("READ by ID")
    fetched = PharmacySaleService.get_sale_by_id(db, sale.id)
    print(f"    Fetched sale: {fetched.id} | amount={fetched.total_amount}")

    step("READ ALL filtered by hospital + payment_status")
    result = PharmacySaleService.get_all_sales(db, hospital_id=hospital.id, payment_status="paid")
    print(f"    Paid sales for hospital: {result['total']}")

    step("READ ALL for patient")
    patient_sales = PharmacySaleService.get_all_sales(db, patient_id=patient.id)
    print(f"    Sales for patient: {patient_sales['total']}")

    step("UPDATE payment status")
    updated = PharmacySaleService.update_sale(db, sale.id, {"payment_status": "completed"})
    print(f"    Updated sale: payment_status={updated.payment_status}")

    return sale

# ═══════════════════════════════════════════════════════════
#  CLEANUP (Delete test data)
# ═══════════════════════════════════════════════════════════

def run_cleanup(db, patient, doctor_user, admin, hospital, cardiology, neurology,
                doctor, token, payment, refund, ticket, record, sale, medicine):
    section("CLEANUP — Delete test data")

    user_ids = [patient.id, doctor_user.id, admin.id]

    # ── Step 1: pharmacy_sales (references doctors, hospitals, users)
    all_sales = db.query(PharmacySale).filter(
        or_(
            PharmacySale.patient_id.in_(user_ids),
            PharmacySale.performed_by.in_([str(u) for u in user_ids])
        )
    ).all()
    for s in all_sales:
        db.delete(s)
    db.commit()
    print("    🗑️ Deleted pharmacy sales")

    # ── Step 2: pharmacy_medicines (references hospitals)
    PharmacyMedicineService.hard_delete_medicine(db, medicine.id)
    print("    🗑️ Deleted medicine")

    # ── Step 3: support_tickets (references users)
    all_tickets = db.query(SupportTicket).filter(SupportTicket.user_id.in_(user_ids)).all()
    for t in all_tickets:
        db.delete(t)
    db.commit()
    print("    🗑️ Deleted support tickets")

    # ── Step 4: medical_records (references users)
    all_records = db.query(MedicalRecord).filter(MedicalRecord.user_id.in_(user_ids)).all()
    for r in all_records:
        db.delete(r)
    db.commit()
    print("    🗑️ Deleted medical records")

    # ── Step 5: activity_logs (references users)
    all_logs = db.query(ActivityLog).filter(ActivityLog.user_id.in_(user_ids)).all()
    for log in all_logs:
        db.delete(log)
    db.commit()
    print("    🗑️ Deleted activity logs")

    # ── Step 6: quick_actions (references users)
    all_qas = db.query(QuickAction).filter(QuickAction.user_id.in_(user_ids)).all()
    for qa in all_qas:
        db.delete(qa)
    db.commit()
    print("    🗑️ Deleted quick actions")

    # ── Step 7: wallets (references users)
    all_wallets = db.query(Wallet).filter(Wallet.user_id.in_(user_ids)).all()
    for w in all_wallets:
        db.delete(w)
    db.commit()
    print("    🗑️ Deleted wallets")

    # ── Step 8: refunds (references tokens + users) — BEFORE payments and tokens
    all_refunds = db.query(Refund).filter(
        or_(
            Refund.user_id.in_(user_ids),
            Refund.token_id.in_(
                db.query(Token.id).filter(Token.patient_id.in_(user_ids)).scalar_subquery()
            )
        )
    ).all()
    for r in all_refunds:
        db.delete(r)
    db.commit()
    print("    🗑️ Deleted refunds")


    # ── Step 9: payments (references tokens) — delete ALL payments for ALL user tokens
    # First get all token IDs for these users
    all_user_tokens = db.query(Token).filter(Token.patient_id.in_(user_ids)).all()
    all_token_ids = [t.id for t in all_user_tokens]

    # Delete ALL payments linked to ANY of those tokens
    if all_token_ids:
        all_payments = db.query(Payment).filter(Payment.token_id.in_(all_token_ids)).all()
        for p in all_payments:
            db.delete(p)
        db.commit()
    print("    🗑️ Deleted payments")

    # ── Step 10: queues (references doctors) — BEFORE doctors
    all_queues = db.query(Queue).filter(Queue.doctor_id == doctor.id).all()
    for q in all_queues:
        db.delete(q)
    db.commit()
    print("    🗑️ Deleted queues")

    #── Step 11: tokens — AFTER all payments and refunds deleted
    if all_token_ids:
        all_tokens = db.query(Token).filter(Token.id.in_(all_token_ids)).all()
        for t in all_tokens:
            db.delete(t)
        db.commit()
    print("    🗑️ Deleted tokens")

    # ── Step 12: doctors — delete by user_id to catch ALL doctors linked to these users
    all_doctors = db.query(Doctor).filter(Doctor.user_id.in_(user_ids)).all()
    for d in all_doctors:
        # First delete any remaining queues for each doctor
        remaining_queues = db.query(Queue).filter(Queue.doctor_id == d.id).all()
        for q in remaining_queues:
            db.delete(q)
    db.commit()

    # Now delete the doctors
    all_doctors = db.query(Doctor).filter(Doctor.user_id.in_(user_ids)).all()
    for d in all_doctors:
        db.delete(d)
    db.commit()
    print("    🗑️ Deleted doctors")

    # ── Step 13: departments (references hospitals) — BEFORE hospitals
    all_departments = db.query(Department).filter(Department.hospital_id == hospital.id).all()
    for dept in all_departments:
        db.delete(dept)
    db.commit()
    print("    🗑️ Deleted departments")

    # ── Step 14: hospital_sequences (references hospitals) — BEFORE hospitals
    all_sequences = db.query(HospitalSequence).filter(HospitalSequence.hospital_id == hospital.id).all()
    for hs in all_sequences:
        db.delete(hs)
    db.commit()
    print("    🗑️ Deleted hospital sequences")

    # ── Step 15: hospitals — AFTER all child tables cleared
    HospitalService.delete_hospital(db, hospital.id)
    print("    🗑️ Deleted hospital")

    # ── Step 16: users — LAST (after all referencing tables cleared)
    for user_id in user_ids:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            db.delete(user)
    db.commit()
    print("    🗑️ Deleted users")

    print("    ✅ All test records deleted")

# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("\n" + "█" * 60)
    print("  PulseQ DB Automation — Full CRUD Test Suite")
    print("█" * 60)

    with get_db() as db:
        # Core entities
        patient, doctor_user, admin = run_users(db)
        hospital = run_hospitals(db)
        cardiology, neurology = run_departments(db, hospital)
        doctor = run_doctors(db, hospital, doctor_user)

        # Sequences + Appointments
        mrn_num = run_sequences(db, hospital)
        token = run_tokens(db, patient, doctor, hospital, mrn_num)

        # Queue
        run_queues(db, doctor)

        # Financial
        payment = run_payments(db, token)
        refund = run_refunds(db, patient, token, payment)
        run_wallets(db, patient)

        # Patient data
        record = run_medical_records(db, patient)
        run_activity_logs(db, patient, token, payment)
        ticket = run_support_tickets(db, patient)
        run_quick_actions(db, patient)
        run_idempotency(db, patient, token)

        # Pharmacy
        medicine = run_pharmacy_medicines(db, hospital)
        sale = run_pharmacy_sales(db, patient, doctor, doctor_user, hospital, medicine)

        # Cleanup
        run_cleanup(db, patient, doctor_user, admin, hospital, cardiology, neurology,
                    doctor, token, payment, refund, ticket, record, sale, medicine)

    print("\n" + "█" * 60)
    print("  ✅ All CRUD operations completed successfully!")
    print("█" * 60 + "\n")


if __name__ == "__main__":
    init_db()
    main()