"""Persistencia del bloque on-chain de un certificado en Supabase.

El agente NUNCA escribe en la BD: arma el payload y lo envia a la Edge Function
`walcert-certificate-onchain` (autenticada con el `EDGE_SHARED_SECRET`), que es
la unica con service role y hace el UPDATE sobre `walcert.certificate_requests`
por `certificate_id`. Best-effort: se dispara en background tras entregar la
respuesta y nunca rompe ni bloquea el request.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("walcert.onchain_log")

# Referencias vivas a las tareas fire-and-forget (evita GC prematuro).
_tasks: set[asyncio.Task] = set()


async def _post(url: str, secret: str, timeout: float, payload: dict[str, Any]) -> None:
    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "onchain log edge %s: HTTP %s %s",
                url,
                resp.status_code,
                resp.text[:200],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("onchain log post failed: %s", exc)


def schedule_onchain_log(
    certificate_id: str | None,
    onchain: dict[str, Any] | None,
    signature: dict[str, Any] | None,
) -> None:
    """Dispara (fire-and-forget) la persistencia del bloque onchain en Supabase."""
    settings = get_settings()
    if not settings.onchain_log_enabled:
        return
    if not (settings.supabase_functions_url and settings.edge_shared_secret):
        return
    if not certificate_id or onchain is None:
        return

    url = f"{settings.supabase_functions_url.rstrip('/')}/{settings.onchain_log_slug}"
    payload: dict[str, Any] = {
        "certificate_id": certificate_id,
        "onchain": onchain,
        "signature": signature,
        "tx_hash": onchain.get("tx_hash") if isinstance(onchain, dict) else None,
    }

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("onchain log: sin event loop; se omite")
        return

    task = loop.create_task(
        _post(url, settings.edge_shared_secret, settings.http_timeout_seconds, payload)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


__all__ = ["schedule_onchain_log"]
