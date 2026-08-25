# Walcert — JSON por certificado

Documento de referencia de los payloads HTTP del agente (hot analysis + Edge scoring).

**Base URL (prod):** `https://walcert.globalscoreagent.com`  
**Método:** `POST /v1/certificates/{certificate_type}` (x402 o canal Summit/interno)  
**Preview:** `POST /v1/preview/{certificate_type}` (solo `origins` / `activity`)

`certificate_type` ∈ `origins` | `activity` | `multichain` | `portfolio`

---

## Request (todos los certificados)

```json
{
  "wallet_address": "0x2eFC66c0a78620Dd254443998BF2f11B685602E3"
}
```

---

## Envelope de éxito (HTTP 200)

El agente responde con este envoltorio. `analysis` es el JSON enriquecido por el provider (+ pricing en Origins). `certificate` es el resultado del scoring Edge (nota A–F + métricas).

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "<origins|activity|multichain|portfolio>",
  "provider": "<alchemy|goldrush|zerion>",
  "analysis": { },
  "certificate": { }
}
```

| `certificate_type` | `provider` |
|--------------------|------------|
| `origins` | `alchemy` |
| `activity` | `alchemy` |
| `multichain` | `goldrush` |
| `portfolio` | `zerion` |

---

## 1. Origins (`POST /v1/certificates/origins`)

Provider: Alchemy (networks from `erc_8004.chains` where `is_active` + `subdomain_alchemy`; fallback `ALCHEMY_NETWORKS`). Up to **500 transfers/network**. USD via DefiLlama / stables / spot. Edge formula `origins-v2.2`.

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "origins",
  "provider": "alchemy",
  "analysis": {
    "module": "origins",
    "version": "2.0",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "networks": ["eth-mainnet", "base-mainnet", "celo-mainnet", "bnb-mainnet"],
    "analyzed_at": "2026-07-26T22:00:00Z",
    "total_transfers_analyzed": 820,
    "total_inflows": 800,
    "priced_inflows": 640,
    "unpriced_inflows": 160,
    "total_value_usd_priced": 12540.2,
    "selection": { "order": "asc", "max_per_network": 500, "formula_hint": "origins-v2.2" },
    "inflows": [
      {
        "from": "0x28c6c06298d514db089934071355e5743bf21d60",
        "usd": 1250.4,
        "usd_method": "historical",
        "amount": 0.42,
        "ts": "2024-03-12T09:14:22Z",
        "asset_category": "external",
        "symbol": "ETH",
        "contract": null,
        "chain_id": 1
      }
    ],
    "first_funding": {},
    "origin_summary": {},
    "top_senders": [],
    "senders": [],
    "score_inputs": {}
  },
  "certificate": {
    "type": "ORIGINS",
    "version": "2.0",
    "formula_version": "origins-v2.2",
    "grade": "B",
    "grade_breakdown": {
      "formula_version": "origins-v2.2",
      "subject_type": "entity",
      "applied_rule": "B",
      "grade": "B",
      "inputs": {},
      "rules_evaluated": []
    },
    "inputs_hash": "0x...",
    "details": {
      "main_origin_type": "cex",
      "cex_percentage": 42.1,
      "bridge_percentage": 10.0,
      "unique_senders": 18,
      "mixing_risk": "low",
      "first_funding_age_days": 820,
      "sanctions_hit": false,
      "hhi": 0.18,
      "concentration": {
        "top1_pct": 28.0,
        "top3_pct": 55.0,
        "top1_share": 0.28,
        "top3_share": 0.55
      },
      "category_percentages": {
        "cex": 42.1,
        "bridge": 10.0,
        "mixer": 0,
        "ofac": 0,
        "airdrop": 0,
        "synthetic": 0,
        "organic": 30.0,
        "unknown": 17.9,
        "dex": 0
      },
      "cex_quality": {
        "regulated_high_quality_usd": 0,
        "high_risk_usd": 0,
        "standard_usd": 0,
        "unknown_usd": 0
      },
      "temporal_funding": {
        "pattern": "gradual",
        "span_days": 120.5,
        "median_gap_hours": 36.0,
        "burst_score": 0.12
      },
      "direct_exposure": {
        "mixer_hits": 0,
        "ofac_hits": 0,
        "sanctions_hit": false,
        "mixing_risk": "low"
      },
      "organic_vs_synthetic": {
        "labeled": 40,
        "synthetic_nft": 2,
        "synthetic_airdrop_reward": 1,
        "organic_or_unknown": 50,
        "unknown": 7
      },
      "formula_version": "origins-v2.2",
      "priced_inflows": 640,
      "unpriced_inflows": 160,
      "total_value_usd_priced": 12540.2
    }
  }
}
```

Notes:

- Las **9 señales** viven en `certificate.details` (tabla arriba en docs de certificados).
- `inflows[].usd` puede ser `null` (`usd_method: none`); % y HHI usan solo filas con `usd > 0`.
- `usd_method` ∈ `stable` | `historical` | `spot` | `none` (y `alchemy` solo si hay fiat explícito).
- `chains_analyzed` lista redes con transfers hallados (lista dinámica vía Edge `walcert-alchemy-networks` / `erc_8004.chains`).
- Legacy `origin_summary` / `senders` / `top_senders` siguen poblados por compatibilidad.

---

## 2. Activity (`POST /v1/certificates/activity`)

Provider: Alchemy (ventana **15 días**, redes desde `erc_8004.chains`; ≤500 txs/dir/red). USD vía DefiLlama. Edge formula `activity-v2.1`.

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "activity",
  "provider": "alchemy",
  "analysis": {
    "module": "activity",
    "version": "2.0",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "window_days": 15,
    "total_transfers": 94,
    "unique_counterparties": 27,
    "counterparty_hhi": 0.18,
    "reciprocity_ratio": 0.12,
    "net_to_gross_ratio": 0.41,
    "velocity_txs_per_day": 6.3,
    "burstiness_score": 0.22,
    "token_diversity": 8,
    "bot_like_score": 0.15,
    "nft_transfer_pct": 5.0,
    "fungible_transfer_pct": 95.0,
    "selection": { "order": "desc", "window_days": 15, "max_per_direction": 500, "truncated": false, "formula_hint": "activity-v2.1" },
    "transfers": [
      {
        "ts": "2026-07-20T12:00:00Z",
        "from": "0x...",
        "to": "0x...",
        "value_usd": 120.5,
        "usd_method": "historical",
        "asset_category": "external",
        "chain_id": 8453
      }
    ]
  },
  "certificate": {
    "type": "ACTIVITY",
    "version": "2.0",
    "formula_version": "activity-v2.1",
    "grade": "B",
    "grade_breakdown": {},
    "inputs_hash": "0x...",
    "details": {
      "window_days": 15,
      "unique_counterparties": 27,
      "counterparty_hhi": 0.18,
      "cex_interaction_pct_value": 22.4,
      "cex_interaction_pct_txs": 31.0,
      "wash_score": 0.12,
      "bot_like_score": 0.15,
      "nft_vs_fungible_ratio": 0.05
    }
  }
}
```

Notes: las 11 señales viven en `certificate.details`; `selection.truncated` indica si se agotó el page cap antes del cutoff.

---

## 3. Multi-Chain (`POST /v1/certificates/multichain`)

Provider: GoldRush (`/activity/` + `transactions_summary` top 6). Edge formula `multichain-v2.1`. Celo is native (no Alchemy merge). Preview of `multichain` is 403.

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "multichain",
  "provider": "goldrush",
  "analysis": {
    "module": "multichain",
    "version": "2.0",
    "formula_hint": "multichain-v2.1",
    "core_ecosystem_list_version": "2026-07-26",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "analyzed_at": "2026-07-26T19:45:00Z",
    "total_chains": 4,
    "total_chains_with_activity": 4,
    "activity_span_days": 986,
    "active_chains_30d": 2,
    "active_chains_90d": 3,
    "dormant_ratio": 0.25,
    "consistency_score": 0.68,
    "recency_score": 0.55,
    "footprint_concentration": 0.42,
    "core_ecosystems": ["base", "eth", "polygon"],
    "core_ecosystem_count": 3,
    "main_chains": ["eth", "base", "bsc", "polygon"],
    "chains": [
      {
        "chain": "base",
        "chain_id": 8453,
        "first_transaction": "2024-02-18T11:05:44Z",
        "last_transaction": "2026-07-16T20:12:55Z",
        "span_days": 879,
        "is_recent_30d": true,
        "is_recent_90d": true,
        "is_dormant": false
      }
    ],
    "score_inputs": {
      "chain_count_score": 0.8,
      "longevity_score": 0.88,
      "recency_score": 0.55,
      "consistency_score": 0.68,
      "core_presence_score": 0.75
    }
  },
  "certificate": {
    "type": "MULTICHAIN",
    "version": "2.0",
    "formula_version": "multichain-v2.1",
    "grade": "B",
    "grade_breakdown": {
      "formula_version": "multichain-v2.1",
      "subject_type": "entity",
      "applied_rule": "B",
      "grade": "B",
      "inputs": {},
      "rules_evaluated": []
    },
    "inputs_hash": "0x...",
    "details": {
      "total_chains_with_activity": 4,
      "activity_span_days": 986,
      "active_chains_90d": 3,
      "core_ecosystems": ["base", "eth", "polygon"]
    }
  }
}
```

Notas:

- Celo viene en GoldRush (`celo-mainnet`); no hay merge Alchemy.
- Intensity se muestrea en top N mainnets (`GOLDRUSH_INTENSITY_TOP_N`, default 6).
- Preview de `multichain` → 403.

### 3b. Alias Summit (`POST /v1/summit/certificates/multichain-v2`)

Mismo provider/fórmula que el público. Auth Summit required (`403 summit_only` otherwise). Certificate `type: MULTICHAIN`, `version: "2.0"`, `formula_version: "multichain-v2.1"`. See [bsg2026-summit.md](bsg2026-summit.md).

---

## 4. Portfolio (`POST /v1/certificates/portfolio`)

Provider: Zerion (`GET /wallets/{address}/positions/`). Edge formula `portfolio-v2.2`.

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "portfolio",
  "provider": "zerion",
  "analysis": {
    "module": "portfolio",
    "version": "2.0",
    "formula_hint": "portfolio-v2.2",
    "token_tier_list_version": "2026-07-26",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "analyzed_at": "2026-07-26T19:45:00Z",
    "total_value_usd": 12480.55,
    "liquid_value_usd": 9820.3,
    "locked_value_usd": 2660.25,
    "liquid_ratio": 78.7,
    "positions_count": 11,
    "positions_used": 8,
    "effective_positions": 7,
    "holdings_hhi": 0.24,
    "top1_share": 0.31,
    "dust_ratio": 0.03,
    "stablecoin_dominance": 42.5,
    "bluechip_share": 31.2,
    "meme_high_risk_share": 7.9,
    "defi_lp_share": 18.4,
    "protocol_exposure_count": 4,
    "native_gas_buffer_usd": 420.0,
    "native_gas_buffer_pct": 3.4,
    "locked_commitment_score": 0.213,
    "category_distribution": {
      "stablecoin": 42.5,
      "bluechip": 31.2,
      "defi_lp": 18.4,
      "meme_or_other": 7.9
    },
    "selection": {
      "positions_cap": 200,
      "dust_usd": 1.0,
      "formula_hint": "portfolio-v2.2",
      "token_tier_list_version": "2026-07-26"
    },
    "positions": [],
    "top_positions": []
  },
  "certificate": {
    "type": "PORTFOLIO",
    "version": "2.0",
    "formula_version": "portfolio-v2.2",
    "grade": "B",
    "grade_breakdown": {
      "formula_version": "portfolio-v2.2",
      "subject_type": "entity",
      "applied_rule": "B",
      "grade": "B",
      "inputs": {},
      "rules_evaluated": []
    },
    "inputs_hash": "0x...",
    "details": {
      "total_value_usd": 12480.55,
      "liquid_ratio": 78.7,
      "holdings_hhi": 0.24,
      "effective_positions": 7,
      "dust_ratio": 0.03,
      "token_tier_list_version": "2026-07-26"
    }
  }
}
```

---

## Respuestas de no disponibilidad (HTTP 503)

### Cuota agotada

```json
{
  "available": false,
  "status": "certificate_unavailable",
  "message": "Certificate not available",
  "certificate_type": "origins",
  "reason": "provider_quota_exceeded",
  "provider": "alchemy",
  "retry_after": "next_day"
}
```

`retry_after` puede ser `"next_day"` o `"next_month"` (Alchemy mensual).

### Provider no configurado (falta API key)

```json
{
  "available": false,
  "status": "certificate_unavailable",
  "message": "Certificate not available",
  "certificate_type": "portfolio",
  "reason": "provider_not_configured",
  "provider": "zerion",
  "retry_after": null
}
```

### Error del provider (HTTP 502)

```json
{
  "available": false,
  "status": "provider_error",
  "message": "Certificate not available",
  "certificate_type": "activity",
  "reason": "provider_error",
  "provider": "alchemy",
  "error": "HTTP 403: ..."
}
```

---

## Payload hacia la Edge Function

El agente envía:

```json
{
  "certificate_type": "origins",
  "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
  "analyzed_at": "2026-07-17T19:45:00Z",
  "payload": {
    "...": "analysis semicrudo (senders[] / counterparties[] / transfers[] / positions[])"
  }
}
```

Auth: `Authorization: Bearer <EDGE_SHARED_SECRET>`.

La respuesta HTTP del agente incluye `analysis` + `certificate` (grade A–F). Ver también `docs/edge-function-security.md`.

### Campos extra en analysis (fase Edge)

| Tipo | Campos |
|------|--------|
| origins | `senders[]` (cap 1000); `inflows[]` con amount/usd; `value_relevant_*` + `priced_coverage_pct` (Edge `origins-v2.2`) |
| activity | `counterparties[]`, `transfers[]` compacto **15d** (`window_days: 15`, formula `activity-v2.1`) |
| multichain | `chains[]` enriquecidos; Edge `multichain-v2.1` (GoldRush público) |
| multichain_v2 | Alias Summit del mismo pipeline; log type `multichain_v2` |
| portfolio | `positions[]` ricos; Edge `portfolio-v2.2` + dual totals `*_credible` / absurd filter |

### Envelope con certificado

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "origins",
  "provider": "alchemy",
  "analysis": { },
  "certificate": {
    "certificate_id": "...",
    "type": "ORIGINS",
    "grade": "B",
    "grade_label": { "eng": "Good", "esp": "Bueno" },
    "provider": "Powered by Global Score Agent. We provide specialized scoring for autonomous agents with daily indices. Contact us or visit our website: globalscoreagent.com",
    "issuer": { "name": "Walcert Agent", "agent_id": "9699", "erc8004_agent_id": "eip155:42220:0xF4D9...", "version": "1.0" },
    "details": { },
    "data_hash": "0x...",
    "signature": {
      "scheme": "eip712",
      "signer": "0xE7e9f27e02149696b33C332b1C2e19F4BF723e51",
      "signature": "0x...",
      "domain": { "name": "Walcert Certificate", "version": "1", "chainId": 42220 },
      "primary_type": "Certificate"
    },
    "onchain": {
      "status": "confirmed",
      "protocol": "erc8004-reputation",
      "method": "giveFeedback",
      "chain_id": 42220,
      "contract": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
      "agent_id": 9699,
      "monitor": "0xE7e9f27e02149696b33C332b1C2e19F4BF723e51",
      "tx_hash": "0x...",
      "block_number": 12345678,
      "feedback_index": 1,
      "value": 5,
      "value_decimals": 2,
      "tag1": "certificate_issued",
      "tag2": "ORIGINS",
      "feedback_hash": "0x...",
      "explorer_url": "https://celoscan.io/tx/0x...",
      "anchored_at": "2026-07-19T05:00:00Z"
    }
  }
}
```

> Nota sobre `provider`: hay dos campos con ese nombre. El `provider` del **envelope** (nivel superior) indica el proveedor de datos (`alchemy|goldrush|zerion`). El `provider` dentro de **`certificate`** es el texto de marca ("Powered by Global Score Agent…") y solo aparece en los certificados completos (no en el preview).

### Verificabilidad on-chain (`signature` + `onchain`)

Solo en los certificados **pagados** (`POST /v1/certificates/*`). El preview gratis no los incluye. Ambos bloques se agregan DESPUES de calcular `data_hash`, por lo que no alteran el hash.

- **`signature`** (EIP-712): firma de la wallet del agente sobre el `data_hash` y campos clave del certificado. Se verifica recuperando el firmante y comparando con `signature.signer`. Autenticidad instantanea, sin gas.
- **`receipt`** (solo pago x402 **BNB**): voucher EIP-712 para `claim` del NFT soulbound [`0x4e430fB5…24c7`](https://bscscan.com/address/0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7). Se arma desde el header `PAYMENT-SIGNATURE` (red + pagador). `data_hash` / `delivery_hash` = mismo bytes32 que el certificado (futuro `deliveryHash` AACP TermiX). Pagos Celo/Base no incluyen este campo. El mint BscScan muestra `From: 0x000…0` (acuñación); el gas lo paga el claimant.
- **`onchain`** (ERC-8004 Reputation Registry en Celo): por cada certificado se llama `giveFeedback` desde una wallet monitor dedicada (distinta al owner del `agentId`). El `feedbackHash` transporta el `data_hash` (prueba on-chain de emision) y `value/value_decimals` el monto pagado, de modo que `getSummary(agentId, "certificate_issued")` expone a la vez el conteo de certificados y los ingresos acumulados. Si el anclaje falla, `onchain.status = "failed"` y el certificado igual se entrega firmado.

Verificacion independiente:

- **HTTP (canonica):** `POST /v1/verify` con `{ "tx_hash": "0x..." }` — Edge `walcert-certificate-verify` (BD + Celo + EIP-712); el agente solo hace de fachada.
- **CLI (offline):** `python scripts/verify_certificate.py <cert.json>` (recupera el firmante EIP-712 y confirma el evento `NewFeedback` con `feedbackHash == data_hash`).
