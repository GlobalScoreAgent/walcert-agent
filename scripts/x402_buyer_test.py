"""Cliente de prueba x402: paga un certificado y valida el flujo completo.

Flujo:
  1. POST /v1/certificates/{type} sin pago -> espera 402 + payment-required.
  2. Firma la autorizacion EIP-3009 (gasless) con la wallet compradora.
  3. Reintenta con el header X-PAYMENT -> el server verifica y liquida via
     el facilitador de esa red (Celo o Base) -> 200 + certificado A-F.

Uso (PowerShell):
    $env:X402_BUYER_PRIVATE_KEY = "<llave_privada del comprador con USDC>"
    # Celo (default): $env:X402_NETWORK = "eip155:42220"
    # Base:           $env:X402_NETWORK = "eip155:8453"
    # BNB Permit2:   $env:X402_NETWORK = "eip155:56"
    python scripts/x402_buyer_test.py [cert_type] [target_wallet]

Requisitos:
  - Wallet compradora con >= precio en USDC en la red elegida.
  - Server con X402_ENABLED=true. Celo: X402_FACILITATOR_API_KEY.
    Base: COINBASE_API_KEY_BASE + COINBASE_SECRET_BASE.
    BNB: X402_BNB_ENABLED=true (Permit2; primer approve al contrato Permit2).
"""

from __future__ import annotations

import json
import os
import sys

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

from x402.client import x402ClientSync
from x402.http import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    decode_payment_required_header,
    decode_payment_response_header,
    x402HTTPClientSync,
)
from x402.mechanisms.evm.constants import NETWORK_CONFIGS
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSignerWithRPC

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8011").rstrip("/")
NETWORK = os.getenv("X402_NETWORK", "eip155:42220").strip()
CELO_RPC_URL = os.getenv("CELO_RPC_URL", "https://forno.celo.org")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
BNB_RPC_URL = os.getenv("BNB_RPC_URL", "https://bsc-dataseed.binance.org")

# Config de red (Celo no viene por defecto en x402). name/version verificados
# on-chain contra los contratos USDC.
_NETWORK_CFG = {
    "eip155:42220": {
        "chain_id": 42220,
        "rpc": CELO_RPC_URL,
        "default_asset": {
            "address": "0xcebA9300f2b948710d2653dD7B07f33A8B32118C",
            "name": "USDC",
            "version": "2",
            "decimals": 6,
        },
    },
    "eip155:11142220": {
        "chain_id": 11142220,
        "rpc": os.getenv("CELO_SEPOLIA_RPC_URL", "https://forno.celo-sepolia.celo-testnet.org"),
        "default_asset": {
            "address": "0x01C5C0122039549AD1493B8220cABEdD739BC44E",
            "name": "USDC",
            "version": "2",
            "decimals": 6,
        },
    },
    "eip155:56": {
        "chain_id": 56,
        "rpc": BNB_RPC_URL,
        "default_asset": {
            "address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            "name": "USD Coin",
            "version": "2",
            "decimals": 18,
            "asset_transfer_method": "permit2",
        },
    },
    "eip155:8453": {
        "chain_id": 8453,
        "rpc": BASE_RPC_URL,
        "default_asset": {
            "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "name": "USDC",
            "version": "2",
            "decimals": 6,
        },
    },
}
for _net, _cfg in _NETWORK_CFG.items():
    NETWORK_CONFIGS.setdefault(
        _net,
        {"chain_id": _cfg["chain_id"], "default_asset": _cfg["default_asset"]},
    )

_ERC20_BALANCE_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    }
]


def _usdc_balance(address: str) -> float:
    cfg = _NETWORK_CFG.get(NETWORK)
    if not cfg:
        return -1.0
    asset = cfg["default_asset"]
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
    c = w3.eth.contract(
        address=Web3.to_checksum_address(asset["address"]), abi=_ERC20_BALANCE_ABI
    )
    raw = c.functions.balanceOf(Web3.to_checksum_address(address)).call()
    return raw / (10 ** asset["decimals"])


def main() -> None:
    cert_type = sys.argv[1] if len(sys.argv) > 1 else "origins"
    target_wallet = (
        sys.argv[2] if len(sys.argv) > 2 else "0x1822438e03542b3a31cd39f434fbd7f0b9eaf7bd"
    )

    pk = os.getenv("X402_BUYER_PRIVATE_KEY")
    if not pk:
        print("[-] Define X402_BUYER_PRIVATE_KEY en el entorno.")
        sys.exit(1)
    if not pk.startswith("0x"):
        pk = "0x" + pk

    account = Account.from_key(pk)
    print(f"[*] Comprador     : {account.address}")
    print(f"[*] Red           : {NETWORK}")
    print(f"[*] Agente        : {AGENT_BASE_URL}")
    print(f"[*] Certificado   : {cert_type}  |  target: {target_wallet}")
    try:
        bal = _usdc_balance(account.address)
        print(f"[*] Saldo USDC    : {bal}")
        if bal == 0:
            print("[-] Abort: la wallet compradora no tiene USDC en esta red.")
            sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"[!] No se pudo leer saldo USDC ({e}); se intenta igual.")

    # Cliente x402 con el esquema exact EVM y el signer de la wallet.
    rpc = (_NETWORK_CFG.get(NETWORK) or {}).get("rpc") or CELO_RPC_URL
    signer = EthAccountSignerWithRPC(account, rpc)
    def _pick_network(_ver, accepts):
        for item in accepts:
            net = getattr(item, "network", None)
            if net == NETWORK:
                return item
        return accepts[0]

    client = x402ClientSync(payment_requirements_selector=_pick_network)
    client.register(NETWORK, ExactEvmClientScheme(signer))
    if hasattr(client, "set_spend_controls"):
        client.set_spend_controls(False)
    http_client = x402HTTPClientSync(client)

    url = f"{AGENT_BASE_URL}/v1/certificates/{cert_type}"
    base_headers = {"Content-Type": "application/json"}
    payload = {"wallet_address": target_wallet}

    with httpx.Client(timeout=120.0) as hc:
        # 1) Peticion sin pago -> 402
        r1 = hc.post(url, headers=base_headers, json=payload)
        print(f"\n[1] Sin pago -> HTTP {r1.status_code}")
        if r1.status_code != 402:
            print("[-] No se recibio 402. Respuesta:")
            print(r1.text[:800])
            sys.exit(1)

        pr_header = r1.headers.get(PAYMENT_REQUIRED_HEADER)
        if pr_header:
            try:
                accepts = decode_payment_required_header(pr_header)
                print("    payment-required:")
                print(json.dumps(accepts, indent=2, default=str)[:900])
            except Exception:  # noqa: BLE001
                pass

        # 2) Construir y firmar el pago; 3) reintentar con X-PAYMENT
        pay_headers, _payload = http_client.handle_402_response(
            dict(r1.headers), r1.content, url
        )
        print("\n[2] Pago firmado. Reintentando con X-PAYMENT...")
        r2 = hc.post(url, headers={**base_headers, **pay_headers}, json=payload)
        print(f"[3] Con pago -> HTTP {r2.status_code}")
        if r2.status_code != 200:
            print("    r2 headers:", {k: v[:80] for k, v in r2.headers.items() if "payment" in k.lower() or k.lower() in ("x-error", "www-authenticate")})

        settle = r2.headers.get(PAYMENT_RESPONSE_HEADER)
        if settle:
            try:
                info = decode_payment_response_header(settle)
                print("    settlement (payment-response):")
                print(json.dumps(info, indent=2, default=str)[:900])
            except Exception:  # noqa: BLE001
                print("    settlement header:", settle[:200])

        if r2.status_code == 200:
            data = r2.json()
            cert = data.get("certificate") or {}
            print("\n[OK] Certificado emitido tras el pago x402:")
            print(
                json.dumps(
                    {
                        "certificate_type": data.get("certificate_type"),
                        "grade": cert.get("grade"),
                        "grade_label": cert.get("grade_label"),
                        "certificate_id": cert.get("certificate_id"),
                        "receipt": cert.get("receipt"),
                    },
                    indent=2,
                    default=str,
                )
            )
        else:
            print("\n[-] El pago no resulto en 200. Cuerpo:")
            print(r2.text[:900])
            sys.exit(1)


if __name__ == "__main__":
    main()
