"""Multichain v2 metrics from GoldRush activity + intensity summaries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.providers.core_ecosystems import (
    CORE_ECOSYSTEM_LIST_VERSION,
    normalize_core_slug,
)
from app.providers.chain_families import ecosystem_family_from_chain_name

DORMANT_DAYS = 180
CONSISTENCY_SPAN_DAYS = 90

# Deterministic intensity sampling priority (plan).
INTENSITY_PRIORITY: list[str] = [
    "eth-mainnet",
    "base-mainnet",
    "arbitrum-mainnet",
    "optimism-mainnet",
    "celo-mainnet",
    "matic-mainnet",
    "bsc-mainnet",
    "avalanche-mainnet",
]

KNOWN_L2_NAMES = {
    "base-mainnet",
    "arbitrum-mainnet",
    "optimism-mainnet",
    "matic-mainnet",
    "polygon-mainnet",
    "zora-mainnet",
    "scroll-mainnet",
    "linea-mainnet",
}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _days_between(a: datetime | None, b: datetime | None) -> int:
    if not a or not b:
        return 0
    return max(0, (b - a).days)


def _days_since(dt: datetime | None, now: datetime) -> int | None:
    if not dt:
        return None
    return max(0, (now - dt).days)


def select_intensity_chains(
    activity_items: list[dict[str, Any]],
    *,
    top_n: int = 6,
    priority: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pick up to top_n mainnet chains: priority ∩ present, then fill by recency/span."""
    priority = priority or INTENSITY_PRIORITY
    mainnets = [
        c
        for c in activity_items
        if not c.get("is_testnet") and str(c.get("name") or "").strip()
    ]
    by_name = {str(c.get("name") or "").lower(): c for c in mainnets}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in priority:
        key = name.lower()
        if key in by_name and key not in seen:
            selected.append(by_name[key])
            seen.add(key)
        if len(selected) >= top_n:
            return selected

    def sort_key(c: dict[str, Any]) -> tuple[float, float]:
        last = _parse_ts(c.get("last_seen_at") if isinstance(c.get("last_seen_at"), str) else None)
        first = _parse_ts(
            c.get("first_seen_at") if isinstance(c.get("first_seen_at"), str) else None
        )
        since = _days_since(last, datetime.now(timezone.utc))
        span = _days_between(first, last)
        # Prefer recent (low since) then longer span
        return (since if since is not None else 10_000, -float(span))

    rest = sorted(
        [c for c in mainnets if str(c.get("name") or "").lower() not in seen],
        key=sort_key,
    )
    for c in rest:
        if len(selected) >= top_n:
            break
        selected.append(c)
        seen.add(str(c.get("name") or "").lower())
    return selected


def compute_multichain_v2_signals(
    activity_items: list[dict[str, Any]],
    *,
    intensity_chain_names: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute Multichain v2 footprint + intensity signals."""
    now = now or datetime.now(timezone.utc)
    _ = intensity_chain_names  # selection already applied via intensity_sampled flags
    mainnets = [c for c in activity_items if not c.get("is_testnet")]
    testnets = [c for c in activity_items if c.get("is_testnet")]

    enriched: list[dict[str, Any]] = []
    first_all: datetime | None = None
    last_all: datetime | None = None
    categories: set[str] = set()
    core_set: list[str] = []
    core_seen: set[str] = set()
    l2_count = 0

    for raw in mainnets:
        name = str(raw.get("name") or "").lower()
        first = _parse_ts(
            raw.get("first_seen_at") if isinstance(raw.get("first_seen_at"), str) else None
        )
        last = _parse_ts(
            raw.get("last_seen_at") if isinstance(raw.get("last_seen_at"), str) else None
        )
        if first and not last:
            last = first
        if last and not first:
            first = last
        span = _days_between(first, last)
        since_last = _days_since(last, now)
        is_recent_30d = since_last is not None and since_last <= 30
        is_recent_90d = since_last is not None and since_last <= 90
        is_dormant = since_last is not None and since_last > DORMANT_DAYS
        if first and (first_all is None or first < first_all):
            first_all = first
        if last and (last_all is None or last > last_all):
            last_all = last
        family = ecosystem_family_from_chain_name(name)
        if family:
            categories.add(family)
        is_app = bool(raw.get("is_appchain")) or name in KNOWN_L2_NAMES
        if is_app:
            l2_count += 1
        slug = normalize_core_slug(name)
        if slug and slug not in core_seen:
            core_seen.add(slug)
            core_set.append(slug)
        enriched.append(
            {
                **raw,
                "name": name,
                "span_days": span,
                "is_recent_30d": is_recent_30d,
                "is_recent_90d": is_recent_90d,
                "is_dormant": is_dormant,
                "is_l2_or_appchain": is_app,
                "ecosystem_family": family,
                "tx_count": int(raw.get("tx_count") or 0),
                "transfer_count": int(raw.get("transfer_count") or 0),
                "gas_spent_quote": raw.get("gas_spent_quote"),
                "intensity_sampled": bool(raw.get("intensity_sampled")),
            }
        )
    core_set.sort()

    n = len(enriched)
    span_days = _days_between(first_all, last_all)
    active_30 = sum(1 for r in enriched if r.get("is_recent_30d"))
    active_90 = sum(1 for r in enriched if r.get("is_recent_90d"))
    dormant_n = sum(1 for r in enriched if r.get("is_dormant"))
    dormant_ratio = round(dormant_n / n, 4) if n else 0.0
    consistent_n = sum(
        1 for r in enriched if int(r.get("span_days") or 0) > CONSISTENCY_SPAN_DAYS
    )
    consistency_score = round(consistent_n / n, 4) if n else 0.0
    recency_vals = [
        1.0 if r.get("is_recent_30d") else (0.5 if r.get("is_recent_90d") else 0.0)
        for r in enriched
    ]
    recency_score = round(sum(recency_vals) / n, 4) if n else 0.0

    spans = [max(0, int(r.get("span_days") or 0)) for r in enriched]
    total_span = sum(spans)
    hhi = 0.0
    if total_span > 0:
        for s in spans:
            share = s / total_span
            hhi += share * share
    elif n > 0:
        share = 1.0 / n
        hhi = n * share * share

    # Intensity from sampled chains
    sampled = [r for r in enriched if r.get("intensity_sampled")]
    tx_counts = [max(0, int(r.get("tx_count") or 0)) for r in sampled]
    total_tx = sum(tx_counts)
    tx_hhi = 0.0
    if total_tx > 0:
        for t in tx_counts:
            share = t / total_tx
            tx_hhi += share * share
    elif sampled:
        share = 1.0 / len(sampled)
        tx_hhi = len(sampled) * share * share

    # Weighted activity: normalize tx * recency weight per sampled chain
    weighted = 0.0
    if sampled:
        max_tx = max(tx_counts) if tx_counts else 0
        for r in sampled:
            tx = int(r.get("tx_count") or 0)
            w_tx = (tx / max_tx) if max_tx > 0 else 0.0
            w_rec = (
                1.0
                if r.get("is_recent_30d")
                else (0.5 if r.get("is_recent_90d") else 0.15)
            )
            weighted += w_tx * w_rec
        weighted = round(weighted / len(sampled), 4)

    primary = None
    if sampled:
        primary = max(
            sampled,
            key=lambda r: (int(r.get("tx_count") or 0), int(r.get("span_days") or 0)),
        )
    gas_total = 0.0
    gas_any = False
    for r in sampled:
        g = r.get("gas_spent_quote")
        if g is not None:
            try:
                gas_total += float(g)
                gas_any = True
            except (TypeError, ValueError):
                pass

    intensity = {
        "chains_sampled": len(sampled),
        "sampled_chains": [str(r.get("name")) for r in sampled],
        "total_tx_count": total_tx,
        "tx_hhi": round(tx_hhi, 4),
        "primary_chain": (primary or {}).get("name") if primary else None,
        "weighted_activity_score": weighted,
        "gas_footprint_quote": round(gas_total, 4) if gas_any else None,
    }

    return {
        "version": "2.0",
        "formula_hint": "multichain-v2.1",
        "core_ecosystem_list_version": CORE_ECOSYSTEM_LIST_VERSION,
        "total_chains_mainnet": n,
        "total_chains_testnet": len(testnets),
        "ecosystem_count": len(categories),
        "l2_or_appchain_count": l2_count,
        "activity_span_days": span_days,
        "active_chains_30d": active_30,
        "active_chains_90d": active_90,
        "dormant_ratio": dormant_ratio,
        "consistency_score": consistency_score,
        "recency_score": recency_score,
        "footprint_concentration": round(hhi, 4),
        "core_ecosystems": core_set,
        "core_ecosystem_count": len(core_set),
        "intensity": intensity,
        "intensity_priority": INTENSITY_PRIORITY,
        "chains": enriched,
        "score_inputs": {
            "chain_count_score": round(min(1.0, n / 6.0), 2),
            "ecosystem_diversity_score": round(min(1.0, len(categories) / 4.0), 2),
            "longevity_score": round(min(1.0, span_days / 1000.0), 2) if span_days else 0.0,
            "recency_score": round(recency_score, 2),
            "consistency_score": round(consistency_score, 2),
            "intensity_score": round(min(1.0, total_tx / 200.0), 2),
        },
    }
