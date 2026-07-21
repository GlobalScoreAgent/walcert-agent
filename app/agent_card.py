"""Public agent card served at GET / (discovery JSON, bilingual eng/esp)."""

from __future__ import annotations

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


def build_agent_card(settings: Settings) -> dict[str, Any]:
    chain = f"eip155:{settings.celo_chain_id}"
    base = (settings.public_base_url or "").rstrip("/")
    agent_id = int(settings.agent_id)
    price = settings.x402_price if settings.x402_price.endswith("USDC") else f"{settings.x402_price} USDC"

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
                "note": {
                    "eng": (
                        "Full signed certificate with metrics, EIP-712 signature and "
                        "ERC-8004 on-chain anchor (giveFeedback)."
                    ),
                    "esp": (
                        "Certificado completo firmado con métricas, firma EIP-712 y "
                        "anclaje on-chain ERC-8004 (giveFeedback)."
                    ),
                },
            },
        },
        "endpoints": {
            "base_url": base or None,
            "health": "/health",
            "quota": "/v1/quota",
            "openapi": "/docs",
        },
        "identity": {
            "pay_to": settings.agent_wallet,
            "explorer": f"https://erc-8004.quicknode.com/agents/celo-mainnet/{agent_id}",
            "gsa": "https://globalscoreagent.com",
            "repo": "https://github.com/GlobalScoreAgent/walcert-agent",
        },
        "message": {
            "eng": "This URL hosts an ERC-8004 agent API, not a human dashboard.",
            "esp": "Esta URL aloja la API de un agente ERC-8004, no un dashboard humano.",
        },
    }
