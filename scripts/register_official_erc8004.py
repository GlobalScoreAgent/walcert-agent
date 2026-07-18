import os
import sys
from web3 import Web3

# --- Manejo adaptativo de compatibilidad para Web3.py v6 y v7 ---
USE_V7_MIDDLEWARE = True
try:
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware as poa_middleware
        USE_V7_MIDDLEWARE = False
    except ImportError as e:
        print(f"[-] Error crítico: No se pudo importar el middleware POA ({e})")
        sys.exit(1)

def register_official_agent():
    rpc_url = "https://forno.celo.org"
    chain_id = 42220
    
    # OPSEC: Leemos la llave privada desde el entorno
    private_key = os.environ.get("AGENT_PRIVATE_KEY")
    if not private_key:
        print("[-] Error: La variable de entorno AGENT_PRIVATE_KEY no está definida.")
        sys.exit(1)
        
    if private_key.startswith("0x"):
        private_key = private_key[2:]

    # EL CID INMUTABLE QUE ACABAMOS DE GENERAR EN AWS:
    agent_uri = "ipfs://QmUvSRPsyHw4JwGPTwkqRhN6KCjLGut39mn3DFzn3fbmLb"
    
    # Contrato oficial de ERC-8004 Identity Registry
    official_registry_address = Web3.to_checksum_address("0x8004A169FB4a3325136EB29fA0ceB6D2e539a432")
    
    # ABI mínimo necesario para interactuar con el estándar
    abi = [
        {
            "name": "register",
            "type": "function",
            "inputs": [{"name": "agentURI", "type": "string"}],
            "outputs": [],
            "stateMutability": "nonpayable"
        }
    ]

    print(f"[*] Conectando a RPC de Celo: {rpc_url}...")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    w3.middleware_onion.inject(poa_middleware, layer=0)
        
    if not w3.is_connected():
        raise ConnectionError("No se pudo conectar al nodo RPC de Celo")
        
    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(address=official_registry_address, abi=abi)

    print(f"[*] Registrando Agente Oficialmente. Wallet: {account.address}")
    print(f"[*] agentURI a inyectar: {agent_uri}")
    
    nonce = w3.eth.get_transaction_count(account.address)
    tx_params = {
        'from': account.address,
        'nonce': nonce,
        'chainId': chain_id,
        'gasPrice': w3.eth.gas_price
    }
    
    print("[*] Construyendo transacción...")
    tx = contract.functions.register(agent_uri).build_transaction(tx_params)
    
    # Buffer de gas para Celo
    tx['gas'] = int(w3.eth.estimate_gas(tx) * 1.25)
    
    print("[*] Firmando y enviando transacción...")
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    print(f"[+] Transacción en vuelo. Hash: {tx_hash.hex()}")
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print("\n[================================================================]")
    print(f"[🟢] ¡AGENTE REGISTRADO EXITOSAMENTE EN ERC-8004 IDENTIY REGISTRY!")
    print(f"[🟢] Ya sos parte oficial de la red descentralizada.")
    print(f"[================================================================]\n")

if __name__ == "__main__":
    try:
        register_official_agent()
    except Exception as e:
        print(f"[-] Falló la ejecución: {e}")
        sys.exit(1)
