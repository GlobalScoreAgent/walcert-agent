# Walcert Agent Certificates (EN)

Walcert Agent is an ERC-8004 agent on **Celo**, built by **Global Score Agent**, that issues **A–F** wallet-maturity certificates through real-time analysis (*hot-analysis*). It keeps no historical store: every certificate is computed on demand from on-chain provider data.

Scoring runs on **Supabase Edge Functions** (one per certificate type) and is enriched with labeled address lists (CEX, bridges, mixers and OFAC sanctions) stored in Supabase.

- **Free preview** (`POST /v1/preview/{type}`): only `origins` and `activity` (Alchemy). Returns the A–F grade only, no metrics or signature, no payment. Rate limit: 8 req/IP per 15 min. `multichain` and `portfolio` → 403 (use the paid endpoint).
- **Full certificate** (`POST /v1/certificates/{type}`): returns the signed certificate (metrics + `data_hash`). Requires an **x402 payment** of **0.05 USDC on Celo mainnet** (gasless EIP-3009 settlement via the `x402.celo.org` facilitator).

All certificate texts (`summary`, `grade_label`, `strengths`, `concerns`) are **bilingual**, shaped as `{ "eng": "...", "esp": "..." }`.

Common grade scale:

| Grade | Label | Meaning |
|-------|-------|---------|
| A | Excellent | Mature, low-risk profile |
| B | Good | Solid profile with minor notes |
| C | Acceptable | Average / mixed profile |
| D | Weak | Risk signals or thin track record |
| F | Poor / High risk | Serious risk (e.g. sanctions/mixer) or no activity |

---

## 1. Origins — Source of funds

**What it evaluates:** where the wallet's funds come from and how clean/diverse that origin is.

**Data sources:**
- Incoming transfers and first funding of the wallet (Alchemy, on Celo and BNB).
- Labeling of sender addresses against the tables `wallets.cex_addresses`, `wallets.bridge_addresses`, `wallets.mixer_addresses` and `wallets.ofac_sanction_addresses` (via the `walcert_lookup_labels` function).

**Key metrics:**
- `cex_percentage`: share of value received from centralized exchanges.
- `bridge_percentage`: share received from bridges.
- `unique_senders`: number of distinct senders (diversity).
- `mixing_risk`: `low` / `medium` / `high` (mixer interaction or single sender).
- `first_funding_age_days`: age of the first funding.
- `sanctions_hit`: match against an OFAC-sanctioned address.

**Grading rules (summary):**
- **F:** OFAC match, or `mixing_risk = high`.
- **A:** `cex ≤ 40%`, `unique_senders ≥ 10`, `mixing = low` and age ≥ 365 days.
- **B:** `cex ≤ 70%`, `unique_senders ≥ 5` and `mixing = low`.
- **D:** `mixing = medium`, or heavy CEX dependency with very low diversity.
- **C:** everything else.

---

## 2. Activity — Recent activity

**What it evaluates:** recent behavior (~7-day window): who the wallet transacts with, whether there are *wash trading* signals or circular patterns, and exposure to CEX/mixers/OFAC.

**Data sources:**
- Recent transfers and counterparties (Alchemy).
- Counterparty labeling against the same `wallets.*` tables.
- Wash-trading / circular-pattern heuristics computed inside the Edge Function from the transfer series (bidirectional pairs, temporal ping-pong, and A→B→A cycles).

**Key metrics:**
- `unique_counterparties`: distinct counterparties.
- `cex_interaction_percentage`: share of activity with CEX.
- `wash_trading_risk`: `low` / `medium` / `high`.
- `circular_patterns`: boolean (cycles/ping-pong detected).
- `bidirectional_pair_share`: volume share in bidirectional pairs.
- `sanctions_hit`, `mixer_hit`.

**Grading rules (summary):**
- **F:** OFAC match, or `wash_trading_risk = high`.
- **D:** circular patterns with medium risk, or mixer interaction, or `unique_counterparties < 3`, or `cex > 60%`.
- **A:** `unique_counterparties ≥ 25`, `wash = low` and no circular patterns.
- **B:** `unique_counterparties ≥ 12` and `wash = low`.
- **C:** everything else.

---

## 3. Multi-Chain — Multi-network presence

**What it evaluates:** how many networks the wallet operates on and for how long (multi-chain consistency and longevity).

**Data sources:**
- Active chains and activity time window (Moralis `getWalletActiveChains`).
- **Celo** activity provided by Alchemy and merged into the result (Celo is not covered by Moralis).

**Key metrics:**
- `total_chains_with_activity`: number of networks with real activity.
- `activity_span_days`: days between first and last activity.
- `main_chains`: main detected networks.

**Grading rules (summary):**
- **A:** ≥ 4 networks and span ≥ 365 days.
- **B:** ≥ 3 networks and span ≥ 180 days.
- **C:** ≥ 2 networks.
- **D:** 1 network with span ≥ 30 days.
- **F:** no meaningful multi-network activity.

---

## 4. Portfolio — Portfolio composition

**What it evaluates:** the quality of the current portfolio: size, liquidity, diversification and speculative exposure.

**Data sources:**
- Portfolio positions (Zerion), including tokens, stablecoins, bluechips and DeFi/LP positions.

**Key metrics:**
- `total_value_usd`: estimated total value.
- `liquid_ratio`: liquid (non-locked) percentage.
- `category_distribution`: distribution by category (stablecoin, bluechip, defi_lp, meme_or_other).
- `concentration`: `top1_share` (weight of the largest asset) and `hhi` (Herfindahl-Hirschman index).
- `defi_exposure_pct`: DeFi/LP exposure.
- `dust_filtered_count` / `spam_filtered_count`: positions discarded as dust or spam/unpriced.

**Grading rules (summary):**
- **F:** value < $10, or meme-dominated (> 85%) with value < $500.
- **D:** value < $100, or memes > 70%, or top-1 concentration > 0.92.
- **A:** value ≥ $10,000, liquid ≥ 60%, memes ≤ 15%, top-1 ≤ 0.55 and HHI ≤ 0.4.
- **B:** value ≥ $2,000, liquid ≥ 50%, memes ≤ 30% and top-1 ≤ 0.7.
- **C:** everything else.

---

## Output example (full certificate)

```json
{
  "certificate_id": "d431f0a7-129d-4e20-8ba7-c88043d80815",
  "type": "ORIGINS",
  "version": "1.0",
  "wallet": "0x1822438e03542b3a31cd39f434fbd7f0b9eaf7bd",
  "chain_id": 42220,
  "analyzed_at": "2026-07-18T05:26:39Z",
  "analysis_mode": "hot",
  "issuer": { "name": "Walcert Agent", "agent_id": "9699" },
  "grade": "A",
  "grade_label": { "eng": "Excellent", "esp": "Excelente" },
  "summary": { "eng": "Funding origins show ...", "esp": "Los orígenes muestran ..." },
  "details": { "cex_percentage": 12.3, "unique_senders": 14, "mixing_risk": "low" },
  "strengths": [
    { "eng": "Low mixing risk", "esp": "Bajo riesgo de mixing" }
  ],
  "concerns": [],
  "data_hash": "0x..."
}
```

`data_hash` is the SHA-256 of the canonical certificate (excluding the hash itself), so integrity can be verified.

## On-chain verifiability (paid certificates)

Paid certificates (`POST /v1/certificates/*`) add two fields after `data_hash` (they do not change the hash):

- **`signature`** — an EIP-712 signature by the agent's wallet over the `data_hash`. Anyone can recover the signer and confirm it matches `signature.signer`. Instant, gasless authenticity.
- **`onchain`** — a per-certificate anchor on the ERC-8004 Reputation Registry on Celo (`0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`). For each issuance the agent calls `giveFeedback` from a dedicated monitor wallet (distinct from the agent's owner). The `feedbackHash` carries the `data_hash` (on-chain proof of issuance) and `value`/`value_decimals` carry the amount paid, so `getSummary(agentId, "certificate_issued")` returns both the certificate count and cumulative revenue. If anchoring fails, `onchain.status = "failed"` and the signed certificate is still delivered.

Independent verification: `python scripts/verify_certificate.py <cert.json>` recovers the EIP-712 signer and confirms the `NewFeedback` event with `feedbackHash == data_hash`.

See also: [certificate-json-schemas.md](certificate-json-schemas.md) and [edge-function-security.md](edge-function-security.md).
