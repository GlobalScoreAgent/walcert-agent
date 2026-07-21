"""In-memory IP rate limiter for free preview endpoints.

Designed for a single EC2 instance (no Redis). Thread-safe via Lock.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.requests import Request

# 8 requests per IP every 15 minutes (ADR 2026-07-21).
PREVIEW_RATE_LIMIT = 8
PREVIEW_RATE_WINDOW_SECONDS = 15 * 60


class InMemoryRateLimiter:
    """Sliding-window counter keyed by client IP."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit and return (allowed, retry_after_seconds).

        When denied, ``retry_after_seconds`` is how long until the oldest
        hit in the window expires (at least 1).
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self._limit:
                retry_after = max(1, int(q[0] + self._window - now) + 1)
                return False, retry_after
            q.append(now)
            return True, 0


_preview_limiter = InMemoryRateLimiter(PREVIEW_RATE_LIMIT, PREVIEW_RATE_WINDOW_SECONDS)


def client_ip(request: Request) -> str:
    """Best-effort client IP behind Cloudflare Tunnel."""
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_preview_rate_limit(request: Request) -> tuple[bool, int]:
    """Apply the preview rate limit for this request's client IP."""
    return _preview_limiter.check(client_ip(request))
