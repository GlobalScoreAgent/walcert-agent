from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse

from app.certificate_verify import VerifyEdgeError, call_verify_edge
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.models import (
    CERTIFICATE_TYPES,
    PREVIEW_ALLOWED_TYPES,
    PROVIDER_BY_TYPE,
    CertificateRequest,
    CertificateUnavailable,
    VerifyRequest,
)
from app.providers.quota import get_quota
from app.rate_limit import check_preview_rate_limit, check_summit_rate_limit
from app.services import run_certificate, run_multichain_v2_summit

router = APIRouter()


def _public_verify_response(edge_body: dict) -> dict:
    """Project Edge payload to the public contract (no internal extras)."""
    cert = edge_body.get("certificate") or {}
    sig = edge_body.get("signature") or {}
    onchain = edge_body.get("onchain") or {}
    out: dict = {
        "valid": bool(edge_body.get("valid")),
        "source": edge_body.get("source") or "database + onchain",
    }
    reason = edge_body.get("reason")
    if reason:
        out["reason"] = reason
    if cert:
        out["certificate"] = {
            "certificate_id": cert.get("certificate_id"),
            "type": cert.get("type"),
            "grade": cert.get("grade"),
            "wallet": cert.get("wallet"),
            "data_hash": cert.get("data_hash"),
            "analyzed_at": cert.get("analyzed_at"),
        }
    if sig or edge_body.get("found"):
        out["signature"] = {
            "valid": bool(sig.get("valid")),
            "signer": sig.get("signer"),
        }
    if onchain or edge_body.get("found"):
        out["onchain"] = {
            "valid": bool(onchain.get("valid")),
            "tx_hash": onchain.get("tx_hash"),
            "contract": onchain.get("contract"),
            "tag1": onchain.get("tag1"),
            "tag2": onchain.get("tag2"),
            "celoscan": onchain.get("celoscan"),
        }
    return out


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": "walcert"}


@router.get("/v1/quota")
async def quota_snapshot() -> dict:
    return get_quota().snapshot()


@router.post("/v1/verify")
async def verify_certificate(request: Request):
    """Public hybrid verification: Edge does DB lookup + Celo + EIP-712."""
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"valid": False, "reason": "invalid_tx_hash"},
        )
    if not isinstance(raw, dict):
        return JSONResponse(
            status_code=400,
            content={"valid": False, "reason": "invalid_tx_hash"},
        )

    try:
        body = VerifyRequest.model_validate(raw)
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"valid": False, "reason": "invalid_tx_hash"},
        )

    payload: dict = {"tx_hash": body.tx_hash}
    if body.data_hash:
        payload["data_hash"] = body.data_hash
    if body.certificate_id:
        payload["certificate_id"] = body.certificate_id.strip()

    try:
        status, edge_body = await call_verify_edge(payload)
    except VerifyEdgeError:
        return JSONResponse(
            status_code=502,
            content={
                "valid": False,
                "reason": "verification_error",
                "source": "edge",
            },
        )

    reason = edge_body.get("reason")

    if status == 400 or reason == "invalid_tx_hash":
        return JSONResponse(
            status_code=400,
            content={
                "valid": False,
                "reason": "invalid_tx_hash",
            },
        )

    if status == 502 or reason == "verification_error":
        return JSONResponse(
            status_code=502,
            content={
                "valid": False,
                "reason": "verification_error",
                "source": edge_body.get("source") or "edge",
            },
        )

    if not edge_body.get("found") or reason == "not_found":
        return JSONResponse(
            status_code=404,
            content={
                "valid": False,
                "reason": "not_found",
            },
        )

    # found=true with valid true/false → always 200 with structured checks
    return JSONResponse(status_code=200, content=_public_verify_response(edge_body))


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
    request: Request,
    body: CertificateRequest,
    certificate_type: str = Path(..., pattern="^(origins|activity|multichain|portfolio)$"),
):
    """Endpoint sin paywall: grade-only preview (Alchemy types + IP rate limit)."""
    if certificate_type not in CERTIFICATE_TYPES:
        raise HTTPException(status_code=404, detail="Unknown certificate type")

    allowed, retry_after = check_preview_rate_limit(request)
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "available": False,
                "status": "rate_limit_exceeded",
                "message": {
                    "eng": "Too many preview requests from this IP. Please try again later.",
                    "esp": "Demasiadas solicitudes de preview desde esta IP. Intenta de nuevo más tarde.",
                },
            },
        )

    if certificate_type not in PREVIEW_ALLOWED_TYPES:
        return JSONResponse(
            status_code=403,
            content={
                "available": False,
                "status": "preview_not_allowed",
                "certificate_type": certificate_type,
                "message": {
                    "eng": "Free preview is only available for origins and activity certificates. Use POST /v1/certificates/{type} (x402 payment) for multichain and portfolio.",
                    "esp": "El preview gratuito solo está disponible para los certificados origins y activity. Usa POST /v1/certificates/{type} (pago x402) para multichain y portfolio.",
                },
            },
        )

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
    request: Request,
    body: CertificateRequest,
    response: Response,
    certificate_type: str = Path(..., pattern="^(origins|activity|multichain|portfolio)$"),
):
    if certificate_type not in CERTIFICATE_TYPES:
        raise HTTPException(status_code=404, detail="Unknown certificate type")

    from app.internal_access import get_access

    if get_access().is_summit:
        allowed, retry_after = check_summit_rate_limit(request, body.wallet_address)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "available": False,
                    "status": "rate_limit_exceeded",
                    "message": {
                        "eng": "Too many Summit certificate requests for this wallet or IP. Please try again later.",
                        "esp": "Demasiadas solicitudes Summit para esta wallet o IP. Intenta de nuevo más tarde.",
                    },
                },
            )

    try:
        result = await run_certificate(
            certificate_type, body.wallet_address, certify=True
        )
        cert = result.get("certificate") or {}
        from app.bnb_receipt import attach_receipt_if_bnb, payment_context_from_request
        from app.onchain_log import schedule_onchain_log

        net, payer = payment_context_from_request(request)
        if cert:
            attach_receipt_if_bnb(
                cert,
                network=net,
                payer=payer,
                fallback_type=certificate_type,
            )
            result["certificate"] = cert
            if cert.get("receipt"):
                schedule_onchain_log(
                    cert.get("certificate_id"),
                    cert.get("onchain"),
                    cert.get("signature"),
                    receipt_bnb=cert.get("receipt"),
                )
        # Correlacion para el registro de compra x402 (lo lee PaymentLogMiddleware).
        # x402 preserva estos headers al recomponer la respuesta tras el settle.
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


@router.post("/v1/summit/certificates/multichain-v2")
async def create_multichain_v2_summit(
    request: Request,
    body: CertificateRequest,
    response: Response,
):
    """Summit-only Multichain v2 (GoldRush). Not in agent card / x402."""
    from app.internal_access import get_access

    if not get_access().is_summit:
        return JSONResponse(
            status_code=403,
            content={
                "available": False,
                "status": "forbidden",
                "reason": "summit_only",
                "message": {
                    "eng": "This endpoint is only available for Blockchain Summit (BSG2026).",
                    "esp": "Este endpoint solo está disponible para Blockchain Summit (BSG2026).",
                },
            },
        )

    allowed, retry_after = check_summit_rate_limit(request, body.wallet_address)
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "available": False,
                "status": "rate_limit_exceeded",
                "message": {
                    "eng": "Too many Summit certificate requests for this wallet or IP. Please try again later.",
                    "esp": "Demasiadas solicitudes Summit para esta wallet o IP. Intenta de nuevo más tarde.",
                },
            },
        )

    certificate_type = "multichain_v2"
    try:
        result = await run_multichain_v2_summit(body.wallet_address)
        cert = result.get("certificate") or {}
        onchain = cert.get("onchain") or {}
        response.headers["X-Walcert-Certificate-Id"] = str(
            cert.get("certificate_id") or ""
        )
        response.headers["X-Walcert-Certificate-Type"] = certificate_type
        response.headers["X-Walcert-Grade"] = str(cert.get("grade") or "")
        response.headers["X-Walcert-Wallet"] = body.wallet_address
        response.headers["X-Walcert-Tx-Hash"] = str(onchain.get("tx_hash") or "")
        return result
    except MissingCredentials as exc:
        payload = CertificateUnavailable(
            certificate_type="multichain",  # type: ignore[arg-type]
            reason="provider_not_configured",
            provider=exc.provider,
            retry_after=None,
        )
        return JSONResponse(status_code=503, content=payload.model_dump())
    except ProviderError as exc:
        if exc.message == "summit_only":
            return JSONResponse(
                status_code=403,
                content={
                    "available": False,
                    "status": "forbidden",
                    "reason": "summit_only",
                },
            )
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
                "provider": exc.provider or "goldrush",
                "error": exc.message,
            },
        )
