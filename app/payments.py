"""Integracion x402 (protocolo estandar) para el agente.

Pagos en Celo (facilitador oficial `x402.celo.org`, Track 2) y opcionalmente
en Base (facilitador CDP). Celo no viene en `NETWORK_CONFIGS` de la libreria
x402, asi que inyectamos su config de red (USDC + dominio EIP-712) al arranque.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.models import CERTIFICATE_TYPES, PROVIDER_BY_TYPE

logger = logging.getLogger("walcert.x402")

BNB_NETWORK_CONFIGS: dict[str, dict] = {
    "eip155:56": {
        "chain_id": 56,
        "default_asset": {
            "address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            "name": "USD Coin",
            "version": "2",
            "decimals": 18,
            "asset_transfer_method": "permit2",
        },
    },
}


def _register_bnb_networks(usdc: str | None = None) -> None:
    """Inyecta BSC Permit2 (18 dec) en el registro x402 (idempotente)."""
    from x402.mechanisms.evm import constants as evm_constants

    cfg = BNB_NETWORK_CONFIGS["eip155:56"]
    if usdc:
        asset = dict(cfg["default_asset"])
        asset["address"] = usdc
        cfg = {"chain_id": 56, "default_asset": asset}
    current = evm_constants.NETWORK_CONFIGS.get("eip155:56")
    if not current or current.get("default_asset", {}).get("decimals") != 18:
        evm_constants.NETWORK_CONFIGS["eip155:56"] = cfg


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
    """AuthProvider para el API key del facilitador Celo (x402.celo.org)."""
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


def facilitator_url_for_network(settings: Settings, network: str | None) -> str:
    """URL del facilitador que liquido, segun CAIP-2 de la requirements."""
    net = (network or "").strip().lower()
    base_net = (settings.x402_base_network or "").strip().lower()
    bnb_net = (getattr(settings, "x402_bnb_network", None) or "").strip().lower()
    if net and (net == base_net or net.endswith(":8453") or "8453" in net):
        return settings.x402_base_facilitator_url
    if net and (
        net == bnb_net or net.endswith(":56") or net == "bsc" or "eip155:56" in net
    ):
        return getattr(
            settings, "x402_bnb_facilitator_url", settings.x402_facilitator_url
        )
    return settings.x402_facilitator_url


def _cdp_facilitator_client(settings: Settings):
    """HTTPFacilitatorClient autenticado contra CDP (JWT Ed25519)."""
    import asyncio as _asyncio

    from x402.http import CreateHeadersAuthProvider, FacilitatorConfig, HTTPFacilitatorClient

    orig_run = _asyncio.run
    try:
        from cdp.x402 import create_facilitator_config
    finally:
        _asyncio.run = orig_run

    cdp_cfg = create_facilitator_config(
        api_key_id=settings.coinbase_api_key_base,
        api_key_secret=settings.coinbase_secret_base,
    )
    url = cdp_cfg.get("url") or settings.x402_base_facilitator_url
    create_headers = cdp_cfg.get("create_headers")
    kwargs: dict[str, Any] = {"url": url}
    if create_headers is not None:
        try:
            kwargs["auth_provider"] = CreateHeadersAuthProvider(create_headers)
            return HTTPFacilitatorClient(FacilitatorConfig(**kwargs))
        except TypeError:
            kwargs.pop("auth_provider", None)
            kwargs["create_headers"] = create_headers
            try:
                return HTTPFacilitatorClient(FacilitatorConfig(**kwargs))
            except TypeError:
                return HTTPFacilitatorClient(cdp_cfg)
    return HTTPFacilitatorClient(FacilitatorConfig(url=url))


# Descriptions for the 402 `resource.description` / CDP Bazaar listing (≤500 chars).
BAZAAR_DESCRIPTIONS: dict[str, str] = {
    "origins": (
        "Before hiring or paying an ERC-8004 agent, grade the controlling "
        "wallet's funding origins (CEX, bridge, mixer, organic) A-F. POST "
        "wallet_address; signed certificate + Celo on-chain anchor. $0.05 USDC."
    ),
    "activity": (
        "Grade 15-day wallet activity (counterparties, HHI, velocity, bot-like) "
        "A-F before you transact. POST wallet_address; signed certificate. $0.05 USDC."
    ),
    "multichain": (
        "Grade a wallet's chain footprint, longevity and sampled tx intensity A-F "
        "across EVM networks. POST wallet_address; signed certificate. $0.05 USDC."
    ),
    "portfolio": (
        "Grade wallet portfolio quality (usable vs spam/dust, concentration, "
        "tiers) A-F. POST wallet_address; signed certificate. $0.05 USDC."
    ),
}

_EXAMPLE_WALLET = "0x2eFC66c0a78620Dd254443998BF2f11B685602E3"


def _bnb_payment_option(settings: Settings):
    from x402.http import PaymentOption

    kwargs = dict(
        scheme="exact",
        pay_to=settings.x402_bnb_pay_to,
        price=settings.x402_price,
        network=settings.x402_bnb_network,
    )
    extra = {"assetTransferMethod": "permit2"}
    try:
        return PaymentOption(**kwargs, extra=extra)
    except TypeError:
        try:
            return PaymentOption(**kwargs, extra=extra)
        except TypeError:
            return PaymentOption(**kwargs)


def _payment_accepts(
    settings: Settings, *, include_base: bool, include_bnb: bool = False
) -> list[Any]:
    """PaymentOption list. Base first when on (CDP Bazaar reads [0]); BNB last."""
    from x402.http import PaymentOption

    celo = PaymentOption(
        scheme="exact",
        pay_to=settings.x402_pay_to,
        price=settings.x402_price,
        network=settings.x402_network,
    )
    options: list[Any] = []
    if include_base:
        options.append(
            PaymentOption(
                scheme="exact",
                pay_to=settings.x402_base_pay_to,
                price=settings.x402_price,
                network=settings.x402_base_network,
            )
        )
    options.append(celo)
    if include_bnb:
        options.append(_bnb_payment_option(settings))
    return options


def _bazaar_output_example(cert_type: str) -> dict[str, Any]:
    """Reduced envelope for Bazaar — no analysis.inflows."""
    return {
        "available": True,
        "status": "ok",
        "mode": "hot",
        "certificate_type": cert_type,
        "provider": PROVIDER_BY_TYPE.get(cert_type, "alchemy"),
        "certificate": {
            "type": cert_type.upper(),
            "grade": "B",
            "grade_label": {"eng": "Good", "esp": "Bueno"},
            "summary": {
                "eng": "Wallet maturity certificate (A-F).",
                "esp": "Certificado de madurez de wallet (A-F).",
            },
            "data_hash": "0x…",
            "signature": {"scheme": "eip712", "signer": "0xE7e9…"},
            "onchain": {"status": "confirmed", "chain_id": 42220, "tx_hash": "0x…"},
        },
    }


def _bazaar_extensions(cert_type: str) -> dict[str, Any]:
    from x402.extensions.bazaar.resource_service import (
        OutputConfig,
        declare_discovery_extension,
    )

    return declare_discovery_extension(
        input={"wallet_address": _EXAMPLE_WALLET},
        input_schema={
            "type": "object",
            "properties": {
                "wallet_address": {
                    "type": "string",
                    "description": "EVM wallet address (0x-prefixed, 42 chars)",
                }
            },
            "required": ["wallet_address"],
        },
        body_type="json",
        output=OutputConfig(example=_bazaar_output_example(cert_type)),
    )


def _certificate_route_config(cert_type: str, accepts: list[Any], *, bazaar: bool) -> Any:
    from x402.http.types import RouteConfig

    description = BAZAAR_DESCRIPTIONS.get(
        cert_type, f"Walcert {cert_type} certificate (A-F, hot-analysis)."
    )
    kwargs: dict[str, Any] = {
        "accepts": accepts,
        "description": description,
        "mime_type": "application/json",
    }
    if bazaar:
        kwargs["extensions"] = _bazaar_extensions(cert_type)
    return RouteConfig(**kwargs)


class _SkipX402IfInternalASGI:
    """Envuelve PaymentMiddlewareASGI: canal interno no paga x402."""

    def __init__(self, app, *, routes, server):
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI

        self.app = app
        self.payment = PaymentMiddlewareASGI(app, routes=routes, server=server)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            from app.internal_access import get_access, is_certificate_post

            if is_certificate_post(scope) and get_access().skips_x402:
                await self.app(scope, receive, send)
                return
        await self.payment(scope, receive, send)


def install_x402(app) -> bool:
    """Monta el paywall x402 sobre los endpoints /v1/certificates/*.

    Devuelve True si quedo instalado. No-op (False) si esta deshabilitado o si
    falta configuracion critica. Requests con auth interna valida saltan el paywall.
    """
    settings = Settings()
    if not settings.x402_enabled:
        logger.info("x402 deshabilitado (X402_ENABLED=false); paywall no montado.")
        return False

    try:
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        logger.error("x402 habilitado pero el paquete no esta instalado: %s", exc)
        return False

    _register_celo_networks()
    if settings.x402_bnb_enabled:
        _register_bnb_networks(settings.x402_bnb_usdc)

    celo_client = HTTPFacilitatorClient(
        FacilitatorConfig(
            url=settings.x402_facilitator_url,
            auth_provider=_build_auth_provider(settings),
        )
    )
    clients: dict[str, Any] = {settings.x402_network: celo_client}

    if settings.x402_base_ready:
        try:
            base_client = _cdp_facilitator_client(settings)
            clients[settings.x402_base_network] = base_client
            logger.info(
                "x402 Base habilitado: red=%s facilitador=%s payTo=%s",
                settings.x402_base_network,
                settings.x402_base_facilitator_url,
                settings.x402_base_pay_to,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("x402 Base no se pudo montar (%s); se sigue solo Celo.", exc)
    elif settings.x402_base_enabled:
        logger.warning(
            "x402 Base pedido (X402_BASE_ENABLED) pero faltan "
            "COINBASE_API_KEY_BASE / COINBASE_SECRET_BASE; solo Celo."
        )

    include_bnb = False
    if settings.x402_bnb_enabled:
        try:
            from x402.http import FacilitatorConfig, HTTPFacilitatorClient

            bnb_client = HTTPFacilitatorClient(
                FacilitatorConfig(url=settings.x402_bnb_facilitator_url)
            )
            clients[settings.x402_bnb_network] = bnb_client
            include_bnb = True
            logger.info(
                "x402 BNB habilitado: red=%s facilitador=%s payTo=%s permit2",
                settings.x402_bnb_network,
                settings.x402_bnb_facilitator_url,
                settings.x402_bnb_pay_to,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("x402 BNB no se pudo montar (%s); Celo/Base siguen.", exc)
            include_bnb = False

    # Native multi-client: initialize() llama get_supported() en cada uno y
    # enruta verify/settle por red. Un solo wrapper solo veia Celo /supported
    # y el 402 de Base reventaba (RouteConfigurationError).
    server = x402ResourceServer(list(clients.values()))
    server.register(settings.x402_network, ExactEvmServerScheme())
    if settings.x402_base_network in clients and settings.x402_base_network != settings.x402_network:
        server.register(settings.x402_base_network, ExactEvmServerScheme())
    if include_bnb and settings.x402_bnb_network not in (
        settings.x402_network,
        settings.x402_base_network,
    ):
        server.register(settings.x402_bnb_network, ExactEvmServerScheme())

    include_base = (
        settings.x402_base_network in clients
        and settings.x402_base_network != settings.x402_network
    )
    if include_base:
        try:
            from x402.extensions.bazaar.server import bazaar_resource_server_extension

            server.register_extension(bazaar_resource_server_extension)
        except Exception as exc:  # noqa: BLE001
            logger.error("Bazaar extension no se pudo registrar (%s); 402 sin discovery.", exc)
            include_base_bazaar = False
        else:
            include_base_bazaar = True
    else:
        include_base_bazaar = False

    accepts = _payment_accepts(
        settings, include_base=include_base, include_bnb=include_bnb
    )

    routes: dict[str, Any] = {}
    for cert_type in CERTIFICATE_TYPES:
        routes[f"POST /v1/certificates/{cert_type}"] = _certificate_route_config(
            cert_type, accepts, bazaar=include_base_bazaar
        )

    app.add_middleware(_SkipX402IfInternalASGI, routes=routes, server=server)
    logger.info(
        "x402 montado (bypass interno/summit): red=%s extra=%s bnb=%s bazaar=%s precio=%s payTo=%s facilitador=%s",
        settings.x402_network,
        settings.x402_base_network if include_base else None,
        settings.x402_bnb_network if include_bnb else None,
        include_base_bazaar,
        settings.x402_price,
        settings.x402_pay_to,
        settings.x402_facilitator_url,
    )
    return True
