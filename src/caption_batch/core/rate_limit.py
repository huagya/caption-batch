"""Thread-safe global rate limiter for provider API calls."""

from __future__ import annotations

import threading
import time
from typing import Optional


class RateLimiter:
    """Serialize callers so requests are spaced by min_interval_sec."""

    def __init__(
        self,
        *,
        min_interval_sec: float | None = None,
        requests_per_minute: float | None = None,
    ) -> None:
        if min_interval_sec is not None and min_interval_sec < 0:
            raise ValueError("min_interval_sec must be >= 0")
        if requests_per_minute is not None and requests_per_minute < 0:
            raise ValueError("requests_per_minute must be >= 0")
        if min_interval_sec is None and requests_per_minute is None:
            raise ValueError("provide min_interval_sec or requests_per_minute")
        if min_interval_sec is not None:
            self.min_interval_sec = float(min_interval_sec)
        else:
            rpm = float(requests_per_minute or 0)
            self.min_interval_sec = (60.0 / rpm) if rpm > 0 else 0.0
        self._lock = threading.Lock()
        self._next_ok_at = 0.0

    def acquire(self) -> None:
        """Block until the next request slot is available, then claim it."""
        if self.min_interval_sec <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_ok_at - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next_ok_at = now + self.min_interval_sec


def make_rate_limiter(rate_limit_rpm: int | None) -> Optional[RateLimiter]:
    """Return a RateLimiter for RPM, or None if disabled (None/0)."""
    if rate_limit_rpm is None or int(rate_limit_rpm) <= 0:
        return None
    return RateLimiter(requests_per_minute=float(rate_limit_rpm))
