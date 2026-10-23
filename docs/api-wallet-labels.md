# API — Wallet labels lookup (`api-wallet-labels`)

Demo endpoint: label lookup for addresses via **Walpulse quality-lookup** (`iq-v1`, `include_kleros: true`).

**Not a full table dump.** Client sends addresses; Edge returns hits from Walpulse cache.

## Deploy

```bash
supabase functions deploy api-wallet-labels --no-verify-jwt
```

Requires Edge secrets: `WALPULSE_QUALITY_LOOKUP_ENABLED`, `WALPULSE_ANON_KEY`, `WALCERT_QUALITY_LOOKUP_SECRET` (see [quality-lookup-walpulse.md](quality-lookup-walpulse.md)).

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
- Priority: `ofac` > `mixer` > `cex` > `bridge` > `airdrop` > `protocol`.
- CORS: `*` (demo).

Public router (optional): `POST https://api.globalscoreagent.com/v1/wallets/labels`.

## Response

```json
{
  "success": true,
  "data": {
    "provider": "walpulse_quality_lookup",
    "contract": "iq-v1",
    "hits": [
      {
        "address": "0x...",
        "kind": "cex",
        "name": "Binance",
        "chain": "ethereum",
        "sourcify_verified": false,
        "kleros_hit": true,
        "kleros_risk": false,
        "spellbook_categories": ["institution"],
        "source": "walpulse"
      }
    ],
    "not_found": ["0x..."],
    "queried": 1
  }
}
```
