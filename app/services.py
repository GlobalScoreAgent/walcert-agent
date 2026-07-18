from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.models import PROVIDER_BY_TYPE
from app.providers.alchemy import AlchemyProvider
from app.providers.cache import TTLCache
from app.providers.edge_scoring import EdgeScoringClient
from app.providers.moralis import MoralisProvider
from app.providers.zerion import ZerionProvider

_settings = get_settings()
_cache = TTLCache(ttl_seconds=_settings.cache_ttl_seconds)
_alchemy = AlchemyProvider()
_moralis = MoralisProvider()
_zerion = ZerionProvider()
_edge = EdgeScoringClient()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def _merge_celo_into_multichain(
    analysis: dict[str, Any], wallet: str
) -> dict[str, Any]:
    chains = list(analysis.get("chains") or [])
    if any(str(c.get("chain", "")).lower() == "celo" for c in chains):
        return analysis

    celo = await _alchemy.probe_celo_activity(wallet)
    if not celo:
        return analysis

    chains.append(celo)
    first_all: datetime | None = None
    last_all: datetime | None = None
    for item in chains:
        first_dt = _parse_ts(
            item.get("first_transaction")
            if isinstance(item.get("first_transaction"), str)
            else None
        )
        last_dt = _parse_ts(
            item.get("last_transaction")
            if isinstance(item.get("last_transaction"), str)
            else None
        )
        if first_dt and (first_all is None or first_dt < first_all):
            first_all = first_dt
        if last_dt and (last_all is None or last_dt > last_all):
            last_all = last_dt

    span_days = 0
    if first_all and last_all:
        span_days = max(0, (last_all - first_all).days)

    chain_count = len(chains)
    longevity = min(1.0, span_days / 1000.0) if span_days else 0.0
    consistency = min(1.0, chain_count / 5.0)
    analysis = dict(analysis)
    analysis["chains"] = chains
    analysis["total_chains_with_activity"] = chain_count
    analysis["activity_span_days"] = span_days
    analysis["score_inputs"] = {
        "chain_count": chain_count,
        "activity_consistency": round(consistency, 2),
        "longevity_score": round(longevity, 2),
    }
    analysis["celo_merged"] = True
    return analysis


async def run_certificate(certificate_type: str, wallet: str) -> dict[str, Any]:
    cache_key = f"{certificate_type}:{wallet.lower()}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    if certificate_type == "origins":
        analysis = await _alchemy.analyze_origins(wallet)
    elif certificate_type == "activity":
        analysis = await _alchemy.analyze_activity(wallet)
    elif certificate_type == "multichain":
        analysis = await _moralis.analyze_multichain(wallet)
        try:
            analysis = await _merge_celo_into_multichain(analysis, wallet)
        except (ProviderError, QuotaExceeded, MissingCredentials):
            # Multichain still valid without Celo merge
            pass
    elif certificate_type == "portfolio":
        analysis = await _zerion.analyze_portfolio(wallet)
    else:
        raise ProviderError("agent", f"unknown certificate type: {certificate_type}")

    result: dict[str, Any] = {
        "available": True,
        "status": "ok",
        "mode": "hot",
        "certificate_type": certificate_type,
        "provider": PROVIDER_BY_TYPE[certificate_type],
        "analysis": analysis,
    }

    if _settings.edge_scoring_enabled and _edge.enabled():
        analyzed_at = str(analysis.get("analyzed_at") or datetime.now(timezone.utc).isoformat())
        certificate = await _edge.score(
            certificate_type, wallet, analyzed_at, analysis
        )
        result["certificate"] = certificate
    elif _settings.edge_scoring_enabled:
        raise ProviderError(
            "edge",
            "EDGE_SHARED_SECRET / SUPABASE_FUNCTIONS_URL not configured",
        )

    _cache.set(cache_key, result)
    return result


__all__ = [
    "run_certificate",
    "QuotaExceeded",
    "ProviderError",
    "MissingCredentials",
]
