"""GoldRush (Covalent) Multichain — footprint + intensity (public + Summit alias)."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.providers.quota import get_quota
from app.providers.multichain_v2_metrics import (
    compute_multichain_v2_signals,
    select_intensity_chains,
)

GOLDRUSH_BASE = "https://api.covalenthq.com/v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GoldRushProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.quota = get_quota()

    def _ensure_credentials(self) -> None:
        if not self.settings.goldrush_api_key:
            raise MissingCredentials("goldrush")

    def _auth_header(self) -> str:
        # GoldRush accepts Bearer; Covalent Basic (key:) also works.
        key = self.settings.goldrush_api_key
        if key.lower().startswith("cqt_"):
            token = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
            return f"Basic {token}"
        return f"Bearer {key}"

    async def _get_json(
        self, client: httpx.AsyncClient, path: str, params: dict | None = None
    ) -> dict[str, Any]:
        url = f"{GOLDRUSH_BASE}{path}"
        headers = {
            "accept": "application/json",
            "Authorization": self._auth_header(),
        }
        try:
            response = await client.get(url, headers=headers, params=params or {})
        except httpx.HTTPError as exc:
            raise ProviderError("goldrush", f"network error: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                "goldrush",
                f"HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("goldrush", "invalid JSON response") from exc
        if isinstance(payload, dict) and payload.get("error") is True:
            msg = payload.get("error_message") or payload.get("error_code") or "api_error"
            raise ProviderError("goldrush", str(msg))
        return payload if isinstance(payload, dict) else {}

    def _parse_activity_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(
                item.get("name")
                or item.get("chain_name")
                or (item.get("chain") or {}).get("name")
                or ""
            ).lower()
            chain_id_raw = item.get("chain_id")
            try:
                chain_id = int(chain_id_raw) if chain_id_raw is not None else None
            except (TypeError, ValueError):
                chain_id = None
            out.append(
                {
                    "name": name,
                    "chain_id": chain_id,
                    "label": item.get("label") or name,
                    "category_label": item.get("category_label") or item.get("category"),
                    "is_testnet": bool(item.get("is_testnet")),
                    "is_appchain": bool(item.get("is_appchain")),
                    "first_seen_at": item.get("first_seen_at"),
                    "last_seen_at": item.get("last_seen_at"),
                }
            )
        return out

    def _parse_summary_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list) or not items:
            return {"tx_count": 0, "transfer_count": 0, "gas_spent_quote": None}
        item = items[0] if isinstance(items[0], dict) else {}
        gas = item.get("gas_summary") if isinstance(item.get("gas_summary"), dict) else {}
        gas_quote = gas.get("total_gas_quote") or gas.get("gas_quote") or gas.get(
            "total_spent_quote"
        )
        earliest = item.get("earliest_transaction")
        latest = item.get("latest_transaction")
        return {
            "tx_count": int(item.get("total_count") or 0),
            "transfer_count": int(item.get("transfer_count") or 0),
            "gas_spent_quote": float(gas_quote) if gas_quote is not None else None,
            "earliest_transaction": (
                earliest.get("block_signed_at")
                if isinstance(earliest, dict)
                else earliest
            ),
            "latest_transaction": (
                latest.get("block_signed_at") if isinstance(latest, dict) else latest
            ),
        }

    async def analyze_multichain_v2(self, wallet: str) -> dict[str, Any]:
        self._ensure_credentials()
        ok, retry = self.quota.can_consume_goldrush(1)
        if not ok:
            raise QuotaExceeded("goldrush", retry or "next_day")
        top_n = self.settings.goldrush_intensity_top_n
        wallet = wallet.lower()

        async with httpx.AsyncClient(
            timeout=self.settings.http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            activity_payload = await self._get_json(
                client,
                f"/address/{wallet}/activity/",
                params={"testnets": "false"},
            )
            activity_items = self._parse_activity_items(activity_payload)
            selected = select_intensity_chains(activity_items, top_n=top_n)

            async def fetch_one(name: str) -> tuple[str, dict[str, Any]]:
                try:
                    raw = await self._get_json(
                        client,
                        f"/{name}/address/{wallet}/transactions_summary/",
                        params={"with-gas": "true", "with-transfer-count": "true"},
                    )
                    return name, self._parse_summary_item(raw)
                except ProviderError:
                    return name, {
                        "tx_count": 0,
                        "transfer_count": 0,
                        "gas_spent_quote": None,
                    }

            summaries = await asyncio.gather(
                *[fetch_one(str(c["name"])) for c in selected]
            )
            summary_by_name = {n: s for n, s in summaries}

        for row in activity_items:
            name = str(row.get("name") or "")
            if name in summary_by_name:
                row.update(summary_by_name[name])
                row["intensity_sampled"] = True
            else:
                row["intensity_sampled"] = False

        signals = compute_multichain_v2_signals(
            activity_items,
            intensity_chain_names=[str(c["name"]) for c in selected],
        )
        self.quota.record_goldrush(1)
        return {
            "module": "multichain",
            "wallet": wallet,
            "analyzed_at": _now_iso(),
            "provider": "goldrush",
            **signals,
        }
