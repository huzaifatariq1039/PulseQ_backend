from __future__ import annotations
from typing import Callable, Dict, Any, Optional, Awaitable
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from app.database import get_db
from app.config import COLLECTIONS


class Idempotency:
    HEADER_NAME = "Idempotency-Key"

    @staticmethod
    def validate_key(key: Optional[str]) -> str:
        if not key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Idempotency-Key header")
        k = key.strip()
        if len(k) < 8 or len(k) > 128:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Idempotency-Key")
        return k

    @staticmethod
    def make_doc_id(user_id: str, key: str, action: str) -> str:
        return f"{user_id}_{action}_{key}"

    @staticmethod
    def get_or_run(user_id: str, key: str, action: str, ttl_minutes: int, runner: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        db = get_db()
        doc_id = Idempotency.make_doc_id(user_id, key, action)
        ref = db.collection(COLLECTIONS["IDEMPOTENCY"]).document(doc_id)
        snap = ref.get()
        if getattr(snap, "exists", False):
            data = snap.to_dict() or {}
            # Optional TTL check
            if ttl_minutes > 0:
                created = data.get("created_at")
                if created and isinstance(created, datetime):
                    if datetime.utcnow() - created > timedelta(minutes=ttl_minutes):
                        # Expired -> proceed to run again
                        pass
                    else:
                        return data.get("response") or {}
                else:
                    return data.get("response") or {}
            else:
                return data.get("response") or {}

        # Not found -> run and store
        result = runner() or {}
        ref.set({
            "id": doc_id,
            "user_id": user_id,
            "key": key,
            "action": action,
            "response": result,
            "created_at": datetime.utcnow(),
        })
        return result

    @staticmethod
    async def get_or_run_async(user_id: str, key: str, action: str, ttl_minutes: int, runner_async: Callable[[], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
        db = get_db()
        doc_id = Idempotency.make_doc_id(user_id, key, action)
        ref = db.collection(COLLECTIONS["IDEMPOTENCY"]).document(doc_id)
        snap = ref.get()
        if getattr(snap, "exists", False):
            data = snap.to_dict() or {}
            if ttl_minutes > 0:
                created = data.get("created_at")
                if created and isinstance(created, datetime):
                    if datetime.utcnow() - created <= timedelta(minutes=ttl_minutes):
                        return data.get("response") or {}
                else:
                    return data.get("response") or {}
            else:
                return data.get("response") or {}

        result = await runner_async()
        ref.set({
            "id": doc_id,
            "user_id": user_id,
            "key": key,
            "action": action,
            "response": result,
            "created_at": datetime.utcnow(),
        })
        return result
