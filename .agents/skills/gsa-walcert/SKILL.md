---
name: gsa-walcert
description: >-
  Bootstrap full Walcert Agent context for Global Score Agent work. Loads product
  knowledge from the Obsidian vault (03 - Walcert, ADRs) and technical docs from
  the walcert-agent repo so an agent can start coding without reinventing
  architecture. Use when starting or continuing Walcert work, when the user
  mentions Walcert, warcert, gsa-walcert, certificates A-F, x402 paywall,
  ERC-8004 agentId 9699, Edge scoring, or walcert.globalscoreagent.com.
---

# GSA Walcert — context bootstrap

Load this skill **before** proposing or editing Walcert code. Product truth lives in the Obsidian vault; implementation detail lives in the repo `docs/`. Do not invent scores, wallets, endpoints, or decisions.

## Mandatory bootstrap (do this first)

Copy and track:

```
Walcert bootstrap:
- [ ] 1. Vault index via MCP Obsidian
- [ ] 2. Core product notes (03 - Walcert)
- [ ] 3. Relevant ADRs (08 - Decisiones)
- [ ] 4. Repo docs for the task
- [ ] 5. Brief confirmation to the user
```

### 1. Vault — MCP `user-obsidian`

If the server is unavailable, say so and fall back to repo docs only.

Read in order:

1. `03 - Walcert/Walcert Agent.md` (canonical index)
2. Task-relevant notes from that index (see map below)
3. Linked ADRs when the change touches payments, on-chain, or providers

Spanish vault; do not paste secrets into notes.

### 2. Note map (vault)

| Need | Note |
|------|------|
| What / identity / index | `03 - Walcert/Walcert Agent.md` |
| Flow, endpoints, Edge | `03 - Walcert/Arquitectura.md` |
| Four certificate types | `03 - Walcert/Certificados.md` |
| Owner / payTo / monitor | `03 - Walcert/Identidad y wallets.md` |
| x402 pricing / Track 2 | `03 - Walcert/Pagos x402.md` |
| EIP-712 + giveFeedback | `03 - Walcert/Verificabilidad on-chain.md` |
| Alchemy / Moralis / Zerion | `03 - Walcert/Providers y cobertura.md` |
| Prod URL, flags, checklist | `03 - Walcert/Operacion.md` |
| Repo GitHub (público vs GSA) | `03 - Walcert/Repositorio GitHub.md` |
| BNB x402 + receipt NFT / DappBay | `03 - Walcert/Pagos BNB y recibo NFT.md` |
| Agent layer rules | `10 - Agents/AGENTS.md` |
| Vault vs repo placement | `00 - Core/Rutina de documentación.md` |

### 3. ADRs (vault `08 - Decisiones`)

- `2026-07-19 - Anclaje on-chain vía ERC-8004 Reputation Registry.md`
- `2026-07-19 - Monetización x402 Track 2.md`
- `2026-07-19 - Split de providers Alchemy Moralis Zerion.md`

### 4. Repo docs (implementation)

**Public GitHub (canonical for links / DappBay / external):**  
https://github.com/MichBarbarian/walcert-agent  

Do **not** link `github.com/GlobalScoreAgent/walcert-agent` in external forms — that user account is flagged and returns **404** to anonymous visitors. Local workspace may still use `origin` → GSA; sync public clone via remote `mich` when needed.

Read only what the task needs (paths relative to the walcert-agent checkout):

| Need | Path |
|------|------|
| Overview / env | `README.md`, `.env.example` |
| Full deploy / onboarding | `docs/deployment-guide.md` |
| BNB x402 + receipt NFT | `docs/bnb-x402-receipt.md` |
| Certificate business | `docs/certificates-en.md` or `docs/certificados-es.md` |
| JSON shapes | `docs/certificate-json-schemas.md` |
| Edge auth model | `docs/edge-function-security.md` |

Code entry points: `server.py`, `app/services.py`, `app/onchain.py`, `app/payments.py`, `app/providers/`, `supabase/functions/`, `contracts/WalcertBnbReceipt.sol`.

Deeper tables (wallets, env names, endpoints) → [reference.md](reference.md).

## Hard rules

1. **Vault for product / why; repo for how.** Do not duplicate long deploy guides into Obsidian. Public repo URL = **MichBarbarian/walcert-agent**.
2. **Three wallets stay separate** (owner ≠ payTo ≠ monitor). Never put private keys in vault or commits.
3. **Preview** (`/v1/preview/*`) is free and does not sign/anchor. **Full** (`/v1/certificates/*`) is x402 + EIP-712 + `giveFeedback`.
4. Identity changes require **both** agent `.env` (`AGENT_ID`, `AGENT_WALLET`) and Edge secrets (`WALCERT_ERC8004_AGENT_ID`, `WALCERT_AGENT_WALLET`).
5. New product decisions → propose ADR under `08 - Decisiones` + short note under `03 - Walcert` when appropriate.
6. Prefer Spanish when talking to the user unless they ask otherwise.

## After bootstrap

Reply with a short confirmation (≤5 bullets): agentId/URL, which notes you read, which repo docs you read, and the proposed next step for the user’s task. Then start the work.

## Auditoría ops (skill hermano)

Para salud de endpoints (Celo + ACP) y estadísticas de uso 7d en Supabase, cargá/seguí **`gsa-walcert-health`** (no duplicar ese procedimiento aquí).
