import os

# Environment separation for web/mobile/ML integrations
ENV = os.getenv("ENV", "development").lower()  # development | staging | production
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "").strip()
MOBILE_BASE_URL = os.getenv("MOBILE_BASE_URL", "").strip()
ML_BASE_URL = os.getenv("ML_BASE_URL", "").strip()

# Optional comma-separated list of extra CORS origins for web/mobile
EXTRA_CORS_ORIGINS = [o.strip() for o in os.getenv("EXTRA_CORS_ORIGINS", "").split(",") if o.strip()]
