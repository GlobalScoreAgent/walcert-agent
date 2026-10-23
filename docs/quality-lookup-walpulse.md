# Quality Lookup Walpulse (iq-v1) — consumo desde Walcert

Walcert Origins / Activity enriquecen labels vía el endpoint **cache-only** de Walpulse:

`POST https://api.walpulse.com/functions/v1/quality-lookup`

Contrato: `iq-v1`. Product guide (vault): `03 - Walcert/Quality Lookup Walpulse - Guía de consumo.md`.

## Auth (Edge secrets en proyecto GSA)

| Secret | Uso |
|--------|-----|
| `WALPULSE_QUALITY_LOOKUP_ENABLED` | `true` para activar |
| `WALPULSE_ANON_KEY` | JWT anon → headers `Authorization` + `apikey` |
| `WALCERT_QUALITY_LOOKUP_SECRET` | Header `X-Walcert-Secret` |
| `WALPULSE_QUALITY_LOOKUP_URL` | Opcional; default API pública Walpulse |

Nunca usar `service_role` de Walpulse desde GSA.

## Request

```json
{
  "items": [{ "chain_id": 1, "address": "0x..." }],
  "include_kleros": true
}
```

Batch 1–100; Walcert chunka automáticamente.

## Mapping → grade

| iq-v1 | Uso en Walcert |
|-------|----------------|
| `categories` ofac/mixer/cex/bridge/airdrop/protocol | `QualityHit.kind` (prioridad ofac→protocol) |
| `cex_name` / Spellbook `institution` | CEX quality |
| `sourcify` non-null | Soft strength (no gate A) |
| `kleros` | Details + soft block A si tags de riesgo |

Fórmulas: **origins-v2.3**, **activity-v2.2**.

## Código

- `supabase/functions/_shared/walpulse_quality_lookup.ts`
- `supabase/functions/_shared/labels.ts` → `lookupLabels()`
- Callers: `walcert-certificate-origins`, `walcert-certificate-activity`, `api-wallet-labels`

El RPC GSA `walcert_lookup_labels` y las tablas `wallets.*` de referencia fueron retirados tras el cutover (migración en `gsa-supabase-schema`).
