# Certificados Walcert Agent (ES)

Walcert Agent es un agente ERC-8004 en **Celo**, desarrollado por **Global Score Agent**, que emite certificados de madurez de wallets con nota **A–F** mediante análisis en tiempo real (*hot-analysis*). No almacena históricos: cada certificado se calcula en el momento a partir de datos on-chain de los proveedores.

El scoring corre en **Supabase Edge Functions** (una por tipo). Origins/Activity enriquecen labels vía Walpulse `quality-lookup` (`iq-v1`, cache-only, `include_kleros: true`) — ver [quality-lookup-walpulse.md](quality-lookup-walpulse.md).

- **Preview gratuito** (`POST /v1/preview/{tipo}`): solo `origins` y `activity` (Alchemy). Devuelve la nota A–F, sin métricas ni firma, sin pago. Rate limit: 8 req/IP cada 15 min. `multichain` y `portfolio` → 403 (usar el endpoint pagado).
- **Certificado completo** (`POST /v1/certificates/{tipo}`): devuelve el certificado firmado (métricas + `data_hash`). Requiere **pago x402** de **0,05 USDC** en **Celo**, **Base** o **BNB** (`eip155:56`, Binance-Peg USDC, Permit2 vía Dexter). Celo/Base: EIP-3009. BNB: primer `approve` a Permit2; el 200 incluye `certificate.receipt` (voucher para `claim` del NFT soulbound). El gas del mint lo paga el **cliente** en BNB (no se descuenta de los 0,05 USDC). Celo `giveFeedback` no cambia.

Todos los textos del certificado (`summary`, `grade_label`, `strengths`, `concerns`) son **bilingües** con la forma `{ "eng": "...", "esp": "..." }`.

Escala común de notas:

| Nota | Etiqueta | Significado |
|------|----------|-------------|
| A | Excelente | Perfil maduro y de bajo riesgo |
| B | Bueno | Perfil sólido con observaciones menores |
| C | Aceptable | Perfil promedio / mixto |
| D | Débil | Señales de riesgo o poca trayectoria |
| F | Deficiente / Alto riesgo | Riesgo grave (p. ej. sanciones/mixer) o sin actividad |

**Fórmulas en prod (2026-10-22):**

| Tipo | `formula_version` | Cert `version` | Canal |
|------|-------------------|----------------|-------|
| Origins | `origins-v2.3` | `2.0` | público + Summit |
| Activity | `activity-v2.2` | `2.0` | público + Summit |
| Multichain | `multichain-v2.1` | `2.0` | público + Summit |
| Portfolio | `portfolio-v2.2` | `2.0` | público + Summit |

Labels (Origins/Activity): Walpulse `quality-lookup` iq-v1 (`include_kleros: true`). Ver [quality-lookup-walpulse.md](quality-lookup-walpulse.md).

---

## 1. Origins — Origen de los fondos

**Qué evalúa:** de dónde provienen los fondos de la wallet y qué tan limpio/diverso es ese origen.

**Versión:** `origins-v2.3` (certificado `version: "2.0"`). Edge canónico: `main_origin_type` = argmax de categorías; HHI/top1 sobre inflows **priced**; `priced_coverage_pct` sobre inflows **value-relevant** (native/ERC-20 amount>0; NFTs fuera del denominador); concentración extrema bloquea A/B.

**Fuentes de datos:**
- Hasta **500 transferencias entrantes por red** (Alchemy, orden ascendente histórico).
- Redes = `erc_8004.chains` con `is_active` y `subdomain_alchemy` (fallback: `ALCHEMY_NETWORKS`).
- Pricing USD: DefiLlama histórico (majors), stables = $1, spot DexScreener, o `null`.
- Labels vía Walpulse `quality-lookup` iq-v1 (`include_kleros: true`): CEX / bridge / mixer / OFAC / airdrop / protocol + Kleros / Sourcify / Spellbook.

**Flujo (prod):** el agente enriquece `analysis` (Alchemy + DefiLlama) → Edge `walcert-certificate-origins` aplica labels Walpulse + 9 señales + nota. Edge **no** llama Alchemy ni DefiLlama.

**Señales (9) — valores en `certificate.details`:**

| # | Señal | Campo |
|---|--------|--------|
| 1 | % por categoría (CEX, bridge, mixer, OFAC, airdrop, protocol, orgánico…) | `category_percentages` |
| 2 | Remitentes únicos | `unique_senders` |
| 3 | Concentración HHI (USD priced) | `hhi` |
| 4 | Top-1 / top-3 share | `concentration` |
| 5 | Calidad de CEX (`cex_name` / Spellbook) | `cex_quality` |
| 6 | Patrón temporal de funding | `temporal_funding` |
| 7 | Exposición mixer / OFAC / Kleros | `direct_exposure`, `mixing_risk`, `sanctions_hit` |
| 8 | Orgánico vs sintético (NFT / airdrop) | `organic_vs_synthetic` |
| 9 | Antigüedad del primer funding | `first_funding_age_days` |

Extras v2.3: `airdrop_percentage`, `protocol_percentage`, `quality_enrichment` (cobertura labels, Sourcify %), `label_hits` (conteos reales Walpulse: ofac/mixer/cex/bridge/airdrop/protocol/kleros/kleros_risk/sourcify).

**Coverage value-relevant:** inflows `external`/`erc20` con `amount > 0` (excluye NFT y amount=0). Campos: `value_relevant_*`, `priced_coverage_pct`, `hhi_value_relevant_priced`. El **grade** usa HHI/top1 sobre USD priced.

**Explicabilidad:** `formula_version: "origins-v2.3"`, `grade_breakdown`, `inputs_hash`.

**Reglas de nota (`subject_type` entity, orden F→A→B→D→C) — cambios v2.3 vs v2.2:**
- **F:** OFAC o `mixing_risk = high` (sin cambio).
- **A:** reglas v2.2 **más** `airdrop_pct ≤ 40` **y** sin `kleros_risk_hit`.
- **B:** reglas v2.2 **más** `airdrop_pct ≤ 70`.
- **D:** reglas v2.2 **más** airdrop dominado (`airdrop_pct ≥ 80` y `unique_senders ≤ 3`).
- **C:** resto.

Protocol % entra en `category_percentages` / narrativa (strength si ≥15% y mixing low); no es gate duro de A/B. Sourcify es soft-strength. Kleros risk solo soft-bloquea **A** (no fuerza D/F por sí solo).

**Narrativa:** concern si `top1 ≥ 70%` o `hhi ≥ 0.70`; concern airdrop alto / Kleros risk; strength protocol ≥15% o Sourcify entre labeled.

**Fuera de alcance (v2):** multi-hop, Sepolia/IPFS ORIGO, Public API / WAMI.

---

## 2. Activity — Actividad reciente

**Qué evalúa:** el comportamiento reciente (ventana de **15 días**): con quién opera, concentración, wash/circular, bot-like, y exposición a CEX/mixers/OFAC.

**Versión:** `activity-v2.2` (certificado `version: "2.0"`). Ventana **15 días**. HHI>0.70 → D; 0.45–0.70 bloquea A/B (cae en C).

**Flujo (prod):** el agente enriquece `analysis` (Alchemy 15d in+out + DefiLlama) → Edge `walcert-certificate-activity` aplica labels Walpulse + señales + nota. Edge **no** llama Alchemy ni DefiLlama.

**Fuentes de datos:**
- Hasta **500 transferencias por dirección (in|out) y por red** (Alchemy, orden desc).
- Redes = `erc_8004.chains` con Alchemy (fallback `ALCHEMY_NETWORKS`), igual que Origins.
- Pricing USD híbrido: HHI / net-gross en USD priced; CEX reporta `% valor` y `% txs`.
- Labels vía Walpulse `quality-lookup` iq-v1 (`include_kleros: true`).

**Señales (en `certificate.details`):** las de v2.1 **más** `airdrop_percentage`, `protocol_percentage`, `kleros_risk_hit`, `label_hits` (conteos Walpulse).

**Explicabilidad:** `formula_version: "activity-v2.2"`, `grade_breakdown`, `inputs_hash`.

**Reglas de nota (orden F→D→A→B→C) — cambios v2.2 vs v2.1:**
- **F:** sin cambio (OFAC, wash high, bot ≥ 0.8, wash_score ≥ 0.75).
- **D:** reglas v2.1 **más** `airdrop_pct > 70`.
- **A:** reglas v2.1 **más** `airdrop_pct ≤ 40` **y** sin `kleros_risk_hit`.
- **B:** reglas v2.1 **más** `airdrop_pct ≤ 60`.
- **C:** resto (incl. mid-HHI 0.45–0.70).

**Narrativa:** strength diversidad solo si unique ≥ 10 **y** HHI ≤ 0.35; concern si HHI > 0.45; airdrop/protocol/Kleros en strengths/concerns según umbrales.

**Fuera de alcance:** ventanas 30/90d; labels DEX routers / known bots (sin catálogo aún).

---

## 3. Multi-Chain — Presencia multi-red

**Qué evalúa:** footprint, longevidad e **intensidad muestreada** (txs en top 6 mainnets). Celo entra nativo (GoldRush); no hay merge Alchemy.

**Versión:** `multichain-v2.1` (certificado `version: "2.0"`). Preview **no** disponible (403).

**Flujo (prod):** el agente enriquece `analysis` (GoldRush `/activity/` + `transactions_summary`) → Edge `walcert-certificate-multichain-v2` recomputa señales desde `chains[]` (canónico) + grade.

**Fuentes de datos:**
- GoldRush `GET /v1/address/{wallet}/activity/` (footprint).
- GoldRush `GET /v1/{chain}/address/{wallet}/transactions_summary/` en top 6 mainnets prioritarios (`GOLDRUSH_INTENSITY_TOP_N`, default 6).
- Lista core versionada (`CORE_ECOSYSTEM_LIST_VERSION`): eth, base, celo, arbitrum, optimism, polygon.
- `ecosystem_count` = family map de chain name (eth/base/arb/op → ethereum), no `category_label` crudo.

**Señales (en `certificate.details`):** mainnets/testnets, span, activas 30d/90d, dormant ratio, consistency, recency, core ecosystems, footprint concentration, intensity (`total_tx_count`, `tx_hhi`, weighted activity, primary chain, gas).

**Explicabilidad:** `formula_version: "multichain-v2.1"`, `grade_breakdown`, `inputs_hash`.

**Reglas de nota (orden F→D→A→B→C):**
- **F:** 0 mainnets, solo testnets, o 1 mainnet con span &lt; 30 y total_tx &lt; 5.
- **D:** 1 mainnet, o (dormant_ratio &gt; 0.75 y active_30d = 0), o total_tx = 0 en sample.
- **A:** mainnets ≥ 5, ecosystems ≥ 3, span ≥ 365, consistency ≥ 0.50, recency ≥ 0.35, core ≥ 2, total_tx ≥ 50, tx_hhi ≤ 0.70.
- **B:** mainnets ≥ 3, ecosystems ≥ 2, span ≥ 180, consistency ≥ 0.40, total_tx ≥ 15.
- **C:** resto.

**Canales de cobro:** x402 **$0,05** (Celo/Base/BNB) y ACP **$0,05**. Preview no usa GoldRush.

### Alias Summit — `POST /v1/summit/certificates/multichain-v2`

Mismo pipeline GoldRush `multichain-v2.1`. Requiere auth Summit (`403 summit_only` si no). Atribución `access_channel=summit` / `billing=free` (no x402).

```http
POST /v1/summit/certificates/multichain-v2
Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
X-Walcert-Marketplace: bsg2026
```

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
