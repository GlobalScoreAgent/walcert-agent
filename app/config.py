from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
QUOTA_FILE = DATA_DIR / "quota_usage.json"

load_dotenv(ROOT_DIR / ".env")

# Well-known CEX / bridge / DEX funders (lowercase) for semicrude labeling.
KNOWN_LABELS: dict[str, tuple[str, str]] = {
    # (category, label)
    "0x28c6c06298d514db089934071355e5743bf21d60": ("cex", "Binance"),
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": ("cex", "Binance"),
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": ("cex", "Binance"),
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": ("cex", "Binance"),
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": ("cex", "Coinbase"),
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": ("cex", "Coinbase"),
    "0x503828976d22510aad84384440fe63dcbb73b7a1": ("cex", "Coinbase"),
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": ("cex", "Kraken"),
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": ("cex", "Kraken"),
    "0x6cc5f688a315f3dc28a7781717a9f41396704d0a": ("cex", "OKX"),
    "0x2faf487a4414fe77e2327f0bf4ae2a264a776ad2": ("cex", "FTX"),
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("other", "USDT"),
}

# Alchemy network slug -> chain metadata
ALCHEMY_NETWORK_META: dict[str, dict[str, int | str]] = {
    "celo-mainnet": {"chain_id": 42220, "name": "celo"},
    "bnb-mainnet": {"chain_id": 56, "name": "bsc"},
    "eth-mainnet": {"chain_id": 1, "name": "eth"},
    "base-mainnet": {"chain_id": 8453, "name": "base"},
    "arb-mainnet": {"chain_id": 42161, "name": "arbitrum"},
    "opt-mainnet": {"chain_id": 10, "name": "optimism"},
    "polygon-mainnet": {"chain_id": 137, "name": "polygon"},
}

# Chains accepted by Moralis getWalletActiveChains (mainnets). Celo is excluded.
_MORALIS_SUPPORTED = {
    "eth",
    "ethereum",
    "base",
    "arbitrum",
    "polygon",
    "optimism",
    "bsc",
    "avalanche",
    "fantom",
    "gnosis",
    "linea",
    "moonbeam",
    "moonriver",
}


class Settings:
    agent_id: int
    agent_wallet: str
    public_base_url: str
    alchemy_api_key: str
    alchemy_networks: list[str]
    alchemy_endpoints: list[dict[str, str | int]]
    moralis_api_key: str
    zerion_api_key: str
    cache_ttl_seconds: int
    http_timeout_seconds: float
    alchemy_cu_per_transfer_call: int
    moralis_cu_per_chain: int
    alchemy_monthly_limit_cu: int
    alchemy_daily_limit_cu: int | None
    moralis_daily_limit_cu: int
    zerion_daily_limit: int
    moralis_chains: list[str]
    celo_chain_id: int
    supabase_functions_url: str
    edge_shared_secret: str
    edge_scoring_enabled: bool
    x402_enabled: bool
    x402_network: str
    x402_facilitator_url: str
    x402_facilitator_api_key: str
    x402_facilitator_auth_header: str
    x402_pay_to: str
    x402_price: str
    payment_log_enabled: bool
    payment_log_slug: str

    def __init__(self) -> None:
        self.agent_id = int(os.getenv("AGENT_ID", "9696"))
        self.agent_wallet = os.getenv(
            "AGENT_WALLET", "0x2eFC66c0a78620Dd254443998BF2f11B685602E3"
        )
        self.public_base_url = os.getenv(
            "PUBLIC_BASE_URL", "http://127.0.0.1:8000"
        ).rstrip("/")
        self.alchemy_api_key = os.getenv("ALCHEMY_API_KEY", "")

        # Prefer ALCHEMY_NETWORKS=celo-mainnet,bnb-mainnet
        # Fallback: single ALCHEMY_NETWORK or default celo+bnb
        networks_raw = os.getenv("ALCHEMY_NETWORKS", "").strip()
        if networks_raw:
            self.alchemy_networks = [
                n.strip() for n in networks_raw.split(",") if n.strip()
            ]
        else:
            single = os.getenv("ALCHEMY_NETWORK", "").strip()
            if single:
                self.alchemy_networks = [single]
            else:
                self.alchemy_networks = ["celo-mainnet", "bnb-mainnet"]

        self.alchemy_endpoints = []
        if self.alchemy_api_key:
            for slug in self.alchemy_networks:
                meta = ALCHEMY_NETWORK_META.get(slug, {"chain_id": 0, "name": slug})
                self.alchemy_endpoints.append(
                    {
                        "network": slug,
                        "name": str(meta["name"]),
                        "chain_id": int(meta["chain_id"]),
                        "url": f"https://{slug}.g.alchemy.com/v2/{self.alchemy_api_key}",
                    }
                )

        # Optional full URL override replaces the list with a single endpoint
        explicit_url = os.getenv("ALCHEMY_HTTP_URL", "").strip()
        if explicit_url:
            self.alchemy_endpoints = [
                {
                    "network": "custom",
                    "name": "custom",
                    "chain_id": int(os.getenv("CELO_CHAIN_ID", "42220")),
                    "url": explicit_url,
                }
            ]

        self.moralis_api_key = os.getenv("MORALIS_API_KEY", "")
        self.zerion_api_key = os.getenv("ZERION_API_KEY", "")
        self.cache_ttl_seconds = int(os.getenv("CACHE_TTL_SECONDS", "600"))
        self.http_timeout_seconds = float(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
        self.alchemy_cu_per_transfer_call = int(
            os.getenv("ALCHEMY_CU_PER_TRANSFER_CALL", "120")
        )
        self.moralis_cu_per_chain = int(os.getenv("MORALIS_CU_PER_CHAIN", "50"))
        self.alchemy_monthly_limit_cu = int(
            os.getenv("ALCHEMY_MONTHLY_LIMIT_CU", "30000000")
        )
        daily_alchemy = os.getenv("ALCHEMY_DAILY_LIMIT_CU", "").strip()
        self.alchemy_daily_limit_cu = int(daily_alchemy) if daily_alchemy else None
        self.moralis_daily_limit_cu = int(
            os.getenv("MORALIS_DAILY_LIMIT_CU", "40000")
        )
        self.zerion_daily_limit = int(os.getenv("ZERION_DAILY_LIMIT", "2000"))
        chains_raw = os.getenv(
            "MORALIS_CHAINS",
            "eth,base,arbitrum,polygon,optimism,bsc",
        )
        self.moralis_chains = [
            c.strip()
            for c in chains_raw.split(",")
            if c.strip() and c.strip().lower() in _MORALIS_SUPPORTED
        ]
        if not self.moralis_chains:
            self.moralis_chains = ["eth", "base", "arbitrum", "bsc"]
        self.celo_chain_id = int(os.getenv("CELO_CHAIN_ID", "42220"))
        self.supabase_functions_url = os.getenv(
            "SUPABASE_FUNCTIONS_URL",
            "https://mezqyworblseixaypftg.supabase.co/functions/v1",
        ).rstrip("/")
        self.edge_shared_secret = os.getenv("EDGE_SHARED_SECRET", "").strip()
        self.edge_scoring_enabled = os.getenv(
            "EDGE_SCORING_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}

        # x402 paywall (protocolo estandar via facilitador de Celo).
        self.x402_enabled = os.getenv(
            "X402_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        # CAIP-2. El facilitador oficial api.x402.celo.org hoy solo soporta
        # eip155:42220 (Celo mainnet); Celo Sepolia no esta en /supported.
        self.x402_network = os.getenv("X402_NETWORK", "eip155:42220").strip()
        self.x402_facilitator_url = os.getenv(
            "X402_FACILITATOR_URL", "https://api.x402.celo.org"
        ).strip().rstrip("/")
        self.x402_facilitator_api_key = os.getenv(
            "X402_FACILITATOR_API_KEY", ""
        ).strip()
        self.x402_facilitator_auth_header = os.getenv(
            "X402_FACILITATOR_AUTH_HEADER", "X-API-Key"
        ).strip()
        self.x402_pay_to = os.getenv(
            "X402_PAY_TO", "0xF4D938200445B0Df0f028af6d90D016147AEd095"
        ).strip()
        self.x402_price = os.getenv("X402_PRICE", "$0.05").strip()

        # Registro de compras x402: el agente NO escribe en la BD. Arma la fila
        # y la envia a la Edge Function walcert-payment-log (reusa
        # SUPABASE_FUNCTIONS_URL + EDGE_SHARED_SECRET). No-op si falta config.
        self.payment_log_enabled = os.getenv(
            "PAYMENT_LOG_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.payment_log_slug = os.getenv(
            "PAYMENT_LOG_SLUG", "walcert-payment-log"
        ).strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
