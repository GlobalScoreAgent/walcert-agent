# Walcert Agent Certificates (EN)

Walcert Agent is an ERC-8004 agent on **Celo**, built by **Global Score Agent**, that issues **A–F** wallet-maturity certificates through real-time analysis (*hot-analysis*). It keeps no historical store: every certificate is computed on demand from on-chain provider data.

Scoring runs on **Supabase Edge Functions** (one per certificate type) and is enriched with labeled address lists (CEX, bridges, mixers and OFAC sanctions) stored in Supabase.

- **Free preview** (`POST /v1/preview/{type}`): only `origins` and `activity` (Alchemy). Returns the A–F grade only, no metrics or signature, no payment. Rate limit: 8 req/IP per 15 min. `multichain` and `portfolio` → 403 (use the paid endpoint).
- **Full certificate** (`POST /v1/certificates/{type}`): returns the signed certificate (metrics + `data_hash`). Requires an **x402 payment** of **0.05 USDC** on **Celo**, **Base**, or **BNB** (`eip155:56`, Binance-Peg USDC, Permit2 via Dexter). Celo/Base: EIP-3009. BNB: one-time Permit2 `approve`; the 200 includes `certificate.receipt` (voucher for the soulbound NFT `claim`). Mint gas is paid in **BNB by the client** (not taken from the $0.05). Celo `giveFeedback` is unchanged.

All certificate texts (`summary`, `grade_label`, `strengths`, `concerns`) are **bilingual**, shaped as `{ "eng": "...", "esp": "..." }`.

Common grade scale:

| Grade | Label | Meaning |
|-------|-------|---------|
| A | Excellent | Mature, low-risk profile |
| B | Good | Solid profile with minor notes |
| C | Acceptable | Average / mixed profile |
| D | Weak | Risk signals or thin track record |
| F | Poor / High risk | Serious risk (e.g. sanctions/mixer) or no activity |

**Production formulas (2026-07-27):**

| Type | `formula_version` | Cert `version` | Channel |
|------|-------------------|----------------|---------|
| Origins | `origins-v2.2` | `2.0` | public + Summit |
| Activity | `activity-v2.1` | `2.0` | public + Summit |
| Multichain | `multichain-v1.5` | `1.5` | public + Summit |
| Multichain v2 | `multichain-v2.1` | `2.0` | **Summit-only** |
| Portfolio | `portfolio-v2.2` | `2.0` | public + Summit |

---

## 1. Origins — Source of funds

**What it evaluates:** where the wallet's funds come from and how clean/diverse that origin is.

**Version:** `origins-v2.2` (certificate `version: "2.0"`). Edge-canonical: `main_origin_type` = category argmax; HHI/top1 over **priced** inflows; `priced_coverage_pct` over **value-relevant** inflows (native/ERC-20 amount>0; NFTs out of denominator); extreme concentration blocks A/B.

**Data sources:**
- Up to **500 inbound transfers per network** (Alchemy, ascending historical order).
- Networks from `erc_8004.chains` where `is_active` and `subdomain_alchemy` is set (fallback: `ALCHEMY_NETWORKS`).
- USD pricing: DefiLlama historical (majors), stables = $1, DexScreener spot, or `null`.
- Labels via `walcert_lookup_labels` (CEX / bridge / mixer / OFAC).

**Flow (prod):** the agent enriches `analysis` (Alchemy + DefiLlama) → Edge `walcert-certificate-origins` applies labels + 9 signals + grade. Edge does **not** call Alchemy or DefiLlama.

**Signals (9) — values in `certificate.details`:**

| # | Signal | Field |
|---|--------|--------|
| 1 | Category % (CEX, bridge, mixer, OFAC, airdrop, organic…) | `category_percentages` |
| 2 | Unique senders | `unique_senders` |
| 3 | HHI (priced USD) | `hhi` |
| 4 | Top-1 / top-3 share | `concentration` |
| 5 | CEX quality | `cex_quality` |
| 6 | Temporal funding pattern | `temporal_funding` |
| 7 | Mixer / OFAC exposure | `direct_exposure`, `mixing_risk`, `sanctions_hit` |
| 8 | Organic vs synthetic (NFT / airdrop) | `organic_vs_synthetic` |
| 9 | First-funding age | `first_funding_age_days` |

**Legacy fields:** `main_origin_type`, `cex_percentage`, `bridge_percentage`.

**Value-relevant coverage (v2.2):** inflows `external`/`erc20` with `amount > 0` (excludes NFT and amount=0). Fields: `value_relevant_inflows`, `value_relevant_priced`, `value_relevant_unpriced`, `priced_coverage_pct`, `hhi_value_relevant_priced`. **Grade** uses HHI/top1 on priced USD; summary explains coverage on the value-relevant denominator.

**Explainability (certificate root):** `formula_version: "origins-v2.2"`, `grade_breakdown` (applied rule + conditions), `inputs_hash`. Agent syncs `analysis.origin_summary` from the certificate after Edge.

**USD pricing (agent):** `stable` ($1), `historical` (DefiLlama UTC day), `spot` (DexScreener), `none` (`usd: null`, excluded from % and HHI). Counters: `priced_inflows`, `unpriced_inflows`, `total_value_usd_priced`.

**Grading rules (`subject_type` default `entity`, order F→A→B→D→C):**
- **F:** OFAC or `mixing_risk = high`.
- **A:** `cex ≤ 40%`, `unique_senders ≥ 10`, `mixing = low`, age ≥ 365 days, **`top1_pct ≤ 60`**, **`hhi ≤ 0.55`**.
- **B:** `cex ≤ 70%`, `unique_senders ≥ 5`, `mixing = low`, **`top1_pct ≤ 80`**, **`hhi ≤ 0.70`**.
- **D:** `mixing = medium`, or CEX > 85% with ≤ 2 senders, or **`top1_pct ≥ 95`**, or **`hhi ≥ 0.90`**.
- **C:** everything else.

**Narrative:** concern if `top1 ≥ 70%` or `hhi ≥ 0.70`. Sender-diversity strength only if HHI ≤ 0.55.

**Out of scope (v2):** multi-hop, Sepolia/IPFS ORIGO, Public API / WAMI.

---

## 2. Activity — Recent activity

**What it evaluates:** recent behavior (**15-day** window): counterparties, concentration, wash/circular, bot-like patterns, and CEX/mixer/OFAC exposure.

**Version:** `activity-v2.1` (certificate `version: "2.0"`).

**Flow (prod):** agent enriches `analysis` (Alchemy 15d in+out + DefiLlama) → Edge `walcert-certificate-activity` applies labels + signals + grade.

**Data sources:**
- Up to **500 transfers per direction (in|out) per network** (Alchemy, desc).
- Networks from `erc_8004.chains` with Alchemy (fallback `ALCHEMY_NETWORKS`), same as Origins.
- Hybrid USD pricing: HHI / net-gross on priced USD; CEX reports value % and txs %.
- Labels via `walcert_lookup_labels`.

**Signals (in `certificate.details`):** unique counterparties, HHI, CEX value+txs %, reciprocity, net/gross, velocity, burstiness, token diversity, wash score, bot-like, NFT vs fungible ratio.

**Explainability:** `formula_version: "activity-v2.1"`, `grade_breakdown`, `inputs_hash`. Window **15d**. HHI>0.70 → D; 0.45–0.70 blocks A/B (falls to C).

**Grading rules (order F→D→A→B→C):**
- **F:** OFAC, wash high, `bot_like ≥ 0.8`, or `wash_score ≥ 0.75`.
- **D:** mixer, circular+wash medium, unique &lt; 3, CEX &gt; 60%, **HHI &gt; 0.70**, or bot ≥ 0.55.
- **A:** unique ≥ 25, wash low, no circular, HHI ≤ 0.25, bot &lt; 0.35, velocity ≤ 40 txs/day.
- **B:** unique ≥ 12, wash low, HHI ≤ 0.35, bot &lt; 0.5.
- **C:** everything else (incl. `0.45 < HHI ≤ 0.70` when no other rule applies).

**Narrative:** “counterparty diversity” strength only if unique ≥ 10 **and** HHI ≤ 0.35; concern if HHI > 0.45 (volume concentration).

**Out of scope:** 30/90d windows; DEX router / known-bot labels (no catalog yet).

---

## 3. Multi-Chain — Multi-network presence

**What it evaluates:** multi-network footprint and longevity (not intensity — Moralis has no tx/volume per chain).

**Version:** `multichain-v1.5` (certificate `version: "1.5"`).

**Flow (prod):** agent enriches `analysis` (Moralis chains + optional Celo Alchemy merge) → Edge `walcert-certificate-multichain` recomputes signals from `chains[]` (canonical) + grade.

**Data sources:**
- Moralis `GET /wallets/{address}/chains` (same call as v1).
- **Celo** via Alchemy merge when missing from Moralis.
- Versioned core list (`CORE_ECOSYSTEM_LIST_VERSION`): eth, base, celo, arbitrum, optimism, polygon.

**Signals (in `certificate.details`):** chain count, global span, active 30d/90d, dormant ratio, consistency, recency, core ecosystems, footprint concentration (HHI of span_days), per-chain longevity flags. Legacy: `main_chains`, `total_chains_with_activity`, `activity_span_days`.

**Explainability:** `formula_version: "multichain-v1.5"`, `grade_breakdown`, `inputs_hash`.

**Grading rules (order F→D→A→B→C):**
- **F:** 0 chains, or 1 chain with span &lt; 30d, or 1 chain with no 90d activity and span &lt; 90d.
- **D:** 1 chain, or mostly dormant (dormant_ratio &gt; 0.75 and no 30d), or 2 chains with weak span/consistency.
- **A:** ≥4 chains, span ≥365, consistency ≥0.50, ≥2 core ecosystems, ≥2 active in 90d, footprint HHI ≤0.70, recency ≥0.35.
- **B:** ≥3 chains, span ≥180, ≥1 core, consistency ≥0.40, ≥1 active in 90d.
- **C:** everything else.

**Out of scope (public endpoint):** GoldRush intensity (see Summit-only Multichain v2 below).

### Summit-only — Multichain v2 (GoldRush)

**Not a public agent endpoint** (not in agent card, not x402). Requires Summit auth.

```http
POST /v1/summit/certificates/multichain-v2
Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
X-Walcert-Marketplace: bsg2026
```

**Version:** `multichain-v2.1` (certificate `version: "2.0"`, `type: MULTICHAIN`).

**Data:** GoldRush `/activity/` + `transactions_summary` on top 6 priority mainnets (`GOLDRUSH_API_KEY` on EC2 env).

**Signals:** footprint (mainnets, span, recency, consistency, dormant, core) + intensity (`total_tx_count`, `tx_hhi`, weighted activity, primary chain, gas). `ecosystem_count` = chain families (`eth/base/arb/op → ethereum`, etc.), not raw GoldRush `category_label`.

**Grading rules (order F→D→A→B→C):**
- **F:** 0 mainnets, testnets-only, or 1 mainnet with span &lt; 30 and total_tx &lt; 5.
- **D:** 1 mainnet, or (dormant_ratio &gt; 0.75 and active_30d = 0), or total_tx = 0 in sample.
- **A:** mainnets ≥ 5, ecosystems ≥ 3, span ≥ 365, consistency ≥ 0.50, recency ≥ 0.35, core ≥ 2, total_tx ≥ 50, tx_hhi ≤ 0.70.
- **B:** mainnets ≥ 3, ecosystems ≥ 2, span ≥ 180, consistency ≥ 0.40, total_tx ≥ 15.
- **C:** everything else.

**Non-Summit callers:** HTTP 403 `summit_only`.

---

## 4. Portfolio — Portfolio composition

**What it evaluates:** economic quality of the current portfolio: size, liquidity, diversification, dust hygiene, and speculative / DeFi exposure.

**Version:** `portfolio-v2.2` (certificate `version: "2.0"`). Summary uses `total_value_usd_credible` (excludes absurd valuations >$50M); raw post-filter stays in `details`.

**Flow (prod):** agent enriches `analysis` (Zerion positions + classify) → Edge `walcert-certificate-portfolio` recomputes signals from `positions[]` (canonical) + grade.

**Data sources:**
- Zerion `GET /wallets/{address}/positions` (tokens, stables, bluechips, DeFi/LP).
- Versioned tier lists (`TOKEN_TIER_LIST_VERSION`, e.g. `2026-07-26`): STABLE / BLUECHIP / HIGH_RISK / NATIVE_GAS (+ bluechip protocols).

**Signals (in `certificate.details`):** usable total, liquid/locked + `liquid_ratio`, `holdings_hhi`, `effective_positions`, stable/bluechip/meme shares, DeFi/LP split, `dust_ratio`, `protocol_exposure_count`, `native_gas_buffer_*`, `locked_commitment_score`, dust/spam counts.

**Dual totals (v2.2):**
- `total_value_usd` / `liquid_value_usd` = post spam/dust (usable).
- `total_value_usd_credible` / `liquid_value_usd_credible` = excludes **absurd** valuations (`value > $50M`, or extreme vs median when ≥2 positions).
- Summit summary uses **credible**; if credible = 0, says “unavailable” and mentions raw only as post-filter.
- Fields: `absurd_filtered_count`, `absurd_value_usd_excluded`, `positions_credible`.

**Thresholds:** dust filter `< $1`; effective position = `value_usd ≥ max($10, 1% of total)`.

**Explainability:** `formula_version: "portfolio-v2.2"`, `grade_breakdown`, `inputs_hash`. Grade on **usable** universe (display absurd filter does not change grade).

**Grading rules (order F→D→A→B→C):**
- **F:** total &lt; $10, or (meme &gt; 85% and total &lt; $500), or `effective_positions == 0`.
- **D:** total &lt; $100, or meme &gt; 70%, or HHI &gt; 0.70, or dust_ratio &gt; 0.50, or (effective ≤ 1 and total &lt; $1k), or **spam_dominated** (`spam_filtered ≥ 50` and `positions_used ≤ 1`).
- **A:** total ≥ $10k, liquid ≥ 60%, HHI ≤ 0.35, meme ≤ 15%, effective ≥ 5, top1 ≤ 0.55, **spam_ratio &lt; 0.8**.
- **B:** total ≥ $2k, liquid ≥ 50%, HHI ≤ 0.50, meme ≤ 30%, effective ≥ 3, **spam_ratio &lt; 0.8**.
- **C:** everything else.

**Out of scope:** portfolio history/snapshots, PnL, provider change, full risk-tier engine beyond versioned lists.

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

Independent verification:

- **HTTP (canonical):** `POST /v1/verify` with `{ "tx_hash": "0x..." }`. The agent is a facade; Edge `walcert-certificate-verify` does DB lookup + Celo `NewFeedback` + EIP-712.
- **CLI (offline):** `python scripts/verify_certificate.py <cert.json>` recovers the EIP-712 signer and confirms the `NewFeedback` event with `feedbackHash == data_hash`.

See also: [certificate-json-schemas.md](certificate-json-schemas.md) and [edge-function-security.md](edge-function-security.md).
