"""Verificador de certificados Walcert (firma EIP-712 + anclaje ERC-8004).

Uso:
    python scripts/verify_certificate.py <ruta_al_certificado.json>
    cat cert.json | python scripts/verify_certificate.py -

Comprueba, de forma independiente:
  1. Firma EIP-712: recupera el firmante y lo compara con `signature.signer`.
  2. Anclaje on-chain: en el Reputation Registry de Celo, confirma el evento
     `NewFeedback` de la tx anclada y que `feedbackHash == data_hash`.
  3. (Best-effort) recomputa el SHA-256 del `base` y lo compara con `data_hash`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data
from hexbytes import HexBytes
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.onchain import (  # noqa: E402
    EIP712_DOMAIN_NAME,
    EIP712_DOMAIN_VERSION,
    REPUTATION_ABI,
)

load_dotenv(".env")

OK = "[OK]"
FAIL = "[FAIL]"
INFO = "[*]"

DEFAULT_RPC = os.getenv("CELO_RPC_URL", "https://forno.celo.org").rstrip("/")
DEFAULT_REGISTRY = os.getenv(
    "REPUTATION_REGISTRY_ADDRESS", "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
)

try:  # POA middleware (Celo), compat v6/v7
    from web3.middleware import ExtraDataToPOAMiddleware as _poa
except ImportError:  # pragma: no cover
    try:
        from web3.middleware import geth_poa_middleware as _poa
    except ImportError:  # pragma: no cover
        _poa = None


def _load_certificate(arg: str) -> dict[str, Any]:
    if arg == "-":
        return json.loads(sys.stdin.read())
    with open(arg, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    # Acepta tanto el certificado directo como {"certificate": {...}}.
    if isinstance(data, dict) and "certificate" in data and "data_hash" not in data:
        return data["certificate"]
    return data


def _typed_data(cert: dict[str, Any]) -> dict[str, Any]:
    issuer = cert.get("issuer") or {}
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
            "chainId": int(cert.get("chain_id") or 42220),
        },
        "message": {
            "dataHash": HexBytes(str(cert.get("data_hash") or "")),
            "wallet": Web3.to_checksum_address(str(cert.get("wallet"))),
            "certType": str(cert.get("type") or ""),
            "certificateId": str(cert.get("certificate_id") or ""),
            "agentId": int(issuer.get("agent_id") or 0),
        },
    }


def verify_signature(cert: dict[str, Any]) -> bool:
    sig = cert.get("signature") or {}
    signer = sig.get("signer")
    signature = sig.get("signature")
    if not signer or not signature:
        print(f"{FAIL} Firma: falta signature.signer o signature")
        return False
    try:
        signable = encode_typed_data(full_message=_typed_data(cert))
        recovered = Account.recover_message(signable, signature=HexBytes(signature))
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} Firma: no se pudo recuperar el firmante: {exc}")
        return False
    if recovered.lower() == str(signer).lower():
        print(f"{OK} Firma EIP-712 valida. Firmante: {recovered}")
        return True
    print(f"{FAIL} Firma: recuperado {recovered} != declarado {signer}")
    return False


def verify_onchain(cert: dict[str, Any]) -> bool:
    onchain = cert.get("onchain") or {}
    tx_hash = onchain.get("tx_hash")
    data_hash = str(cert.get("data_hash") or "")
    if not tx_hash:
        print(f"{FAIL} On-chain: el certificado no tiene onchain.tx_hash")
        return False

    registry = onchain.get("contract") or DEFAULT_REGISTRY
    w3 = Web3(Web3.HTTPProvider(DEFAULT_RPC))
    if _poa is not None:
        try:
            w3.middleware_onion.inject(_poa, layer=0)
        except Exception:  # noqa: BLE001
            pass
    if not w3.is_connected():
        print(f"{FAIL} On-chain: no hay conexion RPC ({DEFAULT_RPC})")
        return False

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(registry), abi=REPUTATION_ABI
    )
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as exc:  # noqa: BLE001
        print(f"{FAIL} On-chain: no se encontro la tx {tx_hash}: {exc}")
        return False

    if receipt.status != 1:
        print(f"{FAIL} On-chain: la tx {tx_hash} revirtio")
        return False

    events = contract.events.NewFeedback().process_receipt(receipt)
    want = HexBytes(data_hash)
    for ev in events:
        args = ev["args"]
        if HexBytes(args["feedbackHash"]) == want:
            print(
                f"{OK} Anclaje ERC-8004 confirmado. "
                f"agentId={args['agentId']} clientAddress={args['clientAddress']} "
                f"feedbackIndex={args['feedbackIndex']} tag1={args['tag1']} "
                f"tag2={args['tag2']} value={args['value']} vd={args['valueDecimals']}"
            )
            print(f"{INFO} tx: https://celoscan.io/tx/{tx_hash}")
            return True

    print(
        f"{FAIL} On-chain: la tx no contiene un NewFeedback con "
        f"feedbackHash == data_hash ({data_hash})"
    )
    return False


def verify_hash(cert: dict[str, Any]) -> bool:
    """Best-effort: recomputa SHA-256 del `base` (sin campos agregados)."""
    base = {k: v for k, v in cert.items() if k not in ("data_hash", "signature", "onchain")}
    canonical = json.dumps(base, separators=(",", ":"), ensure_ascii=False)
    recomputed = "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    declared = str(cert.get("data_hash") or "")
    if recomputed == declared:
        print(f"{OK} data_hash recomputado coincide (SHA-256 del base)")
        return True
    print(
        f"{INFO} data_hash recomputado != declarado (puede deberse a orden de "
        f"claves/serializacion; no invalida firma ni anclaje).\n"
        f"      declarado : {declared}\n"
        f"      recomputado: {recomputed}"
    )
    return False


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/verify_certificate.py <cert.json|->")
        return 2
    cert = _load_certificate(sys.argv[1])

    print(f"{INFO} certificate_id: {cert.get('certificate_id')}")
    print(f"{INFO} type: {cert.get('type')}  grade: {cert.get('grade')}")
    print(f"{INFO} data_hash: {cert.get('data_hash')}")
    print("-" * 60)

    sig_ok = verify_signature(cert)
    onchain_ok = verify_onchain(cert)
    verify_hash(cert)  # informativo, no bloquea

    print("-" * 60)
    if sig_ok and onchain_ok:
        print(f"{OK} Certificado VERIFICADO (firma + anclaje on-chain).")
        return 0
    print(f"{FAIL} Verificacion incompleta (revisa los mensajes anteriores).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
