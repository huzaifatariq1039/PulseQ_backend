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
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/pulseq"
)

# Firebase Configuration (deprecated - keeping for migration)
FIREBASE_SERVICE_ACCOUNT_KEY = os.getenv(
    "FIREBASE_SERVICE_ACCOUNT_KEY", 
    "smart-token-247bb-firebase-adminsdk-fbsvc-b793f6e6af.json"
)

#JWT Key
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not configured! Please set SECRET_KEY or JWT_SECRET_KEY in your .env file"
    )
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