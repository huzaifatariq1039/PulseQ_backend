from fastapi import FastAPI, HTTPException, status, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import asyncio
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import PROJECT_NAME, DEBUG
from app.database import initialize_firebase
from app.config_env import WEB_BASE_URL, MOBILE_BASE_URL, EXTRA_CORS_ORIGINS, TRUSTED_HOSTS
from app.utils.responses import fail
from app.exceptions import PulseQException
from app.logger import get_logger
from app.services.ai_engine import ai_engine
from app.services.queue_management_service import QueueManagementService
from app.config import QUEUE_AUTOSKIP_INTERVAL_SECONDS
from app.services.app_scheduler import start_scheduler, shutdown_scheduler
from app.services.sync_service import sync_pos_to_postgres
from app.services.redis_service import init_redis, close_redis
from app.middleware.performance import PerformanceMiddleware
 
from app.routes import auth, hospitals, doctors, tokens, dashboard
from app.routes import realtime, portal
from app.routes import consultation
from app.routes import pos
from app.routes import tokens_listing
from app.routes import tokens_idempotent
from app.routes import health
from app.routes import ml
from app.routes import ai
from app.routes import patient
from app.routes import profile
from app.routes import payments
from app.routes import queue
from app.routes import reception
from app.routes import ratings
from app.routes.whatsapp_webhook import router as whatsapp_webhook_router
from app.routes.pharmacy import public_router as pharmacy_public_router
from app.routes.pharmacy import router as pharmacy_portal_router
from app.routes.token_alias import token_alias_router
from app.routes.auth_otp import router as otp_router
 
# FIX 2: Compute cors_origins BEFORE lifespan so the startup log doesn't crash
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_default_origins = [o for o in [WEB_BASE_URL, MOBILE_BASE_URL, "https://pulseq.health",               # Main Landing Page
    "https://www.pulseq.health",
    "https://patient.pulseq.health",       # Patient Portal
    "https://doctor.pulseq.health",        # Doctor Portal
    "https://reception.pulseq.health",     # Reception Portal
    "https://pharmacy.pulseq.health",      # Pharmacy Portal
    "https://admin.pulseq.health",         # Admin Portal
    "https://demo.pulseq.health",
    "http://patient.localhost:4200/",
    "http://doctor.localhost:4200/",
    "http://reception.localhost:4200/",
    "http://pharmacy.localhost:4200/",
    "http://admin.localhost:4200/",
    "http://demo.localhost:4200/"
] if o]
_extra = EXTRA_CORS_ORIGINS or []
if not (_allowed_origins or _default_origins or _extra):
    _allowed_origins = ["*"]
cors_origins = _allowed_origins or (_default_origins + _extra)

# Initialize logger for main module
logger = get_logger(__name__)
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting PulseQ Backend...")
    logger.info(f"📁 Working Directory: {os.getcwd()}")
    logger.info(f"🔧 Debug Mode: {DEBUG}")
    logger.info(f"🌐 Allowed Origins: {cors_origins}")

    autoskip_task: asyncio.Task | None = None
    pos_sync_task: asyncio.Task | None = None

    async def _autoskip_worker():
        interval = max(15, int(QUEUE_AUTOSKIP_INTERVAL_SECONDS or 60))
        while True:
            try:
                await QueueManagementService.autoskip_cycle()
            except Exception:
                pass
            await asyncio.sleep(interval)

    try:
        initialize_firebase()
        logger.info("✅ Database connection initialized successfully!")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization warning: {e}")
        logger.warning("⚠️ Continuing without database - some features may not work")

    logger.info("✨ Backend started successfully!")

    try:
        autoskip_task = asyncio.create_task(_autoskip_worker())
        logger.info(f"Auto-skip worker started (interval={int(QUEUE_AUTOSKIP_INTERVAL_SECONDS)}s)")
        pos_sync_task = asyncio.create_task(sync_pos_to_postgres())
        logger.info("Go POS background sync worker started (5min interval)")
    except Exception as e:
        logger.error(f"Background worker failed to start: {e}")

    try:
        start_scheduler()
        logger.info("APScheduler started")
    except Exception as e:
        logger.error(f"APScheduler failed to start: {e}")

    try:
        ai_engine.load()
        logger.info("AI Engine model loaded successfully!")
    except Exception as e:
        logger.error(f"AI Engine failed to load: {e}")

    try:
        await init_redis()
        logger.info("🔴 Redis/Upstash initialized for WebSocket Pub/Sub")
    except Exception as e:
        logger.warning(f"Redis initialization warning: {e}")
        logger.warning("⚠️ WebSocket broadcast across instances will be unavailable")

    try:
        start_scheduler()
        logger.info("APScheduler started (used by legacy services only)")
    except Exception as e:
        logger.error(f"APScheduler failed to start: {e}")

    yield  # App is now ready to serve requests

    # Shutdown sequence
    logger.info("🛑 Shutting down PulseQ Backend...")
    try:
        if autoskip_task:
            autoskip_task.cancel()
    except Exception as e:
        logger.error(f"Error cancelling autoskip task: {e}")

    try:
        if pos_sync_task:
            pos_sync_task.cancel()
    except Exception as e:
        logger.error(f"Error cancelling POS sync task: {e}")

    try:
        shutdown_scheduler()
        logger.info("APScheduler shut down")
    except Exception as e:
        logger.error(f"Error shutting down APScheduler: {e}")

    try:
        await close_redis()
        logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")

    logger.info("✅ Backend shutdown complete")
 
 
# FIX 1: redirect_slashes=False prevents 301 redirects that break CORS preflight
app = FastAPI(
    title=PROJECT_NAME,
    description="Backend API for PulseQ mobile application - Healthcare appointment system",
    version="1.0.0",
    debug=DEBUG,
    lifespan=lifespan,
    redirect_slashes=False,  # FIX 1: Prevents CORS preflight redirect failure
)
 
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(PerformanceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apply TrustedHostMiddleware when configured via environment variable
# TRUSTED_HOSTS should be a comma-separated list of allowed hosts (e.g. example.com,api.example.com)
if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
    logger.info(f"Trusted hosts configured: {TRUSTED_HOSTS}")
else:
    logger.info("TrustedHostMiddleware not configured (TRUSTED_HOSTS empty). Skipping.")
 
# 1. Core & System
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Core Authentication"])
app.include_router(health.router, prefix="/api/v1/system", tags=["System Health"])
app.include_router(whatsapp_webhook_router, prefix="/api/v1/webhooks", tags=["Integrations & Webhooks"])
 
# 2. Public Discovery (Patient/Guest)
app.include_router(hospitals.router, prefix="/api/v1/public/hospitals", tags=["Public Discovery"])
app.include_router(doctors.public_router, prefix="/api/v1/public/doctors", tags=["Public Discovery"])
app.include_router(pharmacy_public_router, prefix="/api/v1/public/pharmacy", tags=["Public Discovery"])
 
# 2b. Staff Doctor Management (Admin/Receptionist)
app.include_router(doctors.router, prefix="/api/v1/staff/doctors", tags=["Staff Portal - Doctor Management"])
app.include_router(doctors.router, prefix="/api/v1/doctors", tags=["Doctor Management (Legacy Alias)"])
 
# 3. Patient Services
app.include_router(dashboard.router, prefix="/api/v1/patient/dashboard", tags=["Patient Portal"])
app.include_router(profile.router, prefix="/api/v1/patient/profile", tags=["Patient Portal"])
app.include_router(patient.router, prefix="/api/v1/patient/actions", tags=["Patient Portal"])
app.include_router(tokens.router, prefix="/api/v1/patient/tokens", tags=["Token Management"])
app.include_router(tokens_listing.router, prefix="/api/v1/patient/tokens/list", tags=["Token Management"])
app.include_router(tokens_idempotent.router, prefix="/api/v1/patient/tokens/secure", tags=["Token Management"])
app.include_router(payments.router, prefix="/api/v1/patient/payments", tags=["Payment Services"])
app.include_router(queue.router, prefix="/api/v1/patient/queue", tags=["Queue Services"])
app.include_router(token_alias_router, prefix="/api/v1/patients", tags=["Token Management (Frontend Alias)"])
app.include_router(ratings.router, prefix="/api/v1/ratings")
app.include_router(otp_router, prefix="/api/v1/auth", tags=["Auth"])

# 4. Staff & Provider Services
app.include_router(consultation.router, prefix="/api/v1/staff/consultation", tags=["Staff Portal"])
app.include_router(realtime.router, prefix="/api/v1/staff/realtime", tags=["Staff Portal"])
app.include_router(portal.router, prefix="/api/v1/staff/portal", tags=["Staff Portal"])
app.include_router(portal.router, prefix="/api/v1/portal", tags=["Staff Portal (Alias)"])
app.include_router(pharmacy_portal_router, prefix="/api/v1/staff/pharmacy", tags=["Staff Portal"])
 
# 5. Intelligence & AI
app.include_router(ml.router, prefix="/api/v1/ai/ml", tags=["Intelligence Services"])
app.include_router(ai.router, prefix="/api/v1/ai/core", tags=["Intelligence Services"])
 
# 6. External Integrations
app.include_router(pos.router, prefix="/api/v1/external/pos", tags=["External Integrations"])
app.include_router(reception.router, prefix="/api/v1/external/reception", tags=["External Integrations"])

@app.get("/")
async def root():
    return {
        "message": "PulseQ backend running successfully",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }
 
 
@app.head("/")
async def health_head():
    return Response(status_code=200)
 
 
@app.on_event("startup")
async def startup_event():
    try:
        ai_engine.load()
        logger.info("AI Engine model loaded successfully (startup event)")
    except Exception as e:
        logger.error(f"AI Engine failed to load on startup event: {e}") 
 
@app.get("/ping")
async def health_check():
    return {"status": "healthy", "message": "pong"}
 
 
@app.get("/secure")
async def secure_endpoint():
    return {"message": "This is a protected endpoint", "status": "authenticated"}
 
 
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled exceptions."""
    return fail(
        message="Internal server error",
        error_code="INTERNAL_SERVER_ERROR",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
 
 
@app.exception_handler(PulseQException)
async def pulseq_exception_handler(request, exc: PulseQException):
    """Handler for PulseQException with error_code support.
    
    PulseQException instances already contain an error_code field,
    so we can pass it directly to the fail() function.
    """
    return fail(
        message=exc.detail,
        error_code=exc.error_code,
        status_code=exc.status_code,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handler for HTTP exceptions (401, 403, 404, etc.)."""
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    
    # Map HTTP status codes to error codes
    error_code_map = {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_409_CONFLICT: "CONFLICT",
    }
    error_code = error_code_map.get(exc.status_code, "BAD_REQUEST")
    
    return fail(
        message=message,
        error_code=error_code,
        status_code=exc.status_code,
        data={"detail": exc.detail} if exc.detail else None
    )
 
 
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Handler for request validation errors (malformed JSON, type mismatches, etc.)."""
    try:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join([str(x) for x in first.get("loc", [])]) if first else "request"
        msg = first.get("msg", "Validation error") if first else "Validation error"
        message = f"{loc}: {msg}" if loc else msg
    except Exception:
        message = "Validation error"
    
    return fail(
        message=message,
        error_code="VALIDATION_ERROR",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        data={"errors": exc.errors()}
    )
 
 
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handler for 404 Not Found errors."""
    return fail(
        message="Endpoint not found",
        error_code="NOT_FOUND",
        status_code=status.HTTP_404_NOT_FOUND
    )