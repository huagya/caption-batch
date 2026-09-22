"""Loose timing tests for RateLimiter."""
from __future__ import annotations

import time

from caption_batch.core.rate_limit import RateLimiter, make_rate_limiter


def test_make_rate_limiter_off():
    assert make_rate_limiter(None) is None
    assert make_rate_limiter(0) is None
    assert make_rate_limiter(-1) is None


def test_rate_limiter_spacing():
    lim = RateLimiter(requests_per_minute=600)  # 0.1s between calls
    assert lim is not None
    t0 = time.monotonic()
    lim.acquire()
    lim.acquire()
    lim.acquire()
    dt = time.monotonic() - t0
    # 2 intervals ≈ 0.2s; allow generous slack for CI
    assert dt >= 0.15
    assert dt < 1.5


def test_make_rate_limiter_rpm():
    lim = make_rate_limiter(30)
    assert lim is not None
    assert abs(lim.min_interval_sec - 2.0) < 1e-6
