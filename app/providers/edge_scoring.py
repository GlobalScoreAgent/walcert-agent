from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import ProviderError

EDGE_SLUGS = {
    "origins": "walcert-certificate-origins",
    "activity": "walcert-certificate-activity",
    "multichain": "walcert-certificate-multichain-v2",
    "multichain_v2": "walcert-certificate-multichain-v2",
    "portfolio": "walcert-certificate-portfolio",
}


class EdgeScoringClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def enabled(self) -> bool:
        return bool(
            self.settings.supabase_functions_url and self.settings.edge_shared_secret
        )

    async def score(
        self,
        certificate_type: str,
        wallet: str,
        analyzed_at: str,
        analysis: dict[str, Any],
        access_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise ProviderError(
                "edge",
                "EDGE_SHARED_SECRET / SUPABASE_FUNCTIONS_URL not configured",
            )
        slug = EDGE_SLUGS.get(certificate_type)
        if not slug:
            raise ProviderError("edge", f"unknown certificate type: {certificate_type}")

        base = self.settings.supabase_functions_url.rstrip("/")
        url = f"{base}/{slug}"
        headers = {
            "Authorization": f"Bearer {self.settings.edge_shared_secret}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "wallet": wallet.lower(),
            "analyzed_at": analyzed_at,
            "certificate_type": certificate_type,
            "payload": analysis,
        }
        if access_meta:
            body["_walcert_access"] = access_meta

        async with httpx.AsyncClient(
            timeout=max(120.0, self.settings.http_timeout_seconds),
            follow_redirects=True,
        ) as client:
            try:
                response = await client.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise ProviderError("edge", f"network error: {exc}") from exc

        if response.status_code == 401:
            raise ProviderError("edge", "unauthorized", status_code=401)
        if response.status_code >= 400:
            raise ProviderError(
                "edge",
                f"HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError("edge", "invalid JSON from edge scoring") from exc
