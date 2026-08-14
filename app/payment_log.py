"""Registro de compras x402.

El pago x402 se liquida en el middleware de FastAPI: verify -> ruta -> settle,
y el settlement (tx_hash, payer, monto) queda en el header `PAYMENT-RESPONSE`
de la respuesta. Este modulo agrega un middleware que, por fuera del de x402,
captura esa info y la envia a la Edge Function `walcert-payment-log` (autenticada
con el `EDGE_SHARED_SECRET`). La service role key NUNCA vive en el agente: solo
en la Edge, que es la unica que escribe en `walcert.x402_payments`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings, get_settings
from app.payments import facilitator_url_for_network

logger = logging.getLogger("walcert.payment_log")

_PROTECTED_PREFIX = "/v1/certificates/"

# Referencias vivas a las tareas fire-and-forget (evita GC prematuro).
_tasks: set[asyncio.Task] = set()


def _dig(obj: Any, *path: str) -> Any:
    """Navega dicts anidados de forma defensiva."""
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def _dump(model: Any) -> Any:
    """Serializa un modelo pydantic (o dict) a algo JSON-able, o None."""
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        try:
            return model.model_dump(mode="json", by_alias=True)
        except Exception:  # noqa: BLE001
            try:
                return model.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                return None
    if isinstance(model, (dict, list, str, int, float, bool)):
        return model
    return None


class PaymentLogMiddleware(BaseHTTPMiddleware):
    """Captura el settlement x402 y lo envia (best-effort) a la Edge."""

    def __init__(self, app, settings: Settings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()
        self._url = (
            f"{self.settings.supabase_functions_url.rstrip('/')}/"
            f"{self.settings.payment_log_slug}"
        )

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        try:
            if (
                request.method == "POST"
                and request.url.path.startswith(_PROTECTED_PREFIX)
            ):
                self._maybe_log(request, response)
        except Exception as exc:  # noqa: BLE001 - el logueo nunca rompe la respuesta
            logger.warning("payment log skipped: %s", exc)

        return response

    def _maybe_log(self, request, response) -> None:
        from x402.http import PAYMENT_RESPONSE_HEADER, decode_payment_response_header

        settle_header = response.headers.get(PAYMENT_RESPONSE_HEADER)
        if not settle_header:
            # No hubo settlement (p.ej. 402 sin pago): no es una compra.
            return

        try:
            settle = decode_payment_response_header(settle_header)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot decode PAYMENT-RESPONSE: %s", exc)
            return

        reqs = getattr(request.state, "payment_requirements", None)
        payload = getattr(request.state, "payment_payload", None)
        reqs_dump = _dump(reqs)
        payload_dump = _dump(payload)

        cert_id = response.headers.get("X-Walcert-Certificate-Id") or None
        cert_type = response.headers.get("X-Walcert-Certificate-Type") or None
        wallet = response.headers.get("X-Walcert-Wallet") or None

        network = (
            getattr(settle, "network", None)
            or (reqs_dump or {}).get("network")
            or self.settings.x402_network
        )
        amount = getattr(settle, "amount", None) or (reqs_dump or {}).get("amount")
        asset = (reqs_dump or {}).get("asset")
        pay_to = (reqs_dump or {}).get("payTo") or (reqs_dump or {}).get("pay_to") or (
            self.settings.x402_pay_to
        )
        scheme = (reqs_dump or {}).get("scheme") or "exact"
        nonce = (
            _dig(payload_dump, "payload", "authorization", "nonce")
            or _dig(payload_dump, "payload", "nonce")
        )

        row = {
            "certificate_id": cert_id,
            "certificate_type": cert_type,
            "wallet": wallet,
            "network": network,
            "scheme": scheme,
            "asset": asset,
            "pay_to": pay_to,
            "payer": getattr(settle, "payer", None),
            "amount": str(amount) if amount is not None else None,
            "price": self.settings.x402_price,
            "nonce": str(nonce) if nonce is not None else None,
            "tx_hash": getattr(settle, "transaction", None) or None,
            "success": bool(getattr(settle, "success", False)),
            "facilitator": facilitator_url_for_network(
                self.settings, str(network) if network else None
            ),
            "settle_response": _dump(settle),
            "payment_requirements": reqs_dump,
            "payment_payload": payload_dump,
        }

        task = asyncio.create_task(self._post_payment(row))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    async def _post_payment(self, row: dict) -> None:
        headers = {
            "Authorization": f"Bearer {self.settings.edge_shared_secret}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.http_timeout_seconds
            ) as client:
                resp = await client.post(self._url, headers=headers, json=row)
            if resp.status_code >= 400:
                logger.warning(
                    "payment log edge %s: HTTP %s %s",
                    self._url,
                    resp.status_code,
                    resp.text[:200],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("payment log post failed: %s", exc)


def install_payment_log(app) -> bool:
    """Monta el middleware de registro de pagos. No-op si falta config."""
    settings = get_settings()
    if not settings.payment_log_enabled:
        logger.info("payment log deshabilitado (PAYMENT_LOG_ENABLED=false).")
        return False
    if not (settings.supabase_functions_url and settings.edge_shared_secret):
        logger.info(
            "payment log no montado: falta SUPABASE_FUNCTIONS_URL/EDGE_SHARED_SECRET."
        )
        return False

    app.add_middleware(PaymentLogMiddleware, settings=settings)
    logger.info(
        "payment log montado: edge=%s/%s",
        settings.supabase_functions_url,
        settings.payment_log_slug,
    )
    return True
