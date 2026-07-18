import os
import sys
from web3 import Web3

# --- Compatibilidad middleware POA para Web3.py v6 y v7 ---
try:
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware as poa_middleware
    except ImportError as e:
        print(f"[-] Error critico: no se pudo importar el middleware POA ({e})")
        sys.exit(1)

RPC_URL = "https://forno.celo.org"
CHAIN_ID = 42220
REGISTRY_ADDRESS = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"

# URI inicial (metadata en ingles ya pinneado). Tras conocer el nuevo agentId
# se re-pinea el JSON con ese id y se corrige con set_agent_uri.py.
DEFAULT_URI = "ipfs://QmRwFPYEoqekhw3u6rqEGjooZhFQ3GeNh1y2S25zpG789V"

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ABI = [
    {
        "name": "register",
        "type": "function",
        "inputs": [{"name": "agentURI", "type": "string"}],
        "outputs": [{"name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
    },
    {
        "name": "tokenURI",
        "type": "function",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
    },
]


def register_new_agent():
    private_key = os.environ.get("AGENT_PRIVATE_KEY")
    if not private_key:
        print("[-] Error: define AGENT_PRIVATE_KEY en el entorno (owner nuevo).")
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

    # Preflight: saldo de gas.
    balance_wei = w3.eth.get_balance(account.address)
    balance_celo = w3.from_wei(balance_wei, "ether")
    print(f"[*] Wallet owner nuevo : {account.address}")
    print(f"[*] Saldo CELO         : {balance_celo}")
    print(f"[*] agentURI inicial   : {agent_uri}")
    if balance_wei == 0:
        print("[-] Abort: la wallet no tiene CELO para pagar gas.")
        sys.exit(1)

    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.functions.register(agent_uri).build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        }
    )
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.25)

    print("[*] Firmando y enviando transaccion de registro ...")
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hex = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex
    print(f"[+] Tx enviada. Hash: {tx_hex}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        print("[-] La transaccion revirtio (status=0).")
        sys.exit(1)

    # Detectar el nuevo agentId leyendo el evento Transfer (mint: from == 0x0).
    new_agent_id = None
    zero_topic = "0x" + "00" * 32
    for log in receipt.logs:
        if log.address.lower() != REGISTRY_ADDRESS.lower():
            continue
        topics = [t.hex() if hasattr(t, "hex") else t for t in log.topics]
        topics = [t if str(t).startswith("0x") else "0x" + str(t) for t in topics]
        if len(topics) >= 4 and topics[0].lower() == TRANSFER_TOPIC.lower():
            if int(topics[1], 16) == 0:  # from == address(0) => mint
                new_agent_id = int(topics[3], 16)
                break

    print("\n[================================================================]")
    if new_agent_id is not None:
        print(f"[OK] Agente registrado. NUEVO agentId = {new_agent_id}")
        try:
            uri = contract.functions.tokenURI(new_agent_id).call()
            print(f"[OK] tokenURI({new_agent_id}) = {uri}")
        except Exception:
            pass
    else:
        print("[!] Registro OK pero no se pudo leer el agentId del evento Transfer.")
        print("    Revisa la tx en Celoscan para ver el tokenId minteado.")
    print(f"[OK] Celoscan: https://celoscan.io/tx/{tx_hex}")
    print("[================================================================]\n")
    print(">>> Pasa este agentId al asistente para actualizar y re-pinnear el metadata.")


if __name__ == "__main__":
    try:
        register_new_agent()
    except Exception as e:
        print(f"[-] Fallo la ejecucion: {e}")
        sys.exit(1)
