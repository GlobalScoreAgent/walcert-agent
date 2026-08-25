"""Versioned core ecosystem list for Multichain v1.5.

Edge mirrors these in `_shared/core_ecosystems.ts` — bump CORE_ECOSYSTEM_LIST_VERSION
together when changing membership.
"""

from __future__ import annotations

CORE_ECOSYSTEM_LIST_VERSION = "2026-07-26"

# Canonical slugs (lowercase). Aliases map into these for matching.
CORE_ECOSYSTEMS: set[str] = {
    "eth",
    "base",
    "celo",
    "arbitrum",
    "optimism",
    "polygon",
}

CORE_ECOSYSTEM_ALIASES: dict[str, str] = {
    "ethereum": "eth",
    "matic": "polygon",
}


def normalize_core_slug(chain: str) -> str | None:
    """Return canonical core slug if chain is a core ecosystem, else None."""
    key = (chain or "").lower().strip()
    if key.endswith("-mainnet"):
        key = key[: -len("-mainnet")]
    if key in CORE_ECOSYSTEM_ALIASES:
        key = CORE_ECOSYSTEM_ALIASES[key]
    if key in CORE_ECOSYSTEMS:
        return key
    return None
