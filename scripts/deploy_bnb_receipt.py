"""Deploy WalcertBnbReceipt to BSC mainnet.

Reads OWNER_AGENT_PRIVATE_KEY (or AGENT_PRIVATE_KEY) from env/.env.
Never prints the key. Aborts if the signer is not the expected Owner.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

try:
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
except ImportError:
    from web3.middleware import geth_poa_middleware as poa_middleware

EXPECTED_OWNER = Web3.to_checksum_address("0x475F589BD4bFe82b333b8006dcc278f393b8E124")
ISSUER = Web3.to_checksum_address("0xE7e9f27e02149696b33C332b1C2e19F4BF723e51")
BASE_URI = os.environ.get(
    "BNB_RECEIPT_BASE_URI", "https://walcert.globalscoreagent.com/v1/receipts/"
)
RPC_URL = os.environ.get("BNB_RPC_URL", "https://bsc-dataseed.binance.org")
CHAIN_ID = 56
SOL_PATH = ROOT / "contracts" / "WalcertBnbReceipt.sol"


def _private_key() -> str:
    pk = os.environ.get("AGENT_PRIVATE_KEY") or os.environ.get("OWNER_AGENT_PRIVATE_KEY")
    if not pk:
        print("[-] Define OWNER_AGENT_PRIVATE_KEY (o AGENT_PRIVATE_KEY) en .env")
        sys.exit(1)
    return pk if pk.startswith("0x") else "0x" + pk


def _compile():
    try:
        from solcx import compile_source, install_solc, set_solc_version
    except ImportError:
        print("[-] pip install py-solc-x")
        sys.exit(1)
    install_solc("0.8.24")
    set_solc_version("0.8.24")
    source = SOL_PATH.read_text(encoding="utf-8")
    compiled = compile_source(
        source,
        output_values=["abi", "bin"],
        solc_version="0.8.24",
    )
    for _name, art in compiled.items():
        if art.get("bin"):
            return art["abi"], art["bin"]
    print("[-] Compile produced no bytecode")
    sys.exit(1)


def main() -> None:
    pk = _private_key()
    acct = Account.from_key(pk)
    if acct.address.lower() != EXPECTED_OWNER.lower():
        print(f"[-] Key is {acct.address}, expected Owner {EXPECTED_OWNER}")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
    w3.middleware_onion.inject(poa_middleware, layer=0)
    if int(w3.eth.chain_id) != CHAIN_ID:
        print(f"[-] RPC chainId {w3.eth.chain_id}, expected {CHAIN_ID}")
        sys.exit(1)

    bal = w3.eth.get_balance(acct.address)
    print(f"[*] Signer : {acct.address}")
    print(f"[*] Issuer : {ISSUER}")
    print(f"[*] RPC    : {RPC_URL}")
    print(f"[*] BNB    : {w3.from_wei(bal, 'ether')}")
    if bal < w3.to_wei("0.001", "ether"):
        print("[-] Not enough BNB for gas")
        sys.exit(1)

    print("[*] Compiling contracts/WalcertBnbReceipt.sol (solc 0.8.24)...")
    abi, bytecode = _compile()
    if bytecode.startswith("0x"):
        bytecode = bytecode[2:]

    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    ctor = Contract.constructor(EXPECTED_OWNER, ISSUER, BASE_URI)
    nonce = w3.eth.get_transaction_count(acct.address)
    gas_price = int(w3.eth.gas_price * 12 // 10)
    try:
        gas = ctor.estimate_gas({"from": acct.address})
        gas = int(gas * 12 // 10)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] estimate_gas failed ({exc}); using 2_500_000")
        gas = 2_500_000

    tx = ctor.build_transaction(
        {
            "from": acct.address,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gas": gas,
            "gasPrice": gas_price,
        }
    )
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    print("[*] Sending deploy tx...")
    tx_hash = w3.eth.send_raw_transaction(raw)
    hx = tx_hash.hex()
    if not hx.startswith("0x"):
        hx = "0x" + hx
    print(f"[*] Tx     : https://bscscan.com/tx/{hx}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        print("[-] Deploy reverted")
        sys.exit(1)
    addr = Web3.to_checksum_address(receipt.contractAddress)
    print(f"[OK] Contract: {addr}")
    print(f"     https://bscscan.com/address/{addr}")
    print("     Set BNB_RECEIPT_CONTRACT in the agent .env and restart.")


if __name__ == "__main__":
    main()
