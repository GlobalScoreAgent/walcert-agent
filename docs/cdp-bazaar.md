# CDP Bazaar / agentic.market

How Walcert gets discovered in Coinbase’s x402 catalog. Product context lives in the Obsidian vault (`03 - Walcert/Integración CDP Bazaar`); this file is the operator checklist.

## What it is

CDP Bazaar indexes **x402 resources** that (1) declare `extensions.bazaar` on a 402 and (2) complete a **settle through the CDP facilitator on Base**. The public UI is [agentic.market](https://agentic.market). It is not x402bazaar.org and not Circle’s marketplace.

Python is opt-in: `bazaar_resource_server_extension` + `declare_discovery_extension` in `app/payments.py`. Dependency: `jsonschema>=4.18.0`.

## 402 shape (prod)

When Base/CDP is mounted:

- `accepts[0]` = Base (`eip155:8453`, USDC `0x8335…`)
- `accepts[1]` = Celo (`eip155:42220`) — Track 2 stays available
- `extensions.bazaar` on `POST /v1/certificates/{origins,activity,multichain,portfolio}`
- Preview and `/v1/verify` are not declared (no x402 paywall)

If CDP keys are missing, the 402 is Celo-only and **Bazaar is off**.

## Validate vs indexed

| Check | Means |
|-------|--------|
| `POST https://api.cdp.coinbase.com/platform/v2/x402/validate` → `valid: true` | Eligible. No API key. Reads `accepts[0]`. |
| First **settle** via CDP on that URL | Resource appears in discovery / agentic.market |
| ≥1 CDP settle every 30 days | Stay listed (Celo settlements do not count) |

Featured / `enriched` is editorial. Indexed is the success criterion.

## Deploy

```powershell
powershell -File deploy\push_cdp_bazaar.ps1
```

Smoke unpaid: `POST https://walcert.globalscoreagent.com/v1/certificates/origins` → **402**, `accepts[0]=eip155:8453`, `extensions.bazaar` present.

## Index a route (buyer)

Any EOA with native Base USDC can pay. Do **not** use payTo as the buyer (self-pay). Owner as buyer is fine **locally** (`X402_BUYER_PRIVATE_KEY`); never put the owner key on the server.

```powershell
$env:AGENT_BASE_URL = "https://walcert.globalscoreagent.com"
$env:X402_NETWORK = "eip155:8453"
python scripts/x402_buyer_test.py origins
```

Each paid path is a separate catalog resource. Settling `origins` does not index activity / multichain / portfolio.

## Evidence (2026-08-17)

- Validate ×4: `valid: true` / `simulation.outcome: accepted` (2026-08-16)
- First Base settle: origins, payer Owner `0x475F…E124` → payTo `0xF4D9…d095`, $0.05 USDC
- Tx: https://basescan.org/tx/0xfae8a5c6e5b12aec49472fe547a40cb069be81b43ae4e10fdbf0bd4023924216
- Listing: [agentic.market/?q=walcert](https://agentic.market/?q=walcert) — service `walcert-globalscoreagent-com`, endpoint origins, **not** featured
