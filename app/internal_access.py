"""Canal interno (marketplaces) + canal Summit BSG2026 (bypass x402 + atribución).

Contrato marketplace:
  Authorization: Bearer <WALCERT_INTERNAL_API_KEY>
  X-Walcert-Marketplace: virtuals_acp
  X-Walcert-Access-Channel: internal   # opcional si ya va Bearer+marketplace

Contrato Summit (key dedicada; caduca 1 ago 2026):
  Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
  X-Walcert-Marketplace: bsg2026
"""

from __future__ import annotations

import logging
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings, get_settings

logger = logging.getLogger("walcert.internal_access")

HEADER_MARKETPLACE = "x-walcert-marketplace"
HEADER_ACCESS_CHANNEL = "x-walcert-access-channel"

ALLOWED_MARKETPLACES_DEFAULT = (
    "virtuals_acp",
    "olas",
    "circle",
    "x402_bazaar",
    "agentverse",
)

# Errors that map to HTTP 403 (Summit window closed / kill switch).
_SUMMIT_FORBIDDEN = frozenset({"summit_disabled", "summit_expired"})


@dataclass(frozen=True, slots=True)
class AccessContext:
    access_channel: str  # direct | internal | summit
    marketplace: str | None
    billing: str  # x402 | marketplace | free

    @property
    def is_internal(self) -> bool:
        return self.access_channel == "internal"

    @property
    def is_summit(self) -> bool:
        return self.access_channel == "summit"

    @property
    def skips_x402(self) -> bool:
        return self.access_channel in {"internal", "summit"}


_access_ctx: ContextVar[AccessContext | None] = ContextVar(
    "walcert_access", default=None
)


def get_access() -> AccessContext:
    ctx = _access_ctx.get()
    if ctx is None:
        return AccessContext(
            access_channel="direct", marketplace=None, billing="x402"
        )
    return ctx


def set_access(ctx: AccessContext):
    return _access_ctx.set(ctx)


def reset_access(token) -> None:
    _access_ctx.reset(token)


def access_meta_for_edge(ctx: AccessContext | None = None) -> dict[str, Any]:
    c = ctx or get_access()
    return {
        "access_channel": c.access_channel,
        "marketplace": c.marketplace,
        "billing": c.billing,
    }


def _headers_map(scope: Scope) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        out[key.decode("latin-1").lower()] = value.decode("latin-1")
    return out


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _claims_internal(headers: dict[str, str]) -> bool:
    channel = (headers.get(HEADER_ACCESS_CHANNEL) or "").strip().lower()
    marketplace = (headers.get(HEADER_MARKETPLACE) or "").strip()
    return channel == "internal" or bool(marketplace)


def _token_matches(expected: str, token: str | None) -> bool:
    if not expected or not token:
        return False
    if len(expected) != len(token):
        # compare_digest requires equal length; avoid leaking via exception.
        secrets.compare_digest(expected, expected)
        return False
    return secrets.compare_digest(expected, token)


def _resolve_summit(
    headers: dict[str, str],
    token: str | None,
    *,
    settings: Settings,
) -> tuple[AccessContext | None, str | None]:
    """Returns (ctx, err) if Bearer matches summit key; else (None, None) to continue."""
    expected = (settings.walcert_summit_api_key or "").strip()
    if not expected or not _token_matches(expected, token):
        return None, None

    if not settings.walcert_summit_enabled:
        return None, "summit_disabled"

    now = datetime.now(timezone.utc)
    if now >= settings.walcert_summit_expires_at:
        return None, "summit_expired"

    marketplace = (headers.get(HEADER_MARKETPLACE) or "").strip().lower()
    required = (settings.walcert_summit_marketplace or "bsg2026").lower()
    if not marketplace:
        return None, "missing_marketplace"
    if marketplace != required:
        return None, "marketplace_not_allowed"

    return (
        AccessContext(
            access_channel="summit",
            marketplace=required,
            billing="free",
        ),
        None,
    )


def resolve_access(
    headers: dict[str, str],
    *,
    settings: Settings | None = None,
    default_billing: str = "x402",
) -> tuple[AccessContext | None, str | None]:
    """Resuelve el contexto de acceso.

    Returns:
      (context, error_code). error_code set → caller should respond 401/403.
      context None + error None → use default direct (no internal/summit claim).
    """
    settings = settings or get_settings()
    token = _bearer_token(headers.get("authorization"))

    summit_ctx, summit_err = _resolve_summit(headers, token, settings=settings)
    if summit_err is not None:
        return None, summit_err
    if summit_ctx is not None:
        return summit_ctx, None

    claims = _claims_internal(headers)
    if not claims:
        return None, None

    # Explicit internal claim: must authenticate.
    expected = (settings.walcert_internal_api_key or "").strip()
    if not expected:
        logger.warning("internal claim without WALCERT_INTERNAL_API_KEY configured")
        return None, "internal_auth_not_configured"

    if not _token_matches(expected, token):
        return None, "invalid_internal_credentials"

    marketplace = (headers.get(HEADER_MARKETPLACE) or "").strip().lower()
    if not marketplace:
        return None, "missing_marketplace"
    if marketplace not in settings.walcert_internal_marketplaces:
        return None, "marketplace_not_allowed"
    # Summit marketplace must not be claimed via the internal marketplace key.
    summit_slug = (settings.walcert_summit_marketplace or "bsg2026").lower()
    if marketplace == summit_slug:
        return None, "marketplace_not_allowed"

    billing = "marketplace" if default_billing == "x402" else default_billing
    return (
        AccessContext(
            access_channel="internal",
            marketplace=marketplace,
            billing=billing,
        ),
        None,
    )


def is_certificate_post(scope: Scope) -> bool:
    if scope.get("method") != "POST":
        return False
    path = scope.get("path") or ""
    return path.startswith("/v1/certificates/")


def is_preview_post(scope: Scope) -> bool:
    if scope.get("method") != "POST":
        return False
    path = scope.get("path") or ""
    return path.startswith("/v1/preview/")


async def _send_json(
    send: Send, status: int, body: dict[str, Any]
) -> None:
    import json

    raw = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


def _auth_error_payload(err: str) -> tuple[int, dict[str, Any]]:
    if err in _SUMMIT_FORBIDDEN:
        return 403, {
            "available": False,
            "status": "forbidden",
            "reason": err,
            "message": {
                "eng": "Summit access channel is disabled or expired.",
                "esp": "El canal Summit está deshabilitado o ha caducado.",
            },
        }
    return 401, {
        "available": False,
        "status": "unauthorized",
        "reason": err,
        "message": {
            "eng": "Invalid internal or Summit credentials.",
            "esp": "Credenciales internas o Summit inválidas.",
        },
    }


class AccessContextMiddleware:
    """ASGI: atribución + 401/403 en claims internos/Summit inválidos (antes de x402)."""

    def __init__(self, app: ASGIApp, settings: Settings | None = None):
        self.app = app
        self.settings = settings or get_settings()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers_map(scope)
        default_billing = "free" if is_preview_post(scope) else "x402"
        ctx, err = resolve_access(
            headers, settings=self.settings, default_billing=default_billing
        )

        if err is not None:
            status, body = _auth_error_payload(err)
            await _send_json(send, status, body)
            return

        if ctx is None:
            billing = "free" if is_preview_post(scope) else "x402"
            ctx = AccessContext(
                access_channel="direct", marketplace=None, billing=billing
            )
        elif is_preview_post(scope):
            ctx = AccessContext(
                access_channel=ctx.access_channel,
                marketplace=ctx.marketplace,
                billing="free",
            )

        token = set_access(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_access(token)


def install_access_context(app, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    app.add_middleware(AccessContextMiddleware, settings=cfg)
    logger.info(
        "access context middleware montado (internal marketplaces=%s, summit_expires=%s)",
        sorted(cfg.walcert_internal_marketplaces),
        cfg.walcert_summit_expires_at.isoformat(),
    )


__all__ = [
    "AccessContext",
    "AccessContextMiddleware",
    "HEADER_ACCESS_CHANNEL",
    "HEADER_MARKETPLACE",
    "ALLOWED_MARKETPLACES_DEFAULT",
    "access_meta_for_edge",
    "get_access",
    "install_access_context",
    "is_certificate_post",
    "resolve_access",
    "set_access",
    "reset_access",
]
