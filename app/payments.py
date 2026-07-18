"""Integracion x402 (protocolo estandar) para el agente.

Track 2 de la hackathon: los pagos se liquidan via el facilitador oficial de
Celo (`x402.celo.org`) usando USDC gasless (EIP-3009). Celo no viene en el
registro `NETWORK_CONFIGS` de la libreria x402, asi que inyectamos su config de
red (direccion USDC + dominio EIP-712) en tiempo de arranque.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.models import CERTIFICATE_TYPES

logger = logging.getLogger("walcert.x402")

# Config de red de Celo (no incluida por defecto en x402). name/version fueron
# verificados on-chain contra los contratos USDC (EIP-712 domain).
CELO_NETWORK_CONFIGS: dict[str, dict] = {
    "eip155:42220": {
        "chain_id": 42220,
        "default_asset": {
            "address": "0xcebA9300f2b948710d2653dD7B07f33A8B32118C",
            "name": "USDC",
            "version": "2",
            "decimals": 6,
        },
    },
    "eip155:11142220": {
        "chain_id": 11142220,
        "default_asset": {
            "address": "0x01C5C0122039549AD1493B8220cABEdD739BC44E",
            "name": "USDC",
            "version": "2",
            "decimals": 6,
        },
    },
}


def _register_celo_networks() -> None:
    """Inyecta la config de red de Celo en el registro de x402 (idempotente)."""
    from x402.mechanisms.evm import constants as evm_constants

    for network, cfg in CELO_NETWORK_CONFIGS.items():
        if network not in evm_constants.NETWORK_CONFIGS:
            evm_constants.NETWORK_CONFIGS[network] = cfg


def _build_auth_provider(settings: Settings):
    """AuthProvider para el API key del facilitador (p. ej. x402.celo.org)."""
    if not settings.x402_facilitator_api_key:
        return None
    from x402.http import CreateHeadersAuthProvider

    header = {settings.x402_facilitator_auth_header: settings.x402_facilitator_api_key}

    def _create_headers() -> dict[str, dict[str, str]]:
        return {
            "verify": header,
            "settle": header,
            "supported": header,
            "bazaar": header,
        }

    return CreateHeadersAuthProvider(_create_headers)


def install_x402(app) -> bool:
    """Monta el paywall x402 sobre los endpoints /v1/certificates/*.

    Devuelve True si quedo instalado. No-op (False) si esta deshabilitado o si
    falta configuracion critica.
    """
    settings = Settings()
    if not settings.x402_enabled:
        logger.info("x402 deshabilitado (X402_ENABLED=false); paywall no montado.")
        return False

    try:
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.http.types import RouteConfig
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        logger.error("x402 habilitado pero el paquete no esta instalado: %s", exc)
        return False

    _register_celo_networks()

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(
            url=settings.x402_facilitator_url,
            auth_provider=_build_auth_provider(settings),
        )
    )
    server = x402ResourceServer(facilitator)
    server.register(settings.x402_network, ExactEvmServerScheme())

    routes: dict[str, RouteConfig] = {}
    for cert_type in CERTIFICATE_TYPES:
        routes[f"POST /v1/certificates/{cert_type}"] = RouteConfig(
            accepts=[
                PaymentOption(
                    scheme="exact",
                    pay_to=settings.x402_pay_to,
                    price=settings.x402_price,
                    network=settings.x402_network,
                )
            ],
            description=f"Walcert {cert_type} certificate (A-F, hot-analysis).",
            mime_type="application/json",
        )

    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
    logger.info(
        "x402 montado: red=%s, precio=%s, payTo=%s, facilitador=%s",
        settings.x402_network,
        settings.x402_price,
        settings.x402_pay_to,
        settings.x402_facilitator_url,
    )
    return True
