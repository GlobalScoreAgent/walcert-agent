from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CertificateType = Literal["origins", "activity", "multichain", "portfolio"]

CERTIFICATE_TYPES: tuple[str, ...] = (
    "origins",
    "activity",
    "multichain",
    "portfolio",
)

# Free preview is limited to Alchemy-backed types (quota protection).
PREVIEW_ALLOWED_TYPES: tuple[str, ...] = ("origins", "activity")

PROVIDER_BY_TYPE: dict[str, str] = {
    "origins": "alchemy",
    "activity": "alchemy",
    "multichain": "moralis",
    "portfolio": "zerion",
}


class CertificateRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42)

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet(cls, value: str) -> str:
        v = value.strip()
        if not v.startswith("0x") or len(v) != 42:
            raise ValueError("wallet_address must be a 0x-prefixed 20-byte address")
        try:
            int(v[2:], 16)
        except ValueError as exc:
            raise ValueError("wallet_address must be hex") from exc
        return v.lower()


class CertificateUnavailable(BaseModel):
    available: bool = False
    status: str = "certificate_unavailable"
    message: str = "Certificate not available"
    certificate_type: CertificateType
    reason: str
    provider: str
    retry_after: str | None = None


class CertificateSuccess(BaseModel):
    available: bool = True
    status: str = "ok"
    mode: str = "hot"
    certificate_type: CertificateType
    provider: str | None = None
    analysis: dict[str, Any]
    certificate: dict[str, Any] | None = None


class ScoringError(BaseModel):
    available: bool = False
    status: str = "scoring_error"
    message: str = "Certificate scoring failed"
    certificate_type: CertificateType
    reason: str = "scoring_error"
    provider: str = "edge"
    error: str | None = None
