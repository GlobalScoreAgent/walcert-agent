from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.models import PROVIDER_BY_TYPE
from app.providers.alchemy import AlchemyProvider
from app.providers.cache import TTLCache
from app.providers.edge_scoring import EdgeScoringClient
from app.providers.goldrush import GoldRushProvider
from app.providers.zerion import ZerionProvider

_settings = get_settings()
_cache = TTLCache(ttl_seconds=_settings.cache_ttl_seconds)
_alchemy = AlchemyProvider()
_zerion = ZerionProvider()
_goldrush = GoldRushProvider()
_edge = EdgeScoringClient()

# Locks por cache_key para evitar firmar/anclar dos veces el mismo certificado.
_certify_locks: dict[str, asyncio.Lock] = {}


def _sync_origins_analysis_from_certificate(
    analysis: dict[str, Any], certificate: dict[str, Any]
) -> dict[str, Any]:
    """Align agent origin_summary with Edge-canonical certificate details."""
    details = certificate.get("details") if isinstance(certificate, dict) else None
    if not isinstance(details, dict):
        return analysis
    out = dict(analysis)
    main = details.get("main_origin_type")
    cex = details.get("cex_percentage")
    bridge = details.get("bridge_percentage")
    cats = details.get("category_percentages") or {}
    summary = dict(out.get("origin_summary") or {})
    if main is not None:
        summary["main_origin_type"] = main
    if cex is not None:
        summary["cex_percentage"] = cex
    if bridge is not None:
        summary["bridge_percentage"] = bridge
    if isinstance(cats, dict):
        if "dex" in cats:
            summary["dex_percentage"] = cats.get("dex")
        if "organic" in cats:
            summary["other_percentage"] = cats.get("organic")
        elif "unknown" in cats:
            summary["other_percentage"] = cats.get("unknown")
    summary["canonical_source"] = "edge"
    out["origin_summary"] = summary
    if main is not None:
        out["main_origin_type"] = main
    if details.get("hhi") is not None:
        out["hhi"] = details.get("hhi")
    if details.get("concentration") is not None:
        out["concentration"] = details.get("concentration")
    if cats:
        out["category_percentages"] = cats
    return out


async def run_certificate(
    certificate_type: str, wallet: str, certify: bool = False
) -> dict[str, Any]:
    from app.internal_access import AccessContext, get_access, set_access

    ctx = get_access()
    if not certify:
        billing = "free"
    elif ctx.is_summit:
        billing = "free"
    elif ctx.is_internal:
        billing = "marketplace"
    else:
        billing = "x402"
    set_access(
        AccessContext(
            access_channel=ctx.access_channel,
            marketplace=ctx.marketplace,
            billing=billing,
        )
    )
    access_meta = {
        "access_channel": ctx.access_channel,
        "marketplace": ctx.marketplace if ctx.skips_x402 else None,
        "billing": billing,
    }

    # Include channel/marketplace so internal traffic is scored+logged separately
    # from direct (attribution rows in certificate_requests).
    market_part = access_meta.get("marketplace") or "none"
    cache_key = (
        f"{certificate_type}:{wallet.lower()}:"
        f"{access_meta['access_channel']}:{market_part}:{billing}"
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        if certify:
            cached = await _maybe_certify(cache_key, cached)
        return cached

    if certificate_type == "origins":
        analysis = await _alchemy.analyze_origins(wallet)
    elif certificate_type == "activity":
        analysis = await _alchemy.analyze_activity(wallet)
    elif certificate_type == "multichain":
        analysis = await _goldrush.analyze_multichain_v2(wallet)
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
            certificate_type,
            wallet,
            analyzed_at,
            analysis,
            access_meta=access_meta,
        )
        result["certificate"] = certificate
        if certificate_type == "origins":
            analysis = _sync_origins_analysis_from_certificate(analysis, certificate)
            result["analysis"] = analysis
    elif _settings.edge_scoring_enabled:
        raise ProviderError(
            "edge",
            "EDGE_SHARED_SECRET / SUPABASE_FUNCTIONS_URL not configured",
        )

    _cache.set(cache_key, result)

    if certify:
        result = await _maybe_certify(cache_key, result)

    return result


async def _maybe_certify(cache_key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Firma EIP-712 + ancla on-chain el certificado una sola vez (idempotente).

    Solo aplica en el endpoint pagado. Best-effort: si el anclaje falla, el
    certificado igual se entrega con `onchain.status = "failed"`.
    """
    if not (_settings.cert_signing_enabled or _settings.onchain_anchor_enabled):
        return result
    cert = result.get("certificate")
    if not cert or cert.get("signature") or cert.get("onchain"):
        return result

    lock = _certify_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        # Re-check tras el lock: otra corrutina pudo certificar mientras esperaba.
        cert = result.get("certificate")
        if not cert or cert.get("signature") or cert.get("onchain"):
            return result

        from app import onchain
        from app.onchain_log import schedule_onchain_log

        certified = await asyncio.to_thread(onchain.certify, cert)
        result["certificate"] = certified
        _cache.set(cache_key, result)

        # Persistencia en Supabase (fire-and-forget, tras la respuesta).
        schedule_onchain_log(
            certified.get("certificate_id"),
            certified.get("onchain"),
            certified.get("signature"),
        )
    return result


async def run_multichain_v2_summit(wallet: str) -> dict[str, Any]:
    """Summit-only Multichain v2 (GoldRush). Caller must enforce Summit auth."""
    from app.internal_access import AccessContext, get_access, set_access

    ctx = get_access()
    if not ctx.is_summit:
        raise ProviderError("agent", "summit_only", status_code=403)

    set_access(
        AccessContext(
            access_channel="summit",
            marketplace=ctx.marketplace or _settings.walcert_summit_marketplace,
            billing="free",
        )
    )
    access_meta = {
        "access_channel": "summit",
        "marketplace": ctx.marketplace or _settings.walcert_summit_marketplace,
        "billing": "free",
    }
    cache_key = f"multichain_v2:{wallet.lower()}:summit:{access_meta['marketplace']}:free"
    cached = _cache.get(cache_key)
    if cached is not None:
        return await _maybe_certify(cache_key, cached)

    analysis = await _goldrush.analyze_multichain_v2(wallet)
    result: dict[str, Any] = {
        "available": True,
        "status": "ok",
        "mode": "hot",
        "certificate_type": "multichain_v2",
        "provider": "goldrush",
        "analysis": analysis,
    }

    if _settings.edge_scoring_enabled and _edge.enabled():
        analyzed_at = str(
            analysis.get("analyzed_at") or datetime.now(timezone.utc).isoformat()
        )
        certificate = await _edge.score(
            "multichain_v2",
            wallet,
            analyzed_at,
            analysis,
            access_meta=access_meta,
        )
        result["certificate"] = certificate
    elif _settings.edge_scoring_enabled:
        raise ProviderError(
            "edge",
            "EDGE_SHARED_SECRET / SUPABASE_FUNCTIONS_URL not configured",
        )

    _cache.set(cache_key, result)
    return await _maybe_certify(cache_key, result)


__all__ = [
    "run_certificate",
    "run_multichain_v2_summit",
    "QuotaExceeded",
    "ProviderError",
    "MissingCredentials",
]
