from typing import Dict, Set

# Canonical token statuses used across the app
STATUS_WAITING = "pending"      # alias: waiting
STATUS_CONFIRMED = "confirmed"
STATUS_CALLED = "called"
STATUS_IN_QUEUE = "in_queue"
STATUS_IN_CONSULTATION = "in_consultation"  # explicit web state before done
STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"
STATUS_IN_PROGRESS = "in_progress"  # legacy alias used in some mobile flows

# Allowed state transitions for web safety
# Key: from_status -> set of to_status
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    STATUS_WAITING: {STATUS_CALLED, STATUS_IN_CONSULTATION, STATUS_CANCELLED, STATUS_CONFIRMED, STATUS_IN_QUEUE},
    STATUS_CONFIRMED: {STATUS_WAITING, STATUS_CALLED, STATUS_IN_CONSULTATION, STATUS_IN_QUEUE},
    STATUS_IN_QUEUE: {STATUS_CALLED, STATUS_IN_CONSULTATION, STATUS_CANCELLED},
    STATUS_CALLED: {STATUS_IN_CONSULTATION, STATUS_SKIPPED},
    STATUS_IN_PROGRESS: {STATUS_IN_CONSULTATION, STATUS_COMPLETED}, # legacy -> map to stricter flow
    STATUS_IN_CONSULTATION: {STATUS_COMPLETED},                     # DONE allowed only from in_consultation
}


def is_transition_allowed(current: str, target: str) -> bool:
    c = (current or "").lower()
    t = (target or "").lower()
    # Normalize common aliases
    if c == "waiting":
        c = STATUS_WAITING
    if t == "waiting":
        t = STATUS_WAITING
    # Backward compatibility for in_progress
    if c == STATUS_IN_PROGRESS:
        c = STATUS_IN_PROGRESS
    if t == STATUS_IN_PROGRESS:
        t = STATUS_IN_PROGRESS
    allowed = ALLOWED_TRANSITIONS.get(c, set())
    return t in allowed
