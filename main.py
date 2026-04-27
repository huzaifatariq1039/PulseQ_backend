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
 
from app.config import PROJECT_NAME, DEBUG
from app.database import initialize_firebase, init_db
from app.config_env import WEB_BASE_URL, MOBILE_BASE_URL, EXTRA_CORS_ORIGINS
from app.utils.responses import fail
from app.services.ai_engine import ai_engine
from app.services.queue_management_service import QueueManagementService
from app.config import QUEUE_AUTOSKIP_INTERVAL_SECONDS
from app.services.app_scheduler import start_scheduler, shutdown_scheduler
from app.services.sync_service import sync_pos_to_postgres
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
from app.routes.whatsapp_webhook import router as whatsapp_webhook_router
from app.routes.pharmacy import public_router as pharmacy_public_router
from app.routes.pharmacy import router as pharmacy_portal_router
from app.routes.token_alias import token_alias_router
 
# FIX 2: Compute cors_origins BEFORE lifespan so the startup log doesn't crash
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
_default_origins = [o for o in [WEB_BASE_URL, MOBILE_BASE_URL, "http://localhost:4200", "https://pulseq-3l03vs19z-aimens-projects-ff0f0a5e.vercel.app/"] if o]
_extra = EXTRA_CORS_ORIGINS or []
if not (_allowed_origins or _default_origins or _extra):
    _allowed_origins = ["*"]
cors_origins = _allowed_origins or (_default_origins + _extra)
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting PulseQ Backend...")
    print(f"📁 Working Directory: {os.getcwd()}")
    print(f"🔧 Debug Mode: {DEBUG}")
    print(f"🌐 Allowed Origins: {cors_origins}")
 
    autoskip_task: asyncio.Task | None = None
    pos_sync_task: asyncio.Task | None = None
 
    try:
        initialize_firebase()
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
        print("⚠️ Continuing without database - some features may not work")
 
    print("✨ Backend started successfully!")
 
    async def _autoskip_worker():
        interval = max(15, int(QUEUE_AUTOSKIP_INTERVAL_SECONDS or 60))
        while True:
            try:
                await QueueManagementService.autoskip_cycle()
            except Exception:
                pass
            await asyncio.sleep(interval)
 
    try:
        autoskip_task = asyncio.create_task(_autoskip_worker())
        print(f"Auto-skip worker started (interval={int(QUEUE_AUTOSKIP_INTERVAL_SECONDS)}s)")
        pos_sync_task = asyncio.create_task(sync_pos_to_postgres())
        print("Go POS background sync worker started (5min interval)")
    except Exception as e:
        print(f"Background worker failed to start: {e}")
 
    try:
        start_scheduler()
        print("APScheduler started")
    except Exception as e:
        print(f"APScheduler failed to start: {e}")
 
    try:
        ai_engine.load()
        print("AI Engine model loaded successfully!")
    except Exception as e:
        print(f"AI Engine failed to load: {e}")
 
    yield
 
    print("Shutting down Smart Token Backend...")
    try:
        if autoskip_task:
            autoskip_task.cancel()
        if pos_sync_task:
            pos_sync_task.cancel()
    except Exception:
        pass
 
    try:
        shutdown_scheduler()
    except Exception:
        pass
 
 
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
        print("AI Engine model loaded successfully (startup event)")
    except Exception as e:
        print(f"AI Engine failed to load on startup event: {e}")
 
 
@app.get("/ping")
async def health_check():
    return {"status": "healthy", "message": "pong"}
 
 
@app.get("/secure")
async def secure_endpoint():
    return {"message": "This is a protected endpoint", "status": "authenticated"}
 
 
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return fail(message="Internal server error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
 
 
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return fail(message=message, status_code=exc.status_code, data={"detail": exc.detail})
 
 
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    try:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join([str(x) for x in first.get("loc", [])]) if first else "request"
        msg = first.get("msg", "Validation error") if first else "Validation error"
        message = f"{loc}: {msg}" if loc else msg
    except Exception:
        message = "Validation error"
    return fail(message=message, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, data={"errors": exc.errors()})
 
 
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return fail(message="Endpoint not found", status_code=status.HTTP_404_NOT_FOUND)
