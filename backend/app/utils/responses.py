from typing import Any, Dict, Optional, Literal
from fastapi.responses import JSONResponse
from fastapi import status
from datetime import date, datetime
import re
from pydantic import BaseModel

# Standardized error codes for API responses
ERROR_CODES = {
    # Authentication & Authorization (40x)
    "UNAUTHORIZED": "UNAUTHORIZED",                 # 401
    "FORBIDDEN": "FORBIDDEN",                       # 403
    "INVALID_CREDENTIALS": "INVALID_CREDENTIALS",   # 401
    "TOKEN_EXPIRED": "TOKEN_EXPIRED",               # 401
    "INSUFFICIENT_PERMISSIONS": "INSUFFICIENT_PERMISSIONS",  # 403
    
    # Validation (422)
    "VALIDATION_ERROR": "VALIDATION_ERROR",         # 422
    "INVALID_INPUT": "INVALID_INPUT",               # 422
    "MISSING_REQUIRED_FIELD": "MISSING_REQUIRED_FIELD",  # 422
    "INVALID_FORMAT": "INVALID_FORMAT",             # 422
    "INVALID_EMAIL": "INVALID_EMAIL",               # 422
    "INVALID_PHONE": "INVALID_PHONE",               # 422
    
    # Resource Errors (400, 404)
    "NOT_FOUND": "NOT_FOUND",                       # 404
    "BAD_REQUEST": "BAD_REQUEST",                   # 400
    "RESOURCE_NOT_FOUND": "RESOURCE_NOT_FOUND",    # 404
    "ALREADY_EXISTS": "ALREADY_EXISTS",             # 400
    "CONFLICT": "CONFLICT",                         # 409
    
    # Server Errors (500)
    "INTERNAL_SERVER_ERROR": "INTERNAL_SERVER_ERROR",  # 500
    "SERVICE_UNAVAILABLE": "SERVICE_UNAVAILABLE",      # 503
    "DATABASE_ERROR": "DATABASE_ERROR",                # 500
    
    # Business Logic Errors (400, 422)
    "OPERATION_FAILED": "OPERATION_FAILED",         # 400
    "INVALID_STATE": "INVALID_STATE",               # 400
    "INSUFFICIENT_BALANCE": "INSUFFICIENT_BALANCE", # 400
    "QUOTA_EXCEEDED": "QUOTA_EXCEEDED",             # 429
    "RATE_LIMIT_EXCEEDED": "RATE_LIMIT_EXCEEDED",   # 429
}


_ISO_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _to_dd_mm_yyyy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _normalize_dates(obj: Any) -> Any:
    """Recursively convert dates to DD-MM-YYYY strings.

    - datetime/date objects -> DD-MM-YYYY
    - ISO-like strings starting with YYYY-MM-DD -> DD-MM-YYYY (date part only)
    """
    if obj is None:
        return None

    if isinstance(obj, datetime):
        return _to_dd_mm_yyyy(obj.date())

    if isinstance(obj, date):
        return _to_dd_mm_yyyy(obj)

    if isinstance(obj, BaseModel):
        # Support both Pydantic v1 and v2
        if hasattr(obj, "model_dump"):
            return _normalize_dates(obj.model_dump())
        return _normalize_dates(obj.dict())

    if isinstance(obj, dict):
        return {k: _normalize_dates(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_normalize_dates(v) for v in obj]

    if isinstance(obj, str) and _ISO_DATE_PREFIX.match(obj.strip()):
        s = obj.strip()
        try:
            # Convert leading YYYY-MM-DD regardless of time suffix
            yyyy, mm, dd = s[0:10].split("-")
            return f"{dd}-{mm}-{yyyy}"
        except Exception:
            return obj

    return obj


def ok(data: Any = None, message: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, status_code: int = status.HTTP_200_OK, error_code: Optional[str] = None) -> JSONResponse:
    payload: Dict[str, Any] = {"success": True}
    if message is not None:
        payload["message"] = message
    if error_code is not None:
        payload["error_code"] = error_code
    if data is not None:
        payload["data"] = _normalize_dates(data)
    if meta is not None:
        payload["meta"] = _normalize_dates(meta)
    return JSONResponse(status_code=status_code, content=_normalize_dates(payload))


def fail(message: str, status_code: int = status.HTTP_400_BAD_REQUEST, error_code: Optional[str] = None, data: Any = None, meta: Optional[Dict[str, Any]] = None) -> JSONResponse:
    """Return a failure response with standardized error code.
    
    Args:
        message: Human-readable error message
        status_code: HTTP status code (e.g., status.HTTP_400_BAD_REQUEST)
        error_code: Standardized error code for frontend consumption (e.g., 'VALIDATION_ERROR')
        data: Optional error details object
        meta: Optional metadata
    """
    payload: Dict[str, Any] = {"success": False, "message": message}
    if error_code is not None:
        payload["error_code"] = error_code
    if data is not None:
        payload["data"] = _normalize_dates(data)
    if meta is not None:
        payload["meta"] = _normalize_dates(meta)
    return JSONResponse(status_code=status_code, content=_normalize_dates(payload))
