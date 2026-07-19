"""Verificabilidad on-chain de los certificados.

Dos capas, ambas ejecutadas en el agente (nunca en la Edge):

1. Firma EIP-712 de la wallet del agente sobre el `data_hash` del certificado
   (autenticidad instantanea, sin gas).
2. Anclaje on-chain por certificado via `giveFeedback` en el ERC-8004
   Reputation Registry de Celo, desde una wallet monitor dedicada (distinta al
   owner del agentId). El `feedbackHash` transporta el `data_hash` y el `value`
   transporta el monto pagado, de modo que `getSummary` expone a la vez el
   conteo de certificados y los ingresos acumulados.

Todo es sincrono (web3); `services.py` lo invoca dentro de un thread.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from hexbytes import HexBytes
from web3 import Web3

from app.config import get_settings

logger = logging.getLogger("walcert.onchain")

# --- Compatibilidad middleware POA para Web3.py v6 y v7 ---
try:  # v7
    from web3.middleware import ExtraDataToPOAMiddleware as _poa_middleware
except ImportError:  # pragma: no cover - v6
    try:
        from web3.middleware import geth_poa_middleware as _poa_middleware
    except ImportError:  # pragma: no cover
        _poa_middleware = None


# ABI minimo del Reputation Registry (solo lo que usamos).
REPUTATION_ABI = [
    {
        "name": "giveFeedback",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "value", "type": "int128"},
            {"name": "valueDecimals", "type": "uint8"},
            {"name": "tag1", "type": "string"},
            {"name": "tag2", "type": "string"},
            {"name": "endpoint", "type": "string"},
            {"name": "feedbackURI", "type": "string"},
            {"name": "feedbackHash", "type": "bytes32"},
        ],
        "outputs": [],
    },
    {
        "name": "NewFeedback",
        "type": "event",
        "anonymous": False,
        "inputs": [
            {"name": "agentId", "type": "uint256", "indexed": True},
            {"name": "clientAddress", "type": "address", "indexed": True},
            {"name": "feedbackIndex", "type": "uint64", "indexed": False},
            {"name": "value", "type": "int128", "indexed": False},
            {"name": "valueDecimals", "type": "uint8", "indexed": False},
            {"name": "indexedTag1", "type": "string", "indexed": True},
            {"name": "tag1", "type": "string", "indexed": False},
            {"name": "tag2", "type": "string", "indexed": False},
            {"name": "endpoint", "type": "string", "indexed": False},
            {"name": "feedbackURI", "type": "string", "indexed": False},
            {"name": "feedbackHash", "type": "bytes32", "indexed": False},
        ],
    },
]

EIP712_DOMAIN_NAME = "Walcert Certificate"
EIP712_DOMAIN_VERSION = "1"
FEEDBACK_TAG1 = "certificate_issued"

_w3: Web3 | None = None
_account = None
_contract = None


def _get_w3() -> Web3:
    global _w3
    if _w3 is None:
        settings = get_settings()
        w3 = Web3(Web3.HTTPProvider(settings.celo_rpc_url))
        if _poa_middleware is not None:
            try:
                w3.middleware_onion.inject(_poa_middleware, layer=0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("no se pudo inyectar POA middleware: %s", exc)
        _w3 = w3
    return _w3


def _get_account():
    global _account
    if _account is None:
        settings = get_settings()
        key = settings.agent_signer_key
        if not key:
            raise RuntimeError("AGENT_SIGNER_KEY no configurada")
        if key.startswith("0x"):
            key = key[2:]
        _account = Account.from_key(key)
    return _account


def _get_contract():
    global _contract
    if _contract is None:
        settings = get_settings()
        w3 = _get_w3()
        _contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.reputation_registry_address),
            abi=REPUTATION_ABI,
        )
    return _contract


def _typed_data(cert: dict[str, Any]) -> dict[str, Any]:
    """Construye el mensaje EIP-712 tipado para un certificado."""
    settings = get_settings()
    data_hash = str(cert.get("data_hash") or "")
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "Certificate": [
                {"name": "dataHash", "type": "bytes32"},
                {"name": "wallet", "type": "address"},
                {"name": "certType", "type": "string"},
                {"name": "certificateId", "type": "string"},
                {"name": "agentId", "type": "uint256"},
            ],
        },
        "primaryType": "Certificate",
        "domain": {
            "name": EIP712_DOMAIN_NAME,
            "version": EIP712_DOMAIN_VERSION,
            "chainId": settings.celo_chain_id,
        },
        "message": {
            "dataHash": HexBytes(data_hash),
            "wallet": Web3.to_checksum_address(str(cert.get("wallet"))),
            "certType": str(cert.get("type") or ""),
            "certificateId": str(cert.get("certificate_id") or ""),
            "agentId": int(settings.agent_id),
        },
    }


def sign_certificate(cert: dict[str, Any]) -> dict[str, Any]:
    """Firma EIP-712 del certificado con la wallet del agente."""
    account = _get_account()
    typed = _typed_data(cert)
    signable = encode_typed_data(full_message=typed)
    signed = account.sign_message(signable)
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    return {
        "scheme": "eip712",
        "signer": account.address,
        "signature": signature,
        "domain": typed["domain"],
        "primary_type": "Certificate",
    }


def _parse_amount(price_str: str) -> tuple[int, int]:
    """'$0.05' -> (5, 2). Devuelve (value, valueDecimals)."""
    cleaned = "".join(ch for ch in str(price_str) if ch.isdigit() or ch == ".")
    if not cleaned:
        return 0, 0
    try:
        dec = Decimal(cleaned)
    except InvalidOperation:
        return 0, 0
    exponent = -dec.as_tuple().exponent
    if exponent < 0:
        exponent = 0
    value = int(dec.scaleb(exponent))
    return value, exponent


def anchor_certificate(cert: dict[str, Any]) -> dict[str, Any]:
    """Ancla el certificado on-chain via giveFeedback en el Reputation Registry."""
    settings = get_settings()
    w3 = _get_w3()
    account = _get_account()
    contract = _get_contract()

    data_hash = str(cert.get("data_hash") or "")
    cert_type = str(cert.get("type") or "")
    feedback_hash = HexBytes(data_hash)
    if len(feedback_hash) != 32:
        return {"status": "failed", "error": f"data_hash no es bytes32: {data_hash!r}"}

    value, value_decimals = _parse_amount(settings.x402_price)
    endpoint = (
        f"{settings.public_base_url}/v1/certificates/{cert_type.lower()}"
        if cert_type
        else settings.public_base_url
    )

    try:
        nonce = w3.eth.get_transaction_count(account.address)
        fn = contract.functions.giveFeedback(
            int(settings.agent_id),
            int(value),
            int(value_decimals),
            FEEDBACK_TAG1,
            cert_type,
            endpoint,
            "",
            feedback_hash,
        )
        tx = fn.build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": settings.celo_chain_id,
                "gasPrice": w3.eth.gas_price,
            }
        )
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)

        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw)
        tx_hex = tx_hash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex

        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=settings.celo_confirmation_timeout
        )
        if receipt.status != 1:
            return {
                "status": "failed",
                "error": "transaction reverted",
                "tx_hash": tx_hex,
            }

        feedback_index = None
        try:
            events = contract.events.NewFeedback().process_receipt(receipt)
            if events:
                feedback_index = int(events[0]["args"]["feedbackIndex"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("no se pudo leer feedbackIndex: %s", exc)

        return {
            "status": "confirmed",
            "protocol": "erc8004-reputation",
            "method": "giveFeedback",
            "chain_id": settings.celo_chain_id,
            "contract": Web3.to_checksum_address(settings.reputation_registry_address),
            "agent_id": int(settings.agent_id),
            "monitor": account.address,
            "tx_hash": tx_hex,
            "block_number": int(receipt.blockNumber),
            "feedback_index": feedback_index,
            "value": int(value),
            "value_decimals": int(value_decimals),
            "tag1": FEEDBACK_TAG1,
            "tag2": cert_type,
            "feedback_hash": data_hash,
            "explorer_url": f"https://celoscan.io/tx/{tx_hex}",
            "anchored_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("anchor_certificate fallo: %s", exc)
        return {"status": "failed", "error": str(exc)}


def certify(cert: dict[str, Any]) -> dict[str, Any]:
    """Agrega `signature` (EIP-712) y `onchain` (giveFeedback) al certificado.

    Se ejecuta de forma sincrona; el llamador debe correrlo en un thread.
    Nunca lanza: si algo falla, se refleja en `onchain.status = "failed"`.
    """
    settings = get_settings()

    if settings.cert_signing_enabled:
        try:
            cert["signature"] = sign_certificate(cert)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sign_certificate fallo: %s", exc)
            cert["signature"] = {"scheme": "eip712", "error": str(exc)}

    if settings.onchain_anchor_enabled:
        cert["onchain"] = anchor_certificate(cert)

    return cert


__all__ = ["sign_certificate", "anchor_certificate", "certify"]
