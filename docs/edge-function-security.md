# Walcert — Seguridad de las Edge Functions

Requisitos para que el motor de scoring (Supabase Edge Function u equivalente) sea **consumible solo por el agente** y no por el frontend, terceros ni el repo público.

---

## Principio

```text
Cliente ──► Agente (VPS) ──► Edge Function (scoring)
                 ▲                    ▲
                 │                    └── secretos / auth server-side
                 └── API keys de Alchemy/Moralis/Zerion
```

- El **cliente nunca** llama a la Edge Function.
- El **agente** es el único caller autorizado.
- El código de scoring y los secretos **no** viven en el repo público del agente (o viven solo como stub; la function desplegada usa Secrets del proyecto).

---

## Requisitos obligatorios

### 1. Autenticación mutua agente → Edge

| Requisito | Detalle |
|-----------|---------|
| Shared secret | Header `Authorization: Bearer <EDGE_SHARED_SECRET>` (o `X-Walcert-Agent-Secret`) |
| Longitud | ≥ 32 bytes aleatorios (`openssl rand -hex 32`) |
| Almacenamiento agente | Solo `.env` / secrets del VPS — **nunca** en Git, IPFS, metadata ERC-8004 ni dashboard |
| Almacenamiento Edge | Supabase Edge Secrets / env del proyecto |
| Rechazo | Sin secret o secret inválido → **401 Unauthorized**, sin ejecutar scoring |

### 2. No exposición pública útil

| Requisito | Detalle |
|-----------|---------|
| Sin CORS abierto a browsers | No permitir `Access-Control-Allow-Origin: *` para orígenes arbitrarios; idealmente **sin CORS** (solo server-to-server) |
| URL no documentada en metadata pública | El `registration.json` / ERC-8004 lista endpoints del **agente**, no la URL interna de la Edge |
| Sin anon key como única defensa | Si se usa Supabase, **no** basar la seguridad solo en que “nadie conoce la URL”; la `anon` key de un proyecto a menudo es pública en frontends |

### 3. Validación de entrada

| Requisito | Detalle |
|-----------|---------|
| Schema estricto | Solo `certificate_type`, `wallet`, `analyzed_at`, `payload` (analysis semicrudo) |
| Tipos permitidos | `origins` \| `activity` \| `multichain` \| `portfolio` |
| Wallet | `0x` + 40 hex; rechazar otros formatos |
| Tamaño máximo | Límite de body (p. ej. 512 KB–1 MB) para evitar abuse |
| Rechazo | Body inválido → **400** |

### 4. Respuesta mínima

| Requisito | Detalle |
|-----------|---------|
| No devolver el algoritmo | Solo resultado: `score`, `issued_at`, `report_hash`, `summary` opcional |
| No eco del payload crudo | Evitar reenviar todo el `analysis` de vuelta si no hace falta |
| Errores genéricos al exterior | Mensajes que no filtren internals (`"scoring_failed"`, no stack traces) |

### 5. Rate limiting y abuso

| Requisito | Detalle |
|-----------|---------|
| Rate limit por IP / por secret | Tope de requests/min (p. ej. 60/min por agente) |
| Timeout | Cortar ejecución larga (p. ej. 10–30 s) |
| Logs | Registrar `certificate_type`, wallet hasheada o truncada, status — **no** loguear el shared secret ni API keys |

### 6. Transporte

| Requisito | Detalle |
|-----------|---------|
| HTTPS only | TLS obligatorio en producción |
| Sin http:// en prod | El agente solo debe llamar `https://…` |

---

## Requisitos recomendados (refuerzo)

### A. HMAC con timestamp (anti-replay)

Además del Bearer:

1. Agente calcula `signature = HMAC-SHA256(secret, timestamp + "." + body)`
2. Headers: `X-Walcert-Timestamp`, `X-Walcert-Signature`
3. Edge rechaza si `|now - timestamp| > 60s` o la firma no coincide

Así un Bearer filtrado solo no alcanza para reutilizar requests viejos fácilmente.

### B. Allowlist de IP del agente

Si el VPS tiene IP fija (`3.139.89.63` u otra):

- Permitir solo esa IP (o el egress del agente) a nivel Edge / Cloudflare / API gateway.
- **Complemento**, no sustituto del secret (IPs pueden cambiar; no es prueba criptográfica).

### C. JWT de corta vida emitido por el agente

Flujo opcional más estricto:

1. El agente firma un JWT (exp 1–2 min) con clave privada.
2. La Edge verifica con la clave pública / secret compartido.
3. Claims: `iss=walcert-agent`, `aud=walcert-score`, `certificate_type`, `wallet`.

### D. Separación de proyectos

- Proyecto Supabase **dedicado** al scoring (no mezclar con un frontend público que exponga `anon` key).
- Roles: la function no necesita `service_role` para scoring puro; si no escribe en DB, no uses service role.

---

## Contrato HTTP sugerido

### Request (agente → Edge)

```http
POST /functions/v1/walcert-score
Authorization: Bearer <EDGE_SHARED_SECRET>
Content-Type: application/json
X-Walcert-Timestamp: 1721246700
X-Walcert-Signature: <hex hmac>   # recomendado
```

```json
{
  "certificate_type": "origins",
  "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
  "analyzed_at": "2026-07-17T19:45:00Z",
  "payload": {
    "module": "origins",
    "score_inputs": { },
    "...": "analysis semicrudo del agente"
  }
}
```

### Response 200

```json
{
  "certificate_type": "origins",
  "wallet": "0x2efc66c0a78620dd254443998bf2f11b685602e3",
  "score": 742,
  "issued_at": "2026-07-17T19:45:01Z",
  "report_hash": "0xabc...",
  "summary": {
    "level": "mature",
    "notes": []
  }
}
```

### Response 401

```json
{
  "error": "unauthorized",
  "message": "Invalid or missing agent credentials"
}
```

---

## Checklist de despliegue

- [ ] `EDGE_SHARED_SECRET` generado y distinto en staging/prod  
- [ ] Secret en VPS (`.env`) y en Supabase Secrets — no en Git  
- [ ] Function verifica Bearer (y HMAC si aplica) **antes** de cualquier lógica  
- [ ] CORS cerrado / ausente  
- [ ] URL de Edge **no** publicada en ERC-8004 metadata  
- [ ] Rate limit activo  
- [ ] HTTPS en producción  
- [ ] Prueba negativa: curl sin secret → 401  
- [ ] Prueba negativa: curl desde browser / otra IP sin secret → 401  
- [ ] Rotación documentada (cambiar secret en Edge + VPS a la vez)

---

## Qué NO hacer

1. Poner la URL de la Edge en `dashboard.html`  
2. Usar la misma key de Alchemy/Moralis/Zerion dentro de la Edge (en el diseño actual el agente ya trae el semicrudo)  
3. Confiar solo en “security through obscurity”  
4. Devolver el código fuente o prompts del modelo de scoring en la respuesta  
5. Commitear `.env` con `EDGE_SHARED_SECRET`

---

## Resumen

La Edge Function es segura para el agente si:

1. **Solo el agente** conoce el secret (y opcionalmente firma HMAC / viene de IP allowlist).  
2. La function **exige** esa credencial en cada request.  
3. El mundo exterior solo habla con el **agente** (x402 + certificados), nunca con el motor.
