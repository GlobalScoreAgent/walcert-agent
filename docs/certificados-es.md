# Certificados Walcert Agent (ES)

Walcert Agent es un agente ERC-8004 en **Celo**, desarrollado por **Global Score Agent**, que emite certificados de madurez de wallets con nota **A–F** mediante análisis en tiempo real (*hot-analysis*). No almacena históricos: cada certificado se calcula en el momento a partir de datos on-chain de los proveedores.

El scoring corre en **Supabase Edge Functions** (una por tipo de certificado) y se enriquece con listas de direcciones etiquetadas (CEX, bridges, mixers y sanciones OFAC) almacenadas en Supabase.

- **Preview gratuito** (`POST /v1/preview/{tipo}`): devuelve solo la nota A–F, sin métricas ni firma, sin pago.
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

---

## 1. Origins — Origen de los fondos

**Qué evalúa:** de dónde provienen los fondos de la wallet y qué tan limpio/diverso es ese origen.

**Fuentes de datos:**
- Transferencias entrantes y primer *funding* de la wallet (Alchemy, en Celo y BNB).
- Etiquetado de las direcciones remitentes contra las tablas `wallets.cex_addresses`, `wallets.bridge_addresses`, `wallets.mixer_addresses` y `wallets.ofac_sanction_addresses` (vía la función `walcert_lookup_labels`).

**Métricas principales:**
- `cex_percentage`: porcentaje del valor recibido desde exchanges centralizados.
- `bridge_percentage`: porcentaje recibido desde bridges.
- `unique_senders`: cantidad de remitentes distintos (diversidad).
- `mixing_risk`: `low` / `medium` / `high` (interacción con mixers o remitente único).
- `first_funding_age_days`: antigüedad del primer financiamiento.
- `sanctions_hit`: coincidencia con dirección sancionada (OFAC).

**Reglas de nota (resumen):**
- **F:** coincidencia OFAC, o `mixing_risk = high`.
- **A:** `cex ≤ 40%`, `unique_senders ≥ 10`, `mixing = low` y antigüedad ≥ 365 días.
- **B:** `cex ≤ 70%`, `unique_senders ≥ 5` y `mixing = low`.
- **D:** `mixing = medium`, o alta dependencia de CEX con muy baja diversidad.
- **C:** resto de los casos.

---

## 2. Activity — Actividad reciente

**Qué evalúa:** el comportamiento reciente (ventana de ~7 días): con quién opera, si hay señales de *wash trading* o patrones circulares, y exposición a CEX/mixers/OFAC.

**Fuentes de datos:**
- Transferencias recientes y contrapartes (Alchemy).
- Etiquetado de contrapartes contra las mismas tablas de `wallets.*`.
- Heurística de *wash trading* / patrones circulares calculada dentro de la Edge Function a partir de la serie de transferencias (pares bidireccionales, ping-pong temporal y ciclos A→B→A).

**Métricas principales:**
- `unique_counterparties`: contrapartes distintas.
- `cex_interaction_percentage`: proporción de operaciones con CEX.
- `wash_trading_risk`: `low` / `medium` / `high`.
- `circular_patterns`: booleano (ciclos/ping-pong detectados).
- `bidirectional_pair_share`: cuota de volumen en pares bidireccionales.
- `sanctions_hit`, `mixer_hit`.

**Reglas de nota (resumen):**
- **F:** coincidencia OFAC, o `wash_trading_risk = high`.
- **D:** patrones circulares con riesgo medio, o interacción con mixer, o `unique_counterparties < 3`, o `cex > 60%`.
- **A:** `unique_counterparties ≥ 25`, `wash = low` y sin patrones circulares.
- **B:** `unique_counterparties ≥ 12` y `wash = low`.
- **C:** resto de los casos.

---

## 3. Multi-Chain — Presencia multi-red

**Qué evalúa:** en cuántas redes opera la wallet y por cuánto tiempo (consistencia y longevidad multi-cadena).

**Fuentes de datos:**
- Cadenas activas y ventana temporal de actividad (Moralis `getWalletActiveChains`).
- Actividad en **Celo** aportada por Alchemy y fusionada al resultado (Celo no está en Moralis).

**Métricas principales:**
- `total_chains_with_activity`: número de redes con actividad real.
- `activity_span_days`: días entre la primera y la última actividad.
- `main_chains`: principales redes detectadas.

**Reglas de nota (resumen):**
- **A:** ≥ 4 redes y span ≥ 365 días.
- **B:** ≥ 3 redes y span ≥ 180 días.
- **C:** ≥ 2 redes.
- **D:** 1 red con span ≥ 30 días.
- **F:** sin actividad multi-red significativa.

---

## 4. Portfolio — Composición del portafolio

**Qué evalúa:** la calidad de la cartera actual: tamaño, liquidez, diversificación y exposición especulativa.

**Fuentes de datos:**
- Posiciones del portafolio (Zerion), incluyendo tokens, stablecoins, bluechips y posiciones DeFi/LP.

**Métricas principales:**
- `total_value_usd`: valor total estimado.
- `liquid_ratio`: porcentaje líquido (no bloqueado).
- `category_distribution`: distribución por categoría (stablecoin, bluechip, defi_lp, meme_or_other).
- `concentration`: `top1_share` (peso del mayor activo) y `hhi` (índice Herfindahl-Hirschman).
- `defi_exposure_pct`: exposición a DeFi/LP.
- `dust_filtered_count` / `spam_filtered_count`: posiciones descartadas por polvo o spam/sin precio.

**Reglas de nota (resumen):**
- **F:** valor < $10, o cartera dominada por memes (> 85%) con valor < $500.
- **D:** valor < $100, o memes > 70%, o concentración top-1 > 0,92.
- **A:** valor ≥ $10.000, líquido ≥ 60%, memes ≤ 15%, top-1 ≤ 0,55 y HHI ≤ 0,4.
- **B:** valor ≥ $2.000, líquido ≥ 50%, memes ≤ 30% y top-1 ≤ 0,7.
- **C:** resto de los casos.

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

Ver también: [certificate-json-schemas.md](certificate-json-schemas.md) y [edge-function-security.md](edge-function-security.md).
