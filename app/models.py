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
    "multichain": "goldrush",
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


class VerifyRequest(BaseModel):
    """Public verification input. Primary key is the on-chain anchor tx_hash."""

    tx_hash: str = Field(..., min_length=66, max_length=66)
    data_hash: str | None = None
    certificate_id: str | None = None

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, value: str) -> str:
        v = value.strip().lower()
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError("tx_hash must be a 0x-prefixed 32-byte hex string")
        try:
            int(v[2:], 16)
        except ValueError as exc:
            raise ValueError("tx_hash must be hex") from exc
        return v

    @field_validator("data_hash")
    @classmethod
    def validate_data_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        if not v:
            return None
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError("data_hash must be a 0x-prefixed 32-byte hex string")
        try:
            int(v[2:], 16)
        except ValueError as exc:
            raise ValueError("data_hash must be hex") from exc
        return v
