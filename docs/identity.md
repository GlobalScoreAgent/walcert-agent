# Identidad Walcert (agentId 9699)

Fuente canónica de producto: bóveda Obsidian `03 - Walcert`. Este archivo resume el estado **técnico** en el repo tras la alineación de julio 2026.

## Identidad on-chain

| Campo | Valor |
|-------|--------|
| agentId (Celo) | **9699** — emisión / anclaje de certificados |
| Explorer Celo | https://erc-8004.quicknode.com/agents/celo-mainnet/9699 |
| agentId (Ethereum) | **50032** — Agent City / discovery Eth (2026-08-16) |
| agentURI (Eth) | `ipfs://QmRdccB4vxSdJPpTnm29VzLFnc4BrieQUvajyutGw92KkV` |
| Tx Eth Identity | https://etherscan.io/tx/0x203de8fe65db17faaf7b210fe1e9022ec089d123e43a81e1dfc02a77ad2887a7 |
| Owner | `0x475F589BD4bFe82b333b8006dcc278f393b8E124` |
| payTo / operativa | `0xF4D938200445B0Df0f028af6d90D016147AEd095` (USDC Celo **y** Base) |
| Monitor / firmante | `0xE7e9f27e02149696b33C332b1C2e19F4BF723e51` |
| agentId (BNB) | **265982** — TermiX / DappBay (no es el emisor canónico) |
| Public URL | https://walcert.globalscoreagent.com (`GET /` = agent card JSON bilingüe) |
| Recibo NFT BNB | Contrato [`0x4e430fB5…24c7`](https://bscscan.com/address/0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7) (soulbound). `claim` del **pagador** x402 BNB; gas BNB del claimant. `data_hash` = futuro deliveryHash AACP. Dual `giveFeedback` BNB **supercedido**. |
| Concordium Agent Card | https://walcert.globalscoreagent.com/agent-card.json (CIS-8004 `agent_uri`; CIS-8 = Owner) |
| State file Eth | `agent/ethereum_identity.json` · script: `scripts/register_erc8004_ethereum.py` |

## Alineación obligatoria

Los tres sitios deben coincidir:

1. **EC2** `.env`: `AGENT_ID=9699`, `AGENT_WALLET` / `X402_PAY_TO` = payTo
2. **Edge secrets**: `WALCERT_ERC8004_AGENT_ID=9699`, `WALCERT_AGENT_WALLET` = payTo
3. **Fallbacks en código**:
   - Agente: `app/config.py`
   - Edge: `supabase/functions/**/_shared/certificate.ts` → `issuer()`

No usar la identidad anterior (`9696` / `0x2eFC66…`).

## Smoke

- `GET /` → `agent_id: 9699`, explorer `…/9699`
- Certificado pagado / fila en `walcert.certificate_requests` → `issuer.agent_id == "9699"`

Ver también: [deployment-guide.md](deployment-guide.md), [edge-function-security.md](edge-function-security.md), [concordium-cis8004.md](concordium-cis8004.md), [agent/registration.json](../agent/registration.json).
