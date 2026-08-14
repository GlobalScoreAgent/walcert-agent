# GSA Walcert — quick reference

Facts for agents after reading vault notes. Prefer vault + repo docs if anything conflicts.

## Identity

| Field | Value |
|-------|--------|
| Product | Walcert Agent (Global Score Agent) |
| agentId | `9699` |
| Chain | Celo mainnet `eip155:42220` |
| Public URL | https://walcert.globalscoreagent.com |
| Repo | https://github.com/GlobalScoreAgent/walcert-agent |
| Identity Registry | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` |
| Reputation Registry | `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63` |

## Wallets (do not mix)

| Role | Address | Runtime? |
|------|---------|----------|
| Owner | `0x475F589BD4bFe82b333b8006dcc278f393b8E124` | No — admin scripts only |
| payTo / operational | `0xF4D938200445B0Df0f028af6d90D016147AEd095` | Receives USDC x402 on Celo and Base |
| Monitor / signer | `0xE7e9f27e02149696b33C332b1C2e19F4BF723e51` | Hot — EIP-712 + `giveFeedback` |

## Certificates → data provider

| Type | Provider | Notes |
|------|----------|--------|
| `origins` | Alchemy `alchemy_getAssetTransfers` | Labels via Edge / `wallets.*` |
| `activity` | Alchemy Transfers (~7d client window) | Same |
| `multichain` | Moralis `/wallets/{addr}/chains` | Celo merged separately |
| `portfolio` | Zerion | Positions |

BSC Transfers via Alchemy confirmed HTTP 200 in production logs (Jul 2026). Gnosis / X Layer not in agent config yet.

## Endpoints

| Path | Auth | Output |
|------|------|--------|
| `GET /` | none | Bilingual agent card JSON (`provider` GSA brand + discovery) |
| `POST /v1/preview/{type}` | none | Grade A–F only (`origins`/`activity`; IP rate-limited) |
| `POST /v1/certificates/{type}` | x402 `$0.05` USDC (Celo or Base) | Full cert + `signature` + `onchain` |
| `GET /health`, `GET /v1/quota` | none | Ops |

Identity defaults (agent `config.py` + Edge `issuer()`): `AGENT_ID`/`WALCERT_ERC8004_AGENT_ID` = **9699**, payTo = `0xF4D9…`. Keep EC2 `.env` and Edge secrets aligned.

## Edge Functions (Bearer shared secret)

`walcert-certificate-{origins,activity,multichain,portfolio}`, `walcert-payment-log`, `walcert-certificate-onchain`.

## x402

Dual paywall on the same endpoint. Client picks one network in the 402.

| | Celo (Track 2) | Base |
|--|----------------|------|
| Network | `eip155:42220` | `eip155:8453` |
| USDC | `0xcebA9300f2b948710d2653dD7B07f33A8B32118C` | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Facilitator | `https://api.x402.celo.org` | CDP `https://api.cdp.coinbase.com/platform/v2/x402` |

Same payTo EOA. Track 2 attribution is Celo settlements only. Env: `X402_BASE_ENABLED`, `COINBASE_API_KEY_BASE`, `COINBASE_SECRET_BASE`.

## On-chain cert

After Edge `data_hash`: EIP-712 sign + `giveFeedback` (`feedbackHash` = `data_hash`, `value` = paid amount, `tag1` = `certificate_issued`). Verify: `python scripts/verify_certificate.py <cert.json>`.

## Persistence

- `walcert.certificate_requests` — cert + signature + onchain
- `walcert.x402_payments` — settled payments

## Key env flag names (never commit values)

`EDGE_SHARED_SECRET`, `X402_ENABLED`, `X402_BASE_ENABLED`, `COINBASE_API_KEY_BASE`, `COINBASE_SECRET_BASE`, `CERT_SIGNING_ENABLED`, `ONCHAIN_ANCHOR_ENABLED`, `AGENT_SIGNER_KEY`, `PAYMENT_LOG_ENABLED`, `ONCHAIN_LOG_ENABLED`.
