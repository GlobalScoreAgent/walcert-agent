from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.providers.quota import QuotaManager, get_quota

ZERION_BASE = "https://api.zerion.io/v1"
POSITIONS_CAP = 200

STABLE_SYMBOLS = {"USDC", "USDT", "DAI", "CUSD", "USDM", "EURC", "USDCE"}
BLUECHIP_SYMBOLS = {
    "ETH",
    "WETH",
    "BTC",
    "WBTC",
    "CELO",
    "MATIC",
    "POL",
    "ARB",
    "OP",
    "BNB",
    "SOL",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _classify_position(symbol: str, name: str, position_type: str | None) -> tuple[str, str]:
    sym = (symbol or "").upper()
    n = (name or "").lower()
    ptype = (position_type or "").lower()
    if "liquidity" in ptype or "pool" in n or "lp" in sym.lower():
        return "defi_lp", "locked" if "staked" in ptype or "locked" in ptype else "liquid"
    if sym in STABLE_SYMBOLS or "usd" in sym.lower():
        return "stablecoin", "liquid"
    if sym in BLUECHIP_SYMBOLS:
        return "bluechip", "liquid"
    if "staked" in ptype or "locked" in ptype or "deposit" in ptype:
        return "meme_or_other", "locked"
    return "meme_or_other", "liquid"


class ZerionProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        quota: QuotaManager | None = None,
    ):
        self.settings = settings or get_settings()
        self.quota = quota or get_quota()

    def _ensure_credentials(self) -> None:
        if not self.settings.zerion_api_key:
            raise MissingCredentials("zerion")

    def _auth_header(self) -> str:
        token = base64.b64encode(
            f"{self.settings.zerion_api_key}:".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"

    async def analyze_portfolio(self, wallet: str) -> dict[str, Any]:
        self._ensure_credentials()
        ok, retry = self.quota.can_consume_zerion(1)
        if not ok:
            raise QuotaExceeded("zerion", retry or "next_day")

        url = f"{ZERION_BASE}/wallets/{wallet}/positions/"
        headers = {
            "accept": "application/json",
            "Authorization": self._auth_header(),
        }
        # No only_simple — include DeFi / complex positions (same request cost)
        params = {"currency": "usd"}

        async with httpx.AsyncClient(
            timeout=self.settings.http_timeout_seconds,
            follow_redirects=True,
        ) as client:
            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise ProviderError("zerion", f"network error: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                "zerion",
                f"HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "zerion",
                f"invalid JSON response (HTTP {response.status_code})",
                status_code=response.status_code,
            ) from exc

        self.quota.record_zerion(1)
        items = payload.get("data") or []

        total = liquid = locked = 0.0
        category_value: dict[str, float] = {
            "stablecoin": 0.0,
            "bluechip": 0.0,
            "defi_lp": 0.0,
            "meme_or_other": 0.0,
        }
        positions: list[dict[str, Any]] = []

        for item in items:
            attrs = item.get("attributes") or {}
            fungible = attrs.get("fungible_info") or {}
            symbol = fungible.get("symbol") or attrs.get("symbol") or "?"
            name = fungible.get("name") or attrs.get("name") or symbol
            value = attrs.get("value")
            if value is None:
                quantity = attrs.get("quantity") or {}
                value = quantity.get("float") or 0
            try:
                value_usd = float(value or 0)
            except (TypeError, ValueError):
                value_usd = 0.0
            position_type = attrs.get("position_type")
            protocol = attrs.get("protocol")
            flags = fungible.get("flags") if isinstance(fungible.get("flags"), dict) else {}
            verified = fungible.get("verified")
            if verified is None and "verified" in flags:
                verified = flags.get("verified")
            category, classification = _classify_position(
                symbol, name, str(position_type or protocol or "")
            )
            total += value_usd
            category_value[category] += value_usd
            if classification == "locked":
                locked += value_usd
            else:
                liquid += value_usd
            positions.append(
                {
                    "name": name,
                    "symbol": symbol,
                    "value_usd": round(value_usd, 2),
                    "category": category,
                    "classification": classification,
                    "position_type": position_type,
                    "protocol": protocol,
                    "flags": flags or None,
                    "verified": verified,
                }
            )

        positions.sort(key=lambda x: x["value_usd"], reverse=True)
        positions = positions[:POSITIONS_CAP]
        top_positions = positions[:10]
        liquid_ratio = round(100.0 * liquid / total, 1) if total else 0.0

        def share(cat: str) -> float:
            return round(100.0 * category_value[cat] / total, 1) if total else 0.0

        size_score = min(1.0, total / 20000.0)
        liquidity_score = liquid / total if total else 0.0
        divers = min(1.0, len(items) / 15.0)
        risk = 1.0 - (category_value["meme_or_other"] / total if total else 0.0)

        return {
            "module": "portfolio",
            "wallet": wallet.lower(),
            "analyzed_at": _now_iso(),
            "total_value_usd": round(total, 2),
            "liquid_value_usd": round(liquid, 2),
            "locked_value_usd": round(locked, 2),
            "liquid_ratio": liquid_ratio,
            "positions_count": len(items),
            "category_distribution": {
                "stablecoin": share("stablecoin"),
                "bluechip": share("bluechip"),
                "defi_lp": share("defi_lp"),
                "meme_or_other": share("meme_or_other"),
            },
            "positions": positions,
            "top_positions": top_positions,
            "score_inputs": {
                "portfolio_size_score": round(size_score, 2),
                "liquidity_score": round(liquidity_score, 2),
                "diversification_score": round(divers, 2),
                "risk_exposure_score": round(risk, 2),
            },
        }
