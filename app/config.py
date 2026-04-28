import os
from dotenv import load_dotenv
from pathlib import Path

# Base directory - project root (where .env file is located)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file in project root
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8", override=True)

# Project Settings
PROJECT_NAME = os.getenv("PROJECT_NAME", "PulseQBackend")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Payments: per-token fee (not doctor consultation fee)
TOKEN_FEE = float(os.getenv("TOKEN_FEE", "50"))

# Testing Mode (for development without Firebase)
TESTING_MODE = os.getenv("TESTING_MODE", "False").lower() == "true"

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Default fallback for development
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pulseq"

# Firebase Configuration (deprecated - keeping for migration)
FIREBASE_SERVICE_ACCOUNT_KEY = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_KEY", 
    "smart-token-247bb-firebase-adminsdk-fbsvc-b793f6e6af.json"
)

#JWT Key
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    # Do not raise RuntimeError at top-level to prevent app crash during initialization on Render.
    # We will log a warning instead.
    print("⚠️ WARNING: SECRET_KEY is not configured! Please set SECRET_KEY or JWT_SECRET_KEY in your environment variables.")
    # For safety, we set a temporary dummy key so the app can start (will fail later on JWT verification)
    SECRET_KEY = "temporary-development-key-replace-me-immediately"
    
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# Firestore Collections
COLLECTIONS = {
    "USERS": "users",
    "HOSPITALS": "hospitals", 
    "DOCTORS": "doctors",
    "TOKENS": "tokens",
    "PAYMENTS": "payments",
    "DEPARTMENTS": "departments",
    "APPOINTMENTS": "appointments",
    "ACTIVITIES": "activities",
    "QUICK_ACTIONS": "quick_actions",
    "COUNTERS": "counters",
    "CAPACITY": "capacity",
    "IDEMPOTENCY": "idempotency",
    "PHARMACY_ITEMS": "pharmacy_items",
    "PHARMACY_STOCK_LOGS": "pharmacy_stock_logs",
    "PHARMACY_SALES": "pharmacy_sales",
    "PHARMACY_MEDICINES": "pharmacy_medicines",
    "PHARMACY_PRESCRIPTIONS": "pharmacy_prescriptions",
    "QUEUES": "queues",
} 

AVG_CONSULTATION_TIME_MINUTES = int(os.getenv("AVG_CONSULTATION_TIME_MINUTES", "5"))
QUEUE_GRACE_TIME_MINUTES = int(os.getenv("QUEUE_GRACE_TIME_MINUTES", "3"))

# Smart notifications
QUEUE_SMART_NOTIFY_POSITION_THRESHOLD = int(os.getenv("QUEUE_SMART_NOTIFY_POSITION_THRESHOLD", "4"))
QUEUE_SMART_NOTIFY_WAIT_THRESHOLD_MINUTES = int(os.getenv("QUEUE_SMART_NOTIFY_WAIT_THRESHOLD_MINUTES", "15"))

# Background auto-skip worker
QUEUE_AUTOSKIP_INTERVAL_SECONDS = int(os.getenv("QUEUE_AUTOSKIP_INTERVAL_SECONDS", "60"))

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
TWILIO_TEMPLATE_SID = os.getenv("TWILIO_TEMPLATE_SID") # New: For WhatsApp buttons
TWILIO_CALL_ALERT_SID = os.getenv("TWILIO_CALL_ALERT_SID") # New: For "patient_call_alert"
TWILIO_FINAL_ALERT_SID = os.getenv("TWILIO_FINAL_ALERT_SID") # New: For "final_alert"
TWILIO_DOCTOR_CHANGE_SID = os.getenv("TWILIO_DOCTOR_CHANGE_SID") # New: For "appointment_doctor_change"
TWILIO_CANCELLED_SID = os.getenv("TWILIO_CANCELLED_SID") # New: For "cancelled" template
TWILIO_THANKYOU_SID = os.getenv("TWILIO_THANKYOU_SID", "HX07f9a8376cbb2c26e39703037696df36") # New: For "template" (thankyou) template
TWILIO_SKIPPED_SID = os.getenv("TWILIO_SKIPPED_SID") # New: For "skipped" template
TWILIO_REMINDER_CONFIRM_SID = os.getenv("TWILIO_REMINDER_CONFIRM_SID") # New: For "reminder_for_confirmation" template
TWILIO_QUEUE_UPDATE_SID = os.getenv("TWILIO_QUEUE_UPDATE_SID") # New: For "queue_update" template after YES
TWILIO_TOKEN_NUMBER_SID = os.getenv("TWILIO_TOKEN_NUMBER_SID")

# POS System Integration
POS_SYSTEM_BASE_URL = os.getenv("POS_SYSTEM_BASE_URL", "http://localhost:5000")
POS_SYSTEM_API_KEY = os.getenv("POS_SYSTEM_API_KEY", "")
POS_WEBHOOK_SECRET = os.getenv("POS_WEBHOOK_SECRET", "")