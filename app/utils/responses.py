from typing import Any, Dict, Optional
from fastapi.responses import JSONResponse
from fastapi import status
from datetime import date, datetime
import re


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


def ok(data: Any = None, message: Optional[str] = None, meta: Optional[Dict[str, Any]] = None, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    payload: Dict[str, Any] = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = _normalize_dates(data)
    if meta is not None:
        payload["meta"] = _normalize_dates(meta)
    return JSONResponse(status_code=status_code, content=_normalize_dates(payload))


def fail(message: str, status_code: int = status.HTTP_400_BAD_REQUEST, data: Any = None, meta: Optional[Dict[str, Any]] = None) -> JSONResponse:
    payload: Dict[str, Any] = {"success": False, "message": message}
    if data is not None:
        payload["data"] = _normalize_dates(data)
    if meta is not None:
        payload["meta"] = _normalize_dates(meta)
    return JSONResponse(status_code=status_code, content=_normalize_dates(payload))
