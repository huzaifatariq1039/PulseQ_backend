from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.config import TOKEN_FEE


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return f
    except Exception:
        return None


def compute_total_amount(
    *,
    consultation_fee: Any,
    session_fee: Any,
    include_consultation_fee: Optional[bool],
    include_session_fee: Optional[bool],
) -> Dict[str, Any]:
   
    token_fee = float(TOKEN_FEE)
    c = _to_float(consultation_fee)
    s = _to_float(session_fee)

    # Defaults: if flags not provided, include consultation when present; include session when present.
    inc_c = include_consultation_fee if include_consultation_fee is not None else (c is not None and c > 0)
    inc_s = include_session_fee if include_session_fee is not None else (s is not None and s > 0)

    # Normalize selected fees
    selected_c = c if (inc_c and c is not None and c > 0) else None
    selected_s = s if (inc_s and s is not None and s > 0) else None

    medical_total = float(selected_c or 0) + float(selected_s or 0)
    total_amount = token_fee + medical_total

    return {
        "token_fee": token_fee,
        "consultation_fee": selected_c,
        "session_fee": selected_s,
        "total_fee": medical_total,
        "total_amount": total_amount,
        "include_consultation_fee": bool(inc_c),
        "include_session_fee": bool(inc_s),
    }

