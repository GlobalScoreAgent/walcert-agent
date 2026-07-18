from __future__ import annotations

import time
from threading import Lock
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if now >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time() + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
