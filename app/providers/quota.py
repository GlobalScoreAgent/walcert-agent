from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, QUOTA_FILE, Settings, get_settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m-%d")


def _month_key(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m")


class QuotaManager:
    """Tracks provider free-tier usage (calls or CU) with disk persistence."""

    def __init__(self, settings: Settings | None = None, path: Path | None = None):
        self.settings = settings or get_settings()
        self.path = path or QUOTA_FILE
        self._lock = threading.Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            "alchemy": {"daily_cu": {}, "monthly_cu": {}},
            "goldrush": {"daily_calls": {}},
            "zerion": {"daily_calls": {}},
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            base = self._default_state()
            for provider, buckets in base.items():
                incoming = data.get(provider) or {}
                for key in buckets:
                    buckets[key] = incoming.get(key) or {}
            return base
        except (json.JSONDecodeError, OSError):
            return self._default_state()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _get_counter(self, provider: str, bucket: str, key: str) -> int:
        return int(self._state[provider][bucket].get(key, 0))

    def estimate_alchemy_cu(self, http_calls: int) -> int:
        return http_calls * self.settings.alchemy_cu_per_transfer_call

    def can_consume_alchemy(self, cu: int) -> tuple[bool, str | None]:
        now = _utc_now()
        day = _day_key(now)
        month = _month_key(now)
        with self._lock:
            daily = self._get_counter("alchemy", "daily_cu", day)
            monthly = self._get_counter("alchemy", "monthly_cu", month)
        if self.settings.alchemy_daily_limit_cu is not None:
            if daily + cu > self.settings.alchemy_daily_limit_cu:
                return False, "next_day"
        if monthly + cu > self.settings.alchemy_monthly_limit_cu:
            return False, "next_month"
        return True, None

    def can_consume_goldrush(self, analyses: int = 1) -> tuple[bool, str | None]:
        day = _day_key()
        with self._lock:
            daily = self._get_counter("goldrush", "daily_calls", day)
        if daily + analyses > self.settings.goldrush_daily_limit:
            return False, "next_day"
        return True, None

    def can_consume_zerion(self, calls: int = 1) -> tuple[bool, str | None]:
        day = _day_key()
        with self._lock:
            daily = self._get_counter("zerion", "daily_calls", day)
        if daily + calls > self.settings.zerion_daily_limit:
            return False, "next_day"
        return True, None

    def record_alchemy(self, cu: int) -> None:
        now = _utc_now()
        day = _day_key(now)
        month = _month_key(now)
        with self._lock:
            self._state["alchemy"]["daily_cu"][day] = (
                self._get_counter("alchemy", "daily_cu", day) + cu
            )
            self._state["alchemy"]["monthly_cu"][month] = (
                self._get_counter("alchemy", "monthly_cu", month) + cu
            )
            self._save()

    def record_goldrush(self, analyses: int = 1) -> None:
        day = _day_key()
        with self._lock:
            self._state["goldrush"]["daily_calls"][day] = (
                self._get_counter("goldrush", "daily_calls", day) + analyses
            )
            self._save()

    def record_zerion(self, calls: int = 1) -> None:
        day = _day_key()
        with self._lock:
            self._state["zerion"]["daily_calls"][day] = (
                self._get_counter("zerion", "daily_calls", day) + calls
            )
            self._save()

    def snapshot(self) -> dict[str, Any]:
        now = _utc_now()
        day = _day_key(now)
        month = _month_key(now)
        with self._lock:
            return {
                "as_of": now.isoformat().replace("+00:00", "Z"),
                "alchemy": {
                    "unit": "cu",
                    "daily_used": self._get_counter("alchemy", "daily_cu", day),
                    "daily_limit": self.settings.alchemy_daily_limit_cu,
                    "monthly_used": self._get_counter("alchemy", "monthly_cu", month),
                    "monthly_limit": self.settings.alchemy_monthly_limit_cu,
                    "cu_per_transfer_call": self.settings.alchemy_cu_per_transfer_call,
                },
                "goldrush": {
                    "unit": "analyses",
                    "daily_used": self._get_counter("goldrush", "daily_calls", day),
                    "daily_limit": self.settings.goldrush_daily_limit,
                },
                "zerion": {
                    "unit": "calls",
                    "daily_used": self._get_counter("zerion", "daily_calls", day),
                    "daily_limit": self.settings.zerion_daily_limit,
                },
            }


_quota: QuotaManager | None = None


def get_quota() -> QuotaManager:
    global _quota
    if _quota is None:
        _quota = QuotaManager()
    return _quota
