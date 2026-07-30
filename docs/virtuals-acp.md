# Walcert × Virtuals ACP

Adapter self-hosted (`acp serve`) that lists Walcert offerings on Virtuals ACP and
calls the agent via the **internal marketplace channel** (no x402 double-pay).

## Architecture

```text
Client ACP ──escrow USDC (Base)──► ACP Provider wallet
                 │
                 ▼
         acp serve handlers ──Bearer + X-Walcert-Marketplace──► Walcert FastAPI
                                                                     │
                                                                     ▼
                                                              Edge scoring
                                                                     │
                                                                     ▼
                                              walcert.certificate_requests
                                              (access_channel / marketplace / billing)
```

- Direct API clients still pay **x402 on Celo** → rows in `walcert.x402_payments`.
- Marketplace adapters use **internal auth** → `access_channel=internal`,
  `billing=marketplace`, `marketplace=virtuals_acp` (no x402 settle).

## Prerequisites (agent)

1. Apply SQL:
   [`supabase/migrations/20260723_certificate_requests_attribution.sql`](../supabase/migrations/20260723_certificate_requests_attribution.sql)
   (also port to `gsa-supabase-schema`).
2. Redeploy Edge scoring functions (origins/activity/multichain/portfolio).
3. On the agent host `.env`:

```bash
WALCERT_INTERNAL_API_KEY=<openssl rand -hex 32>
WALCERT_INTERNAL_MARKETPLACES=virtuals_acp,olas,circle,x402_bazaar,agentverse
```

4. Restart `walcert-agent`.

### Internal HTTP contract

```http
Authorization: Bearer <WALCERT_INTERNAL_API_KEY>
X-Walcert-Marketplace: virtuals_acp
X-Walcert-Access-Channel: internal
```

Invalid claim → **401** (does not fall through to x402).

## Offerings

| Offering folder | ACP price | Walcert endpoint |
|-----------------|-----------|------------------|
| `preview-origins` (`walcert_preview_origins`) | $0.01* | `POST /v1/preview/origins` |
| `preview-activity` (`walcert_preview_activity`) | $0.01* | `POST /v1/preview/activity` |
| `certificate-origins` (`walcert_certificate_origins`) | $0.05 | `POST /v1/certificates/origins` |
| `certificate-activity` (`walcert_certificate_activity`) | $0.05 | `POST /v1/certificates/activity` |
| `certificate-multichain` (`walcert_certificate_multichain`) | $0.05 | `POST /v1/certificates/multichain` |
| `certificate-portfolio` (`walcert_certificate_portfolio`) | $0.05 | `POST /v1/certificates/portfolio` |
| `verify-certificate` (`walcert_verify_certificate`) | $0.01* | `POST /v1/verify` |

\*ACP rejects price `0`; product intent for preview/verify is free. Offering names must be **lowercase + underscores** (UI rejects spaces/Title Case as “incompatible name”).


Code: [`integrations/virtuals-acp/`](../integrations/virtuals-acp/).

## Deploy checklist (ops)

### A. Agent + DB

- [ ] Migration applied on prod Supabase (`access_channel`, `marketplace`, `billing` + indexes).
- [ ] Edge functions redeployed.
- [ ] `WALCERT_INTERNAL_API_KEY` set on EC2; same value in ACP adapter `.env`.
- [ ] Smoke direct x402 still works (optional).
- [ ] Smoke internal:

```bash
curl -sS -X POST https://walcert.globalscoreagent.com/v1/certificates/origins \
  -H "Authorization: Bearer $WALCERT_INTERNAL_API_KEY" \
  -H "X-Walcert-Marketplace: virtuals_acp" \
  -H "X-Walcert-Access-Channel: internal" \
  -H "Content-Type: application/json" \
  -d '{"wallet_address":"0x..."}'
```

- [ ] Confirm row: `access_channel=internal`, `marketplace=virtuals_acp`, `billing=marketplace`.

### B. Virtuals ACP provider

- [ ] Install CLI: `npm i -g @virtuals-protocol/acp-cli` (pin version in runbook).
- [ ] Register / login agent; `acp agent add-signer` (OS keychain). Provider wallet on **Base** (≠ Celo payTo/monitor).
- [ ] `cd integrations/virtuals-acp && cp .env.example .env` and fill secrets.
- [ ] Runtime (CLI 1.0.x): `acp events listen` + `provider_worker.mjs` (not legacy `acp serve`).
      systemd: `walcert-acp-listen` + `walcert-acp-worker` on ACP EC2 (`3.139.63.56`).
- [ ] Create offerings via `acp offering create` (min price **0.01** USDC; ACP rejects `0`).
      Helper: `deploy/acp_create_offerings.sh`.

- [ ] E2E: hire preview ($0) → grade; hire certificate ($0.05) → signed cert; verify by `tx_hash`.

### C. Metrics SQL

```sql
-- Direct USDC settles (Track 2 Celo)
SELECT count(*) FROM walcert.x402_payments;

-- Internal channel by marketplace
SELECT marketplace, certificate_type, billing, count(*)
FROM walcert.certificate_requests
WHERE access_channel = 'internal'
GROUP BY 1, 2, 3
ORDER BY 4 DESC;

-- Direct paid product emissions
SELECT count(*) FROM walcert.certificate_requests
WHERE access_channel = 'direct' AND billing = 'x402';
```

## Honest notes

- ACP escrow revenue (Base) **≠** Walcert x402 Track 2 (Celo). Internal path does not credit `x402_payments`.
- Protect `WALCERT_INTERNAL_API_KEY` like production credentials; rotate if leaked.
- Verify offering does not yet write attribution rows (no emission log); certificates/previews do.

## References

- Docs ACP Serve: https://os.virtuals.io/acp/cli/acp-serve/
- Vault: `03 - Walcert/Integración Virtuals ACP`
- ADR: canal interno multi-marketplace + atribución BD
