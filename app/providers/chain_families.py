"""Chain → ecosystem family map for Multichain v2.1 (shared with Edge)."""

from __future__ import annotations

# Prefix / name fragment → family. Longer prefixes checked first via sorted length.
_FAMILY_RULES: list[tuple[str, str]] = [
    ("arbitrum", "ethereum"),
    ("optimism", "ethereum"),
    ("base", "ethereum"),
    ("zksync", "ethereum"),
    ("zk-sync", "ethereum"),
    ("scroll", "ethereum"),
    ("linea", "ethereum"),
    ("zora", "ethereum"),
    ("blast", "ethereum"),
    ("mode", "ethereum"),
    ("eth", "ethereum"),
    ("ethereum", "ethereum"),
    ("matic", "polygon"),
    ("polygon", "polygon"),
    ("bsc", "bnb"),
    ("binance", "bnb"),
    ("bnb", "bnb"),
    ("avalanche", "avalanche"),
    ("avax", "avalanche"),
    ("celo", "celo"),
    ("gnosis", "gnosis"),
    ("xdai", "gnosis"),
    ("fantom", "fantom"),
    ("ftm", "fantom"),
    ("moonbeam", "polkadot"),
    ("moonriver", "polkadot"),
    ("solana", "solana"),
    ("cosmos", "cosmos"),
    ("osmosis", "cosmos"),
    ("near", "near"),
    ("tron", "tron"),
]


def ecosystem_family_from_chain_name(name: str | None) -> str | None:
    """Map GoldRush chain name to a stable ecosystem family. None if empty."""
    raw = str(name or "").strip().lower()
    if not raw:
        return None
    # Prefer longest matching prefix/substring key
    for key, family in sorted(_FAMILY_RULES, key=lambda x: -len(x[0])):
        if raw == key or raw.startswith(key + "-") or f"-{key}-" in raw or raw.endswith("-" + key):
            return family
        if key in raw.split("-"):
            return family
    # Unknown mainnet: one family per chain slug (not raw category_label noise)
    slug = raw.replace("_", "-")
    return f"other:{slug}"
