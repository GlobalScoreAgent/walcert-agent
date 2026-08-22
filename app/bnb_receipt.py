"""BNB receipt NFT voucher (EIP-712) bound to certificate data_hash.

The bytes32 `data_hash` is the stable id shared with Celo giveFeedback and the
future TermiX AACP deliveryHash. Celo/Base payments never require a claim.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from hexbytes import HexBytes
from web3 import Web3

from app.config import get_settings

logger = logging.getLogger("walcert.bnb_receipt")

EIP712_NAME = "Walcert Receipt"
EIP712_VERSION = "1"
CLAIM_DEADLINE_SECONDS = 7 * 24 * 3600
BNB_CAIP = "eip155:56"


def is_bnb_network(network: str | None) -> bool:
    net = (network or "").strip().lower().replace("eip155:", "eip155:")
    return net in {BNB_CAIP, "bsc", "eip155:56"} or net.endswith(":56") or "eip155:56" in net


def _bytes32(data_hash: str) -> bytes:
    raw = HexBytes(data_hash)
    if len(raw) != 32:
        raise ValueError(f"data_hash must be bytes32, got {data_hash!r}")
    return bytes(raw)


def build_claim_voucher(
    *,
    data_hash: str,
    cert_type: str,
    payer: str,
    contract: str | None = None,
    deadline: int | None = None,
) -> dict[str, Any] | None:
    """Sign an EIP-712 Claim for the payer. None if BNB receipt is not configured."""
    settings = get_settings()
    contract = (contract or getattr(settings, "bnb_receipt_contract", "") or "").strip()
    if not getattr(settings, "bnb_receipt_enabled", True) or not contract:
        return None
    key = settings.agent_signer_key
    if not key:
        logger.warning("BNB receipt: AGENT_SIGNER_KEY missing; voucher omitted")
        return None
    if key.startswith("0x"):
        key = key[2:]

    try:
        payer_cs = Web3.to_checksum_address(payer)
        contract_cs = Web3.to_checksum_address(contract)
        dh = _bytes32(data_hash)
    except Exception as exc:  # noqa: BLE001
        logger.warning("BNB receipt voucher skipped: %s", exc)
        return None

    if deadline is None:
        deadline = int(time.time()) + CLAIM_DEADLINE_SECONDS

    typed = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Claim": [
                {"name": "dataHash", "type": "bytes32"},
                {"name": "certType", "type": "string"},
                {"name": "payer", "type": "address"},
                {"name": "deadline", "type": "uint256"},
            ],
        },
        "primaryType": "Claim",
        "domain": {
            "name": EIP712_NAME,
            "version": EIP712_VERSION,
            "chainId": getattr(settings, "bnb_chain_id", 56),
            "verifyingContract": contract_cs,
        },
        "message": {
            "dataHash": dh,
            "certType": cert_type,
            "payer": payer_cs,
            "deadline": deadline,
        },
    }
    account = Account.from_key(key)
    encoded = encode_typed_data(full_message=typed)
    signed = account.sign_message(encoded)
    sig = signed.signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    return {
        "kind": "walcert_bnb_receipt_claim",
        "chain_id": getattr(settings, "bnb_chain_id", 56),
        "contract": contract_cs,
        "delivery_hash": "0x" + dh.hex(),
        "data_hash": "0x" + dh.hex(),
        "cert_type": cert_type,
        "payer": payer_cs,
        "deadline": deadline,
        "issuer": account.address,
        "signature": sig,
        "claim": {
            "function": "claim(bytes32,string,address,uint256,bytes)",
            "args": ["0x" + dh.hex(), cert_type, payer_cs, deadline, sig],
        },
        "explorer_hint": f"https://bscscan.com/address/{contract_cs}",
    }


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json", by_alias=True)
        except Exception:  # noqa: BLE001
            try:
                return obj.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                return {}
    return {}


def _extract_network_payer(obj: Any) -> tuple[str | None, str | None]:
    """Pull CAIP-2 network + payer from a payment payload / requirements object."""
    data = _as_dict(obj)
    if not data:
        return None, None
    accepted = data.get("accepted") or data.get("paymentRequirements") or {}
    if not isinstance(accepted, dict):
        accepted = _as_dict(accepted)
    network = (
        data.get("network")
        or accepted.get("network")
        or (getattr(obj, "network", None) if obj is not None else None)
    )
    if hasattr(obj, "get_network"):
        try:
            network = network or obj.get_network()
        except Exception:  # noqa: BLE001
            pass
    inner = data.get("payload") if isinstance(data.get("payload"), dict) else data
    payer = None
    for key in ("from", "from_", "payer", "fromAddress"):
        if inner.get(key):
            payer = inner.get(key)
            break
    for nested_name in (
        "authorization",
        "permit2Authorization",
        "permit2_authorization",
        "permit2Authorization",
    ):
        nested = inner.get(nested_name)
        if not isinstance(nested, dict):
            nested = _as_dict(nested)
        if not nested:
            continue
        payer = (
            payer
            or nested.get("from")
            or nested.get("from_")
            or nested.get("fromAddress")
            or nested.get("from_address")
        )
    return (
        str(network) if network else None,
        str(payer) if payer else None,
    )


def _payment_from_headers(request: Any) -> Any | None:
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    names = (
        "PAYMENT-SIGNATURE",
        "PAYMENT-SIGNATURE",
        "X-PAYMENT",
        "payment-signature",
        "x-payment",
    )
    raw = None
    for name in names:
        try:
            raw = headers.get(name)
        except Exception:  # noqa: BLE001
            raw = None
        if raw:
            break
    if not raw:
        return None
    try:
        from x402.http import decode_payment_signature_header

        return decode_payment_signature_header(raw)
    except Exception:  # noqa: BLE001
        logger.warning("BNB receipt: could not decode PAYMENT-SIGNATURE header")
        return None


def payment_context_from_request(request: Any) -> tuple[str | None, str | None]:
    """Best-effort (network, payer) from request.state or PAYMENT-SIGNATURE header."""
    state = getattr(request, "state", None)
    net, payer = _extract_network_payer(
        getattr(state, "payment_payload", None) if state is not None else None
    )
    if not net:
        n2, _ = _extract_network_payer(
            getattr(state, "payment_requirements", None) if state is not None else None
        )
        net = net or n2
    if not net or not payer:
        n3, p3 = _extract_network_payer(_payment_from_headers(request))
        net = net or n3
        payer = payer or p3
    return net, payer


def attach_receipt_if_bnb(
    cert: dict[str, Any],
    *,
    network: str | None,
    payer: str | None,
    fallback_type: str | None = None,
) -> dict[str, Any]:
    """Add certificate['receipt'] when the x402 settle was on BNB. Idempotent."""
    if not is_bnb_network(network) or not payer:
        logger.info(
            "BNB receipt skipped (network=%s payer=%s)", network, bool(payer)
        )
        return cert
    if cert.get("receipt"):
        return cert
    data_hash = str(cert.get("data_hash") or "")
    cert_type = str(cert.get("type") or fallback_type or "")
    if not data_hash or not cert_type:
        logger.warning("BNB receipt skipped: missing data_hash or type")
        return cert
    voucher = build_claim_voucher(
        data_hash=data_hash, cert_type=cert_type, payer=payer
    )
    if voucher:
        cert["receipt"] = voucher
    return cert
