# API — Wallet labels lookup (`api-wallet-labels`)

Hackathon / demo endpoint: label lookup for addresses against `wallets.cex_addresses`, `wallets.bridge_addresses`, `wallets.mixer_addresses`, and `wallets.ofac_sanction_addresses` via `walcert.walcert_lookup_labels`.

**Not a full table dump.** Client sends addresses; Edge returns hits.

## Deploy

```bash
supabase functions deploy api-wallet-labels --no-verify-jwt
```

Uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (same as other Walcert Edge Functions).

## Contract

```http
POST /functions/v1/api-wallet-labels
Content-Type: application/json

{
  "addresses": ["0x..."],
  "chains": ["ethereum", "base"]
}
```

- Max **500** addresses per request.
- Priority: `ofac` > `mixer` > `cex` > `bridge`.
- CORS: `*` (demo).

Public router (optional): `POST https://api.globalscoreagent.com/v1/wallets/labels` (Cloudflare Worker `gsa-api-router`, 20 req/min/IP).

## Response

```json
{
  "success": true,
  "data": {
    "hits": [
      { "address": "0x...", "kind": "cex", "name": "Binance", "chain": "ethereum" }
    ],
    "not_found": ["0x..."],
    "queried": 1
  }
}
```
