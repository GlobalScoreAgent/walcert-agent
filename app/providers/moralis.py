from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.providers.quota import QuotaManager, get_quota

MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"

CHAIN_ID_MAP: dict[str, int] = {
    "eth": 1,
    "ethereum": 1,
    "base": 8453,
    "celo": 42220,
    "arbitrum": 42161,
    "polygon": 137,
    "optimism": 10,
    "bsc": 56,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_int_id(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        return int(text, 0)
    except ValueError:
        return None


class MoralisProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        quota: QuotaManager | None = None,
    ):
        self.settings = settings or get_settings()
        self.quota = quota or get_quota()

    def _ensure_credentials(self) -> None:
        if not self.settings.moralis_api_key:
            raise MissingCredentials("moralis")

    async def analyze_multichain(self, wallet: str) -> dict[str, Any]:
        self._ensure_credentials()
        chains = self.settings.moralis_chains
        estimated = self.quota.estimate_moralis_cu(len(chains))
        ok, retry = self.quota.can_consume_moralis(estimated)
        if not ok:
            raise QuotaExceeded("moralis", retry or "next_day")

        params = [("chains", c) for c in chains]
        headers = {
            "accept": "application/json",
            "X-API-Key": self.settings.moralis_api_key,
        }
        url = f"{MORALIS_BASE}/wallets/{wallet}/chains"

        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise ProviderError("moralis", f"network error: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                "moralis",
                f"HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )

        payload = response.json()
        active = payload.get("active_chains") or payload.get("chains") or []
        if isinstance(payload, list):
            active = payload

        normalized: list[dict[str, Any]] = []
        first_all: datetime | None = None
        last_all: datetime | None = None

        for item in active:
            chain_name = (
                item.get("chain")
                or item.get("name")
                or item.get("chain_id")
                or "unknown"
            )
            chain_key = str(chain_name).lower()
            chain_id = _as_int_id(item.get("chain_id") or CHAIN_ID_MAP.get(chain_key))
            first_tx = (
                (item.get("first_transaction") or {}).get("block_timestamp")
                if isinstance(item.get("first_transaction"), dict)
                else item.get("first_transaction")
            )
            last_tx = (
                (item.get("last_transaction") or {}).get("block_timestamp")
                if isinstance(item.get("last_transaction"), dict)
                else item.get("last_transaction")
            )
            first_dt = _parse_ts(first_tx)
            last_dt = _parse_ts(last_tx)
            # Moralis echoes every requested chain in active_chains and marks
            # the absence of on-chain activity with null timestamps. Only count
            # a chain as active when it has at least one real transaction.
            if first_dt is None and last_dt is None:
                continue
            if first_dt and (first_all is None or first_dt < first_all):
                first_all = first_dt
            if last_dt and (last_all is None or last_dt > last_all):
                last_all = last_dt
            normalized.append(
                {
                    "chain": chain_key,
                    "chain_id": chain_id,
                    "first_transaction": (
                        first_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if first_dt else first_tx
                    ),
                    "last_transaction": (
                        last_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if last_dt else last_tx
                    ),
                }
            )

        # Bill for requested chain set (conservative estimate used at check time)
        actual_cu = self.quota.estimate_moralis_cu(len(chains))
        self.quota.record_moralis(actual_cu)

        span_days = 0
        if first_all and last_all:
            span_days = max(0, (last_all - first_all).days)

        chain_count = len(normalized)
        longevity = min(1.0, span_days / 1000.0) if span_days else 0.0
        consistency = min(1.0, chain_count / 5.0)

        return {
            "module": "multichain",
            "wallet": wallet,
            "analyzed_at": _now_iso(),
            "total_chains_with_activity": chain_count,
            "chains": normalized,
            "activity_span_days": span_days,
            "score_inputs": {
                "chain_count": chain_count,
                "activity_consistency": round(consistency, 2),
                "longevity_score": round(longevity, 2),
            },
        }
