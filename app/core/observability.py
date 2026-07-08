"""Lightweight in-memory 5xx error rate tracking for admin observability."""
import threading
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Deque, Tuple

_lock = threading.Lock()
_events: Deque[Tuple[datetime, bool]] = deque(maxlen=10000)


def record_response(status_code: int) -> None:
    is_error = status_code >= 500
    with _lock:
        _events.append((datetime.now(timezone.utc), is_error))


def get_error_rate_24h() -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    with _lock:
        recent = [(ts, err) for ts, err in _events if ts >= cutoff]
    if not recent:
        return 0.0
    errors = sum(1 for _, err in recent if err)
    return round(errors / len(recent) * 100, 2)
