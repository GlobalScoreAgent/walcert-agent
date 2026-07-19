from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Response
from fastapi.responses import JSONResponse

from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.models import (
    CERTIFICATE_TYPES,
    PROVIDER_BY_TYPE,
    CertificateRequest,
    CertificateUnavailable,
)
from app.providers.quota import get_quota
from app.services import run_certificate

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "walcert"}


@router.get("/v1/quota")
async def quota_snapshot() -> dict:
    return get_quota().snapshot()


def _preview_from_result(certificate_type: str, wallet: str, result: dict) -> dict:
    """Resumen gratuito (grade + label) sin exponer el detalle ni el analysis."""
    cert = result.get("certificate") or {}
    return {
        "preview": True,
        "certificate_type": certificate_type,
        "wallet": wallet,
        "grade": cert.get("grade"),
        "grade_label": cert.get("grade_label"),
        "analyzed_at": cert.get("analyzed_at") or (result.get("analysis") or {}).get("analyzed_at"),
        "note": {
            "eng": "Free preview. The full certificate (metrics + signature) requires an x402 payment at POST /v1/certificates/{type}.",
            "esp": "Preview gratuito. El certificado completo (metricas + firma) requiere pago x402 en POST /v1/certificates/{type}.",
        },
    }


@router.post("/v1/preview/{certificate_type}")
async def preview_certificate(
    body: CertificateRequest,
    certificate_type: str = Path(..., pattern="^(origins|activity|multichain|portfolio)$"),
):
    """Endpoint sin paywall: devuelve solo el grado, para el dashboard/demo."""
    if certificate_type not in CERTIFICATE_TYPES:
        raise HTTPException(status_code=404, detail="Unknown certificate type")

    try:
        result = await run_certificate(certificate_type, body.wallet_address)
        return _preview_from_result(certificate_type, body.wallet_address, result)
    except QuotaExceeded as exc:
        payload = CertificateUnavailable(
            certificate_type=certificate_type,  # type: ignore[arg-type]
            reason="provider_quota_exceeded",
            provider=exc.provider,
            retry_after=exc.retry_after,
        )
        return JSONResponse(status_code=503, content=payload.model_dump())
    except MissingCredentials as exc:
        payload = CertificateUnavailable(
            certificate_type=certificate_type,  # type: ignore[arg-type]
            reason="provider_not_configured",
            provider=exc.provider,
            retry_after=None,
        )
        return JSONResponse(status_code=503, content=payload.model_dump())
    except ProviderError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "available": False,
                "status": "provider_error",
                "certificate_type": certificate_type,
                "reason": "provider_error",
                "provider": exc.provider or PROVIDER_BY_TYPE.get(certificate_type),
                "error": exc.message,
            },
        )


@router.post("/v1/certificates/{certificate_type}")
async def create_certificate(
    body: CertificateRequest,
    response: Response,
    certificate_type: str = Path(..., pattern="^(origins|activity|multichain|portfolio)$"),
):
    if certificate_type not in CERTIFICATE_TYPES:
        raise HTTPException(status_code=404, detail="Unknown certificate type")

    try:
        result = await run_certificate(
            certificate_type, body.wallet_address, certify=True
        )
        # Correlacion para el registro de compra x402 (lo lee PaymentLogMiddleware).
        # x402 preserva estos headers al recomponer la respuesta tras el settle.
        cert = result.get("certificate") or {}
        onchain = cert.get("onchain") or {}
        response.headers["X-Walcert-Certificate-Id"] = str(cert.get("certificate_id") or "")
        response.headers["X-Walcert-Certificate-Type"] = certificate_type
        response.headers["X-Walcert-Grade"] = str(cert.get("grade") or "")
        response.headers["X-Walcert-Wallet"] = body.wallet_address
        response.headers["X-Walcert-Tx-Hash"] = str(onchain.get("tx_hash") or "")
        return result
    except QuotaExceeded as exc:
        payload = CertificateUnavailable(
            certificate_type=certificate_type,  # type: ignore[arg-type]
            reason="provider_quota_exceeded",
            provider=exc.provider,
            retry_after=exc.retry_after,
        )
        return JSONResponse(status_code=503, content=payload.model_dump())
    except MissingCredentials as exc:
        payload = CertificateUnavailable(
            certificate_type=certificate_type,  # type: ignore[arg-type]
            reason="provider_not_configured",
            provider=exc.provider,
            retry_after=None,
        )
        return JSONResponse(status_code=503, content=payload.model_dump())
    except ProviderError as exc:
        if exc.provider == "edge":
            return JSONResponse(
                status_code=502,
                content={
                    "available": False,
                    "status": "scoring_error",
                    "message": "Certificate scoring failed",
                    "certificate_type": certificate_type,
                    "reason": "scoring_error",
                    "provider": "edge",
                    "error": exc.message,
                },
            )
        return JSONResponse(
            status_code=502,
            content={
                "available": False,
                "status": "provider_error",
                "message": "Certificate not available",
                "certificate_type": certificate_type,
                "reason": "provider_error",
                "provider": exc.provider or PROVIDER_BY_TYPE.get(certificate_type),
                "error": exc.message,
            },
        )
