"""Public agent card served at GET / (discovery JSON, bilingual eng/esp)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models import CERTIFICATE_TYPES, PREVIEW_ALLOWED_TYPES

GSA_PROVIDER_ENG = (
    "Powered by Global Score Agent. We provide specialized scoring for autonomous "
    "agents with daily indices. Contact us or visit our website: globalscoreagent.com"
)
GSA_PROVIDER_ESP = (
    "Powered by Global Score Agent. Ofrecemos scoring especializado para agentes "
    "autónomos con índices diarios. Contactanos o visitá nuestro sitio: globalscoreagent.com"
)

# Canonical Concordium / A2A card (exact bytes hashed on-chain as metadata_hash).
_REPO_ROOT = Path(__file__).resolve().parent.parent
CONCORDIUM_AGENT_CARD_PATH = _REPO_ROOT / "agent" / "concordium-agent-card.json"


def concordium_agent_card_path() -> Path:
    """Absolute path to the Concordium Agent Card JSON file."""
    return CONCORDIUM_AGENT_CARD_PATH


def concordium_agent_card_sha256_hex() -> str:
    """SHA-256 hex of the raw file bytes (for CIS-8004 metadata_hash)."""
    data = CONCORDIUM_AGENT_CARD_PATH.read_bytes()
    return hashlib.sha256(data).hexdigest()


def build_agent_card(settings: Settings) -> dict[str, Any]:
    chain = f"eip155:{settings.celo_chain_id}"
    base = (settings.public_base_url or "").rstrip("/")
    agent_id = int(settings.agent_id)
    price = settings.x402_price if settings.x402_price.endswith("USDC") else f"{settings.x402_price} USDC"
    concordium_card_url = f"{base}/agent-card.json" if base else "/agent-card.json"

    return {
        "agent": "Walcert Agent",
        "product_of": "Global Score Agent",
        "provider": {
            "eng": GSA_PROVIDER_ENG,
            "esp": GSA_PROVIDER_ESP,
        },
        "agent_id": agent_id,
        "chain": chain,
        "description": {
            "eng": (
                "ERC-8004 agent on Celo that issues A–F wallet-maturity certificates "
                "via real-time analysis (hot-analysis). Agent-to-agent HTTP JSON; "
                "full certificates settle with x402."
            ),
            "esp": (
                "Agente ERC-8004 en Celo que emite certificados de madurez de wallets "
                "con nota A–F mediante análisis en tiempo real (hot-analysis). "
                "Consumo agente-a-agente por HTTP JSON; certificados completos con pago x402."
            ),
        },
        "capabilities": {
            "certificates": list(CERTIFICATE_TYPES),
            "grades": "A-F",
            "preview": {
                "path": "/v1/preview/{type}",
                "types_allowed": list(PREVIEW_ALLOWED_TYPES),
                "auth": "none",
                "note": {
                    "eng": (
                        "Free preview returns A–F grade only for origins and activity "
                        "(Alchemy). Rate-limited by IP. multichain and portfolio require "
                        "the paid endpoint."
                    ),
                    "esp": (
                        "El preview gratuito solo devuelve la nota A–F para origins y "
                        "activity (Alchemy). Tiene rate limit por IP. multichain y "
                        "portfolio requieren el endpoint de pago."
                    ),
                },
            },
            "full_certificate": {
                "path": "/v1/certificates/{type}",
                "auth": "x402",
                "price": price,
                "network": chain,
                "networks": (
                    [chain, settings.x402_base_network]
                    if settings.x402_base_ready
                    else [chain]
                ),
                "facilitators": {
                    chain: settings.x402_facilitator_url,
                    **(
                        {settings.x402_base_network: settings.x402_base_facilitator_url}
                        if settings.x402_base_ready
                        else {}
                    ),
                },
                "note": {
                    "eng": (
                        "Full signed certificate with metrics, EIP-712 signature and "
                        "ERC-8004 on-chain anchor (giveFeedback). x402: 0.05 USDC on "
                        "Celo mainnet and, when enabled, Base mainnet (same payTo)."
                    ),
                    "esp": (
                        "Certificado completo firmado con métricas, firma EIP-712 y "
                        "anclaje on-chain ERC-8004 (giveFeedback). x402: 0,05 USDC en "
                        "Celo mainnet y, si está habilitado, Base mainnet (mismo payTo)."
                    ),
                },
            },
            "verify": {
                "path": "/v1/verify",
                "auth": "none",
                "method": "POST",
                "input": {
                    "tx_hash": "required",
                    "data_hash": "optional",
                    "certificate_id": "optional",
                },
                "note": {
                    "eng": (
                        "Public hybrid verification: looks up the certificate by "
                        "on-chain tx_hash, then confirms NewFeedback on Celo and "
                        "EIP-712 signature (logic runs in Supabase Edge)."
                    ),
                    "esp": (
                        "Verificación pública híbrida: busca el certificado por "
                        "tx_hash on-chain y confirma NewFeedback en Celo y la firma "
                        "EIP-712 (la lógica corre en Supabase Edge)."
                    ),
                },
            },
        },
        "endpoints": {
            "base_url": base or None,
            "health": "/health",
            "quota": "/v1/quota",
            "verify": "/v1/verify",
            "agent_card_concordium": "/agent-card.json",
            "openapi": "/docs",
        },
        "identity": {
            "pay_to": settings.agent_wallet,
            "explorer": f"https://erc-8004.quicknode.com/agents/celo-mainnet/{agent_id}",
            "gsa": "https://globalscoreagent.com",
            "repo": "https://github.com/GlobalScoreAgent/walcert-agent",
            "concordium_agent_card": concordium_card_url,
            "owner": "0x475F589BD4bFe82b333b8006dcc278f393b8E124",
        },
        "message": {
            "eng": "This URL hosts an ERC-8004 agent API, not a human dashboard.",
            "esp": "Esta URL aloja la API de un agente ERC-8004, no un dashboard humano.",
        },
    }
