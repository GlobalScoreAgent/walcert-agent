import os
import sys
from web3 import Web3

# --- Manejo adaptativo de compatibilidad para Web3.py v6 y v7 ---
try:
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware as poa_middleware
    except ImportError as e:
        print(f"[-] Error critico: no se pudo importar el middleware POA ({e})")
        sys.exit(1)

# Configuracion Celo mainnet + ERC-8004 Identity Registry oficial
RPC_URL = "https://forno.celo.org"
CHAIN_ID = 42220
REGISTRY_ADDRESS = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
AGENT_ID = int(os.environ.get("AGENT_ID", "9699"))
DEFAULT_URI = "ipfs://QmT6G4Rbd78fg1AWmDv3ktBTD5c3hZPeYSsNtSwebLsTrb"

ABI = [
    {
        "name": "setAgentURI",
        "type": "function",
        "inputs": [
            {"name": "agentId", "type": "uint256"},
            {"name": "newURI", "type": "string"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "ownerOf",
        "type": "function",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
    },
    {
        "name": "tokenURI",
        "type": "function",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
    },
]


def set_agent_uri():
    # OPSEC: la llave privada se lee del entorno, nunca se versiona.
    private_key = os.environ.get("AGENT_PRIVATE_KEY")
    if not private_key:
        print("[-] Error: define AGENT_PRIVATE_KEY en el entorno (owner del agentId).")
        sys.exit(1)
    if private_key.startswith("0x"):
        private_key = private_key[2:]

    agent_uri = os.environ.get("AGENT_URI", DEFAULT_URI)

    print(f"[*] Conectando a RPC de Celo: {RPC_URL} ...")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    w3.middleware_onion.inject(poa_middleware, layer=0)
    if not w3.is_connected():
        raise ConnectionError("No se pudo conectar al nodo RPC de Celo")

    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(REGISTRY_ADDRESS), abi=ABI
    )

    # Verificacion previa: la wallet firmante debe ser owner del agentId.
    try:
        owner = contract.functions.ownerOf(AGENT_ID).call()
    except Exception as e:
        print(f"[-] No se pudo leer ownerOf({AGENT_ID}): {e}")
        sys.exit(1)

    print(f"[*] agentId          : {AGENT_ID}")
    print(f"[*] owner on-chain   : {owner}")
    print(f"[*] wallet firmante  : {account.address}")
    if owner.lower() != account.address.lower():
        print("[-] Abort: la wallet firmante NO es el owner del agentId.")
        print("    Solo el owner (o un operador aprobado) puede llamar setAgentURI.")
        sys.exit(1)

    try:
        current = contract.functions.tokenURI(AGENT_ID).call()
        print(f"[*] agentURI actual  : {current}")
    except Exception:
        pass

    print(f"[*] agentURI nuevo   : {agent_uri}")

    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.functions.setAgentURI(AGENT_ID, agent_uri).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)

    print("[*] Firmando y enviando transaccion ...")
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"[+] Tx enviada. Hash: 0x{tx_hash.hex().lstrip('0x')}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status == 1:
        print("\n[================================================================]")
        print(f"[OK] agentURI actualizado para agentId {AGENT_ID}")
        print(f"[OK] Ver en Celoscan: https://celoscan.io/tx/0x{tx_hash.hex().lstrip('0x')}")
        print("[================================================================]\n")
    else:
        print("[-] La transaccion revirtio (status=0). Revisa owner/permisos.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        set_agent_uri()
    except Exception as e:
        print(f"[-] Fallo la ejecucion: {e}")
        sys.exit(1)
