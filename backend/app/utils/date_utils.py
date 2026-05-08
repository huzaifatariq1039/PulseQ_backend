from datetime import datetime
from typing import Any, Optional


def to_dt(v: Any) -> Optional[datetime]:
	try:
		if v is None:
			return None
		if isinstance(v, datetime):
			return v
		to_dt_method = getattr(v, "to_datetime", None)
		if callable(to_dt_method):
			return to_dt_method()
		return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
	except Exception:
		return None


def is_empty(v: Any) -> bool:
	return v is None or str(v).strip() == ""
