# Certificados Walcert Agent (ES)

Walcert Agent es un agente ERC-8004 en **Celo**, desarrollado por **Global Score Agent**, que emite certificados de madurez de wallets con nota **A–F** mediante análisis en tiempo real (*hot-analysis*). No almacena históricos: cada certificado se calcula en el momento a partir de datos on-chain de los proveedores.

El scoring corre en **Supabase Edge Functions** (una por tipo de certificado) y se enriquece con listas de direcciones etiquetadas (CEX, bridges, mixers y sanciones OFAC) almacenadas en Supabase.

- **Preview gratuito** (`POST /v1/preview/{tipo}`): solo `origins` y `activity` (Alchemy). Devuelve la nota A–F, sin métricas ni firma, sin pago. Rate limit: 8 req/IP cada 15 min. `multichain` y `portfolio` → 403 (usar el endpoint pagado).
- **Certificado completo** (`POST /v1/certificates/{tipo}`): devuelve el certificado firmado (métricas + `data_hash`). Requiere **pago x402** de **0,05 USDC en Celo mainnet** (liquidación gasless EIP-3009 vía el facilitador `x402.celo.org`).

Todos los textos del certificado (`summary`, `grade_label`, `strengths`, `concerns`) son **bilingües** con la forma `{ "eng": "...", "esp": "..." }`.

Escala común de notas:

| Nota | Etiqueta | Significado |
|------|----------|-------------|
| A | Excelente | Perfil maduro y de bajo riesgo |
| B | Bueno | Perfil sólido con observaciones menores |
| C | Aceptable | Perfil promedio / mixto |
| D | Débil | Señales de riesgo o poca trayectoria |
| F | Deficiente / Alto riesgo | Riesgo grave (p. ej. sanciones/mixer) o sin actividad |

**Fórmulas en prod (2026-07-27):**

| Tipo | `formula_version` | Cert `version` | Canal |
|------|-------------------|----------------|-------|
| Origins | `origins-v2.2` | `2.0` | público + Summit |
| Activity | `activity-v2.1` | `2.0` | público + Summit |
| Multichain | `multichain-v1.5` | `1.5` | público + Summit |
| Multichain v2 | `multichain-v2.1` | `2.0` | **solo Summit** |
| Portfolio | `portfolio-v2.2` | `2.0` | público + Summit |

---

## 1. Origins — Origen de los fondos

**Qué evalúa:** de dónde provienen los fondos de la wallet y qué tan limpio/diverso es ese origen.

**Versión:** `origins-v2.2` (certificado `version: "2.0"`). Edge canónico: `main_origin_type` = argmax de categorías; HHI/top1 sobre inflows **priced**; `priced_coverage_pct` sobre inflows **value-relevant** (native/ERC-20 amount>0; NFTs fuera del denominador); concentración extrema bloquea A/B.

**Fuentes de datos:**
- Hasta **500 transferencias entrantes por red** (Alchemy, orden ascendente histórico).
- Redes = `erc_8004.chains` con `is_active` y `subdomain_alchemy` (fallback: `ALCHEMY_NETWORKS`).
- Pricing USD: DefiLlama histórico (majors), stables = $1, spot DexScreener, o `null`.
- Labels vía `walcert_lookup_labels` (CEX / bridge / mixer / OFAC).

**Flujo (prod):** el agente enriquece `analysis` (Alchemy + DefiLlama) → Edge `walcert-certificate-origins` aplica labels + 9 señales + nota. Edge **no** llama Alchemy ni DefiLlama.

**Señales (9) — valores en `certificate.details`:**

| # | Señal | Campo |
|---|--------|--------|
| 1 | % por categoría (CEX, bridge, mixer, OFAC, airdrop, orgánico…) | `category_percentages` |
| 2 | Remitentes únicos | `unique_senders` |
| 3 | Concentración HHI (USD priced) | `hhi` |
| 4 | Top-1 / top-3 share | `concentration` |
| 5 | Calidad de CEX | `cex_quality` |
| 6 | Patrón temporal de funding | `temporal_funding` |
| 7 | Exposición mixer / OFAC | `direct_exposure`, `mixing_risk`, `sanctions_hit` |
| 8 | Orgánico vs sintético (NFT / airdrop) | `organic_vs_synthetic` |
| 9 | Antigüedad del primer funding | `first_funding_age_days` |

**Coverage value-relevant (v2.2):** inflows `external`/`erc20` con `amount > 0` (excluye NFT y amount=0). Campos: `value_relevant_inflows`, `value_relevant_priced`, `value_relevant_unpriced`, `priced_coverage_pct`, `hhi_value_relevant_priced`. El **grade** usa HHI/top1 sobre USD priced; el summary explica coverage sobre el denominador value-relevant.

**Campos legacy (compatibilidad):** `main_origin_type`, `cex_percentage`, `bridge_percentage`.

**Explicabilidad (raíz del certificado):** `formula_version: "origins-v2.2"`, `grade_breakdown` (regla aplicada + condiciones), `inputs_hash`. El agente sincroniza `analysis.origin_summary` desde el certificado tras Edge.

**Pricing USD (agente):** `stable` ($1), `historical` (DefiLlama por día UTC), `spot` (DexScreener), `none` (`usd: null`, excluido de % y HHI). Contadores: `priced_inflows`, `unpriced_inflows`, `total_value_usd_priced`.

**Reglas de nota (`subject_type` default `entity`, orden F→A→B→D→C):**
- **F:** OFAC o `mixing_risk = high`.
- **A:** `cex ≤ 40%`, `unique_senders ≥ 10`, `mixing = low`, antigüedad ≥ 365 días, **`top1_pct ≤ 60`**, **`hhi ≤ 0.55`**.
- **B:** `cex ≤ 70%`, `unique_senders ≥ 5`, `mixing = low`, **`top1_pct ≤ 80`**, **`hhi ≤ 0.70`**.
- **D:** `mixing = medium`, o CEX > 85% con ≤ 2 senders, o **`top1_pct ≥ 95`**, o **`hhi ≥ 0.90`**.
- **C:** resto.

**Narrativa:** concern si `top1 ≥ 70%` o `hhi ≥ 0.70`. Strength de diversidad de senders solo si HHI ≤ 0.55.

**Fuera de alcance (v2):** multi-hop, Sepolia/IPFS ORIGO, Public API / WAMI.

---

## 2. Activity — Actividad reciente

**Qué evalúa:** el comportamiento reciente (ventana de **15 días**): con quién opera, concentración, wash/circular, bot-like, y exposición a CEX/mixers/OFAC.

**Versión:** `activity-v2.1` (certificado `version: "2.0"`). Ventana **15 días**. HHI>0.70 → D; 0.45–0.70 bloquea A/B (cae en C).

**Flujo (prod):** el agente enriquece `analysis` (Alchemy 15d in+out + DefiLlama) → Edge `walcert-certificate-activity` aplica labels + señales + nota. Edge **no** llama Alchemy ni DefiLlama.

**Fuentes de datos:**
- Hasta **500 transferencias por dirección (in|out) y por red** (Alchemy, orden desc).
- Redes = `erc_8004.chains` con Alchemy (fallback `ALCHEMY_NETWORKS`), igual que Origins.
- Pricing USD híbrido: HHI / net-gross en USD priced; CEX reporta `% valor` y `% txs`.
- Labels vía `walcert_lookup_labels` (CEX / bridge / mixer / OFAC).

**Señales (en `certificate.details`):**
1. `unique_counterparties`
2. `counterparty_hhi`
3. `cex_interaction_pct_value` + `cex_interaction_pct_txs` (+ legacy `cex_interaction_percentage`)
4. `reciprocity_ratio`
5. `net_to_gross_ratio`
6. `velocity_txs_per_day`
7. `burstiness_score`
8. `token_diversity`
9. `wash_trading_risk` / `circular_patterns` / `wash_score`
10. `bot_like_score`
11. `nft_transfer_pct` / `fungible_transfer_pct` / `nft_vs_fungible_ratio`

**Explicabilidad:** `formula_version: "activity-v2.1"`, `grade_breakdown`, `inputs_hash`.

**Reglas de nota (orden F→D→A→B→C):**
- **F:** OFAC, wash high, `bot_like ≥ 0.8`, o `wash_score ≥ 0.75`.
- **D:** mixer, circular+wash medium, unique &lt; 3, CEX &gt; 60%, **HHI &gt; 0.70**, o bot ≥ 0.55.
- **A:** unique ≥ 25, wash low, sin circular, HHI ≤ 0.25, bot &lt; 0.35, velocity ≤ 40 txs/día.
- **B:** unique ≥ 12, wash low, HHI ≤ 0.35, bot &lt; 0.5.
- **C:** resto (incl. `0.45 < HHI ≤ 0.70` si no aplica otra regla).

**Narrativa:** strength “diversidad de contrapartes” solo si unique ≥ 10 **y** HHI ≤ 0.35; concern si HHI > 0.45 (concentración de volumen).

**Fuera de alcance:** ventanas 30/90d; labels DEX routers / known bots (sin catálogo aún).

---

## 3. Multi-Chain — Presencia multi-red

**Qué evalúa:** footprint y longevidad multi-red (no intensidad — Moralis no da txs/volumen por chain).

**Versión:** `multichain-v1.5` (certificado `version: "1.5"`).

**Flujo (prod):** el agente enriquece `analysis` (Moralis + merge Celo opcional) → Edge `walcert-certificate-multichain` recomputa señales desde `chains[]` (canónico) + grade.

**Fuentes de datos:**
- Moralis `GET /wallets/{address}/chains` (misma llamada que v1).
- **Celo** vía Alchemy cuando falta en Moralis.
- Lista core versionada (`CORE_ECOSYSTEM_LIST_VERSION`): eth, base, celo, arbitrum, optimism, polygon.

**Señales (en `certificate.details`):** chain count, span global, activas 30d/90d, dormant ratio, consistency, recency, core ecosystems, footprint concentration (HHI de span_days), flags de longevidad por chain. Legacy: `main_chains`, `total_chains_with_activity`, `activity_span_days`.

**Explicabilidad:** `formula_version: "multichain-v1.5"`, `grade_breakdown`, `inputs_hash`.

**Reglas de nota (orden F→D→A→B→C):**
- **F:** 0 chains, o 1 chain con span &lt; 30d, o 1 chain sin actividad 90d y span &lt; 90d.
- **D:** 1 chain, o mayormente dormidas (dormant_ratio &gt; 0.75 y sin 30d), o 2 chains con span/consistency débiles.
- **A:** ≥4 chains, span ≥365, consistency ≥0.50, ≥2 core, ≥2 activas en 90d, HHI footprint ≤0.70, recency ≥0.35.
- **B:** ≥3 chains, span ≥180, ≥1 core, consistency ≥0.40, ≥1 activa en 90d.
- **C:** resto.

**Fuera de alcance (endpoint público):** intensidad GoldRush (ver Multichain v2 Summit abajo).

### Solo Summit — Multichain v2 (GoldRush)

**No es endpoint público del agente** (no agent card, no x402). Requiere auth Summit.

```http
POST /v1/summit/certificates/multichain-v2
Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
X-Walcert-Marketplace: bsg2026
```

**Versión:** `multichain-v2.1` (certificado `version: "2.0"`, `type: MULTICHAIN`).

**Datos:** GoldRush `/activity/` + `transactions_summary` en top 6 mainnets prioritarios (`GOLDRUSH_API_KEY` en env EC2).

**Señales:** footprint (mainnets, span, recency, consistency, dormant, core) + intensity (`total_tx_count`, `tx_hhi`, weighted activity, primary chain, gas). `ecosystem_count` = familias de chain (`eth/base/arb/op → ethereum`, etc.), no `category_label` crudo.

**Reglas de nota (orden F→D→A→B→C):**
- **F:** 0 mainnets, solo testnets, o 1 mainnet con span &lt; 30 y total_tx &lt; 5.
- **D:** 1 mainnet, o (dormant_ratio &gt; 0.75 y active_30d = 0), o total_tx = 0 en sample.
- **A:** mainnets ≥ 5, ecosystems ≥ 3, span ≥ 365, consistency ≥ 0.50, recency ≥ 0.35, core ≥ 2, total_tx ≥ 50, tx_hhi ≤ 0.70.
- **B:** mainnets ≥ 3, ecosystems ≥ 2, span ≥ 180, consistency ≥ 0.40, total_tx ≥ 15.
- **C:** resto.

**Sin Summit:** HTTP 403 `summit_only`.

---

## 4. Portfolio — Composición del portafolio

**Qué evalúa:** calidad económica de la cartera actual: tamaño, liquidez, diversificación, higiene de dust y exposición especulativa / DeFi.

**Versión:** `portfolio-v2.2` (certificado `version: "2.0"`). Summary usa `total_value_usd_credible` (excluye valuaciones absurdas >$50M); raw post-filtro permanece en `details`.

**Flujo (prod):** el agente enriquece `analysis` (Zerion + classify) → Edge `walcert-certificate-portfolio` recomputa señales desde `positions[]` (canónico) + grade.

**Fuentes de datos:**
- Zerion `GET /wallets/{address}/positions`.
- Listas versionadas (`TOKEN_TIER_LIST_VERSION`, p.ej. `2026-07-26`): STABLE / BLUECHIP / HIGH_RISK / NATIVE_GAS (+ protocolos bluechip).

**Señales (en `certificate.details`):** valor total usable, liquid/locked + `liquid_ratio`, `holdings_hhi`, `effective_positions`, shares stable/bluechip/meme, split DeFi/LP, `dust_ratio`, `protocol_exposure_count`, `native_gas_buffer_*`, `locked_commitment_score`, counts dust/spam.

**Dual totals (v2.2):**
- `total_value_usd` / `liquid_value_usd` = post spam/dust (usable).
- `total_value_usd_credible` / `liquid_value_usd_credible` = excluye valuaciones **absurdas** (`value > $50M`, o extremo vs mediana si hay ≥2 posiciones).
- Summary Summit usa **credible**; si credible = 0, dice “unavailable” y menciona raw solo como post-filter.
- Campos: `absurd_filtered_count`, `absurd_value_usd_excluded`, `positions_credible`.

**Umbrales:** dust `< $1`; posición efectiva = `value_usd ≥ max($10, 1% del total)`.

**Explicabilidad:** `formula_version: "portfolio-v2.2"`, `grade_breakdown`, `inputs_hash`. Grade sobre universo **usable** (no cambia por filtro absurd de display).

**Reglas de nota (orden F→D→A→B→C):**
- **F:** total &lt; $10, o (meme &gt; 85% y total &lt; $500), o `effective_positions == 0`.
- **D:** total &lt; $100, o meme &gt; 70%, o HHI &gt; 0,70, o dust_ratio &gt; 0,50, o (effective ≤ 1 y total &lt; $1k), o **spam_dominated** (`spam_filtered ≥ 50` y `positions_used ≤ 1`).
- **A:** total ≥ $10k, líquido ≥ 60%, HHI ≤ 0,35, meme ≤ 15%, effective ≥ 5, top1 ≤ 0,55, **spam_ratio &lt; 0.8**.
- **B:** total ≥ $2k, líquido ≥ 50%, HHI ≤ 0,50, meme ≤ 30%, effective ≥ 3, **spam_ratio &lt; 0.8**.
- **C:** resto.

**Fuera de alcance:** histórico/snapshots, PnL, cambio de proveedor, motor risk-tier más allá de listas versionadas.

---

## Ejemplo de salida (certificado completo)

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

El campo `data_hash` es el SHA-256 del certificado canónico (sin el propio hash), y permite verificar su integridad.

## Verificabilidad on-chain (certificados pagados)

Los certificados pagados (`POST /v1/certificates/*`) agregan dos campos después de `data_hash` (no alteran el hash):

- **`signature`** — firma EIP-712 de la wallet del agente sobre el `data_hash`. Cualquiera puede recuperar el firmante y confirmar que coincide con `signature.signer`. Autenticidad instantánea y sin gas.
- **`onchain`** — anclaje por certificado en el ERC-8004 Reputation Registry de Celo (`0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`). Por cada emisión el agente llama `giveFeedback` desde una wallet monitor dedicada (distinta al owner del agente). El `feedbackHash` transporta el `data_hash` (prueba on-chain de emisión) y `value`/`value_decimals` el monto pagado, de modo que `getSummary(agentId, "certificate_issued")` devuelve a la vez el conteo de certificados y los ingresos acumulados. Si el anclaje falla, `onchain.status = "failed"` y el certificado igual se entrega firmado.

Verificación independiente:

- **HTTP (canónica):** `POST /v1/verify` con `{ "tx_hash": "0x..." }`. El agente es fachada; la Edge `walcert-certificate-verify` hace lookup en BD + confirma `NewFeedback` en Celo + EIP-712.
- **CLI (offline):** `python scripts/verify_certificate.py <cert.json>` recupera el firmante EIP-712 y confirma el evento `NewFeedback` con `feedbackHash == data_hash`.

Ver también: [certificate-json-schemas.md](certificate-json-schemas.md) y [edge-function-security.md](edge-function-security.md).
