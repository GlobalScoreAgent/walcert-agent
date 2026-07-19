# Walcert — JSON por certificado

Documento de referencia de los payloads HTTP del agente en la fase actual (hot analysis, sin x402 ni Edge).

**Base URL (dev):** `http://127.0.0.1:8001`  
**Método:** `POST /v1/certificates/{certificate_type}`

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

El agente responde siempre con este envoltorio. El detalle del módulo va en `analysis`.

Ese objeto `analysis` es el JSON **semicrudo** que, en la siguiente fase, se enviará a la Edge Function de scoring.

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "<origins|activity|multichain|portfolio>",
  "provider": "<alchemy|moralis|zerion>",
  "analysis": { }
}
```

| `certificate_type` | `provider` |
|--------------------|------------|
| `origins` | `alchemy` |
| `activity` | `alchemy` |
| `multichain` | `moralis` |
| `portfolio` | `zerion` |

---

## 1. Origins (`POST /v1/certificates/origins`)

Provider: Alchemy (`celo-mainnet` + `bnb-mainnet`).

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "origins",
  "provider": "alchemy",
  "analysis": {
    "module": "origins",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "chains_analyzed": [
      {
        "chain": "celo",
        "chain_id": 42220,
        "network": "celo-mainnet",
        "transfers": 2
      },
      {
        "chain": "bsc",
        "chain_id": 56,
        "network": "bnb-mainnet",
        "transfers": 12
      }
    ],
    "networks": ["celo-mainnet", "bnb-mainnet"],
    "analyzed_at": "2026-07-17T19:45:00Z",
    "total_transfers_analyzed": 14,
    "first_funding": {
      "timestamp": "2024-03-12T09:14:22Z",
      "from": "0x28c6c06298d514db089934071355e5743bf21d60",
      "value_usd_estimate": 1250.4,
      "category": "cex",
      "label": "Binance",
      "chain": "bsc",
      "chain_id": 56
    },
    "origin_summary": {
      "cex_percentage": 68.5,
      "bridge_percentage": 12.3,
      "dex_percentage": 9.1,
      "other_percentage": 10.1,
      "unique_senders": 14,
      "mixing_risk": "low",
      "main_origin_type": "cex"
    },
    "top_senders": [
      {
        "address": "0x28c6c06298d514db089934071355e5743bf21d60",
        "label": "Binance",
        "total_value_usd": 1840.2,
        "tx_count": 3
      }
    ],
    "score_inputs": {
      "cex_dependency": 0.68,
      "sender_diversity": 0.72,
      "mixing_signals": 0.15
    }
  }
}
```

Notas:

- `first_funding` puede ser `null` si no hay transfers con timestamp usable.
- `chains_analyzed` solo lista redes con transfers encontrados.

---

## 2. Activity (`POST /v1/certificates/activity`)

Provider: Alchemy (ventana ~7 días, Celo + BNB).

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "activity",
  "provider": "alchemy",
  "analysis": {
    "module": "activity",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "chains_analyzed": [
      {
        "chain": "celo",
        "chain_id": 42220,
        "network": "celo-mainnet",
        "transfers": 5
      }
    ],
    "networks": ["celo-mainnet", "bnb-mainnet"],
    "analyzed_at": "2026-07-17T19:45:00Z",
    "window_days": 7,
    "total_transfers": 5,
    "inflow_count": 2,
    "outflow_count": 3,
    "unique_counterparties": 3,
    "cex_interaction_percentage": 0.0,
    "behavior_signals": {
      "wash_trading_risk": "low",
      "circular_patterns": false,
      "bot_like_activity": false,
      "high_frequency_trading": false
    },
    "top_counterparties": [
      {
        "address": "0x2c8b1d651e5ae42dec1c7b238989e8e369241665",
        "tx_count": 3,
        "direction": "out",
        "label": null
      }
    ],
    "score_inputs": {
      "counterparty_diversity": 0.1,
      "cex_dependency": 0.0,
      "natural_flow_score": 0.55
    }
  }
}
```

---

## 3. Multi-Chain (`POST /v1/certificates/multichain`)

Provider: Moralis (`GET /wallets/{address}/chains`).

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "multichain",
  "provider": "moralis",
  "analysis": {
    "module": "multichain",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "analyzed_at": "2026-07-17T19:45:00Z",
    "total_chains_with_activity": 6,
    "chains": [
      {
        "chain": "eth",
        "chain_id": 1,
        "first_transaction": null,
        "last_transaction": null
      },
      {
        "chain": "base",
        "chain_id": 8453,
        "first_transaction": "2024-02-18T11:05:44Z",
        "last_transaction": "2026-07-16T20:12:55Z"
      },
      {
        "chain": "bsc",
        "chain_id": 56,
        "first_transaction": "2023-11-04T14:22:11Z",
        "last_transaction": "2026-07-15T09:41:03Z"
      }
    ],
    "activity_span_days": 986,
    "score_inputs": {
      "chain_count": 6,
      "activity_consistency": 1.0,
      "longevity_score": 0.88
    }
  }
}
```

Notas:

- Moralis no acepta `celo` en este endpoint; el set default es `eth,base,arbitrum,polygon,optimism,bsc`.
- `first_transaction` / `last_transaction` pueden ser `null`.

---

## 4. Portfolio (`POST /v1/certificates/portfolio`)

Provider: Zerion (`GET /wallets/{address}/positions/`).

```json
{
  "available": true,
  "status": "ok",
  "mode": "hot",
  "certificate_type": "portfolio",
  "provider": "zerion",
  "analysis": {
    "module": "portfolio",
    "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
    "analyzed_at": "2026-07-17T19:45:00Z",
    "total_value_usd": 0.81,
    "liquid_value_usd": 0.81,
    "locked_value_usd": 0.0,
    "liquid_ratio": 100.0,
    "positions_count": 1,
    "category_distribution": {
      "stablecoin": 0.0,
      "bluechip": 100.0,
      "defi_lp": 0.0,
      "meme_or_other": 0.0
    },
    "top_positions": [
      {
        "name": "Celo",
        "symbol": "celo",
        "value_usd": 0.81,
        "category": "bluechip",
        "classification": "liquid"
      }
    ],
    "score_inputs": {
      "portfolio_size_score": 0.0,
      "liquidity_score": 1.0,
      "diversification_score": 0.07,
      "risk_exposure_score": 1.0
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
| origins | `senders[]` (cap 1000) con address, chain, value, tx_count |
| activity | `counterparties[]`, `transfers[]` compacto 7d (`ts,from,to,value,chain`) |
| multichain | posible `celo_merged: true` si Alchemy añade Celo |
| portfolio | `positions[]` ricos (sin `only_simple`); Edge aplica dust/HHI/spam/DeFi |

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

> Nota sobre `provider`: hay dos campos con ese nombre. El `provider` del **envelope** (nivel superior) indica el proveedor de datos (`alchemy|moralis|zerion`). El `provider` dentro de **`certificate`** es el texto de marca ("Powered by Global Score Agent…") y solo aparece en los certificados completos (no en el preview).

### Verificabilidad on-chain (`signature` + `onchain`)

Solo en los certificados **pagados** (`POST /v1/certificates/*`). El preview gratis no los incluye. Ambos bloques se agregan DESPUES de calcular `data_hash`, por lo que no alteran el hash.

- **`signature`** (EIP-712): firma de la wallet del agente sobre el `data_hash` y campos clave del certificado. Se verifica recuperando el firmante y comparando con `signature.signer`. Autenticidad instantanea, sin gas.
- **`onchain`** (ERC-8004 Reputation Registry en Celo): por cada certificado se llama `giveFeedback` desde una wallet monitor dedicada (distinta al owner del `agentId`). El `feedbackHash` transporta el `data_hash` (prueba on-chain de emision) y `value/value_decimals` el monto pagado, de modo que `getSummary(agentId, "certificate_issued")` expone a la vez el conteo de certificados y los ingresos acumulados. Si el anclaje falla, `onchain.status = "failed"` y el certificado igual se entrega firmado.

Verificacion independiente: `python scripts/verify_certificate.py <cert.json>` (recupera el firmante EIP-712 y confirma el evento `NewFeedback` con `feedbackHash == data_hash`).
