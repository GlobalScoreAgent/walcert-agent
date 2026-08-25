# Canal Summit BSG2026 (sin x402)

Acceso temporal para la landing del **Blockchain Summit Global 2026** (`bsg2026.globalscoreagent.com`): certificados full sin paywall x402, autenticados con una **API key dedicada** (distinta del canal de marketplaces ACP).

ADR: vault `08 - Decisiones/2026-07-26 - Canal Summit BSG2026 sin x402 (key dedicada + caducidad)`.

## Contrato HTTP

Certificados públicos (mismo path que x402, sin paywall con Summit key):

```http
POST /v1/certificates/{origins|activity|multichain|portfolio}
Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
X-Walcert-Marketplace: bsg2026
Content-Type: application/json

{"wallet_address":"0x..."}
```

| Tipo | `formula_version` (prod) |
|------|--------------------------|
| `origins` | `origins-v2.2` |
| `activity` | `activity-v2.1` |
| `multichain` | `multichain-v2.1` (GoldRush) |
| `portfolio` | `portfolio-v2.2` |

**Multichain v2 (alias Summit)** — mismo GoldRush `multichain-v2.1` que el path público `/v1/certificates/multichain`:

```http
POST /v1/summit/certificates/multichain-v2
Authorization: Bearer <WALCERT_SUMMIT_API_KEY>
X-Walcert-Marketplace: bsg2026
Content-Type: application/json

{"wallet_address":"0x..."}
```

Fórmula: `multichain-v2.1`. Fuera del canal Summit → **403** `summit_only`.

| Resultado | Cuándo |
|-----------|--------|
| **200** | Key válida, marketplace `bsg2026`, canal activo, dentro del rate limit |
| **401** | Key inválida, marketplace ausente/incorrecto |
| **403** | `WALCERT_SUMMIT_ENABLED=false`, `now >= WALCERT_SUMMIT_EXPIRES_AT`, o Multichain v2 sin canal Summit |
| **429** | Rate limit Summit excedido — wallet (12/15 min) o IP backstop (500/15 min); header `Retry-After` |
| **402** | Sin Bearer Summit/internal válido (cliente directo) |

Atribución persistida (vía meta `_walcert_access` → Edge):

- `access_channel`: `summit`
- `marketplace`: `bsg2026`
- `billing`: `free`

Env Summit adicional: `GOLDRUSH_API_KEY` en el agente EC2 (Multichain público + alias Summit).

## Variables de entorno (agente EC2)

| Variable | Rol |
|----------|-----|
| `WALCERT_SUMMIT_API_KEY` | Secreto dedicado (`openssl rand -hex 32`). **≠** `WALCERT_INTERNAL_API_KEY` |
| `WALCERT_SUMMIT_ENABLED` | Kill switch (`true`/`false`) |
| `WALCERT_SUMMIT_EXPIRES_AT` | ISO-8601; default `2026-08-01T00:00:00+00:00` |
| `WALCERT_SUMMIT_RATE_LIMIT_WALLET` | Primary: default **`12`** req / wallet / 15 min (= 3 packs de 4 HTTP) |
| `WALCERT_SUMMIT_RATE_LIMIT` | IP backstop: default **`500`** / IP / 15 min (egress Vercel compartido) |
| `WALCERT_SUMMIT_RATE_WINDOW_SECONDS` | Default `900` (15 min) |

Rate limit dual: se niega con **429** si se excede **wallet o IP**. La landing llama server-side; la IP que ve el agente es la de Vercel, no el WiFi del venue.

**No** agregar `bsg2026` a `WALCERT_INTERNAL_MARKETPLACES`. Ese slug solo se acepta con la summit key.

## Landing (Vercel)

1. Guardar el mismo valor de `WALCERT_SUMMIT_API_KEY` como secret de servidor.
2. Llamar al agente **solo desde server-side** (Route Handler / Server Action). Nunca exponer la key en el browser ni en el QR.
3. Tras el 1 ago 2026 el agente responde 403 aunque la key sea correcta; se puede desactivar antes con `WALCERT_SUMMIT_ENABLED=false`.

## Smoke post-deploy

```bash
# OK (antes del 1 ago 2026, con key válida en .env del host)
curl -sS -o /tmp/summit.json -w "%{http_code}\n" \
  -X POST "https://walcert.globalscoreagent.com/v1/certificates/origins" \
  -H "Authorization: Bearer $WALCERT_SUMMIT_API_KEY" \
  -H "X-Walcert-Marketplace: bsg2026" \
  -H "Content-Type: application/json" \
  -d '{"wallet_address":"0x0000000000000000000000000000000000000001"}'

# 401 — key mala
curl -sS -w "%{http_code}\n" -o /dev/null \
  -X POST "https://walcert.globalscoreagent.com/v1/certificates/origins" \
  -H "Authorization: Bearer wrong" \
  -H "X-Walcert-Marketplace: bsg2026" \
  -H "Content-Type: application/json" \
  -d '{"wallet_address":"0x0000000000000000000000000000000000000001"}'

# 403 — staging con WALCERT_SUMMIT_EXPIRES_AT en el pasado, o ENABLED=false
```

## Checklist deploy

- [ ] Generar key: `openssl rand -hex 32`
- [ ] Setear en `/opt/walcert/.env` del EC2 (y reiniciar `walcert-agent`)
- [ ] Setear el mismo valor en secrets de la landing Vercel (server-only)
- [ ] Confirmar `WALCERT_SUMMIT_EXPIRES_AT=2026-08-01T00:00:00+00:00`
- [ ] Smoke 200 / 401 / (opcional) 403
- [ ] Tras el evento: dejar caducar o poner `WALCERT_SUMMIT_ENABLED=false` y rotar/borrar la key

## Relacionado

- Canal marketplaces (ACP): [virtuals-acp.md](virtuals-acp.md)
- Modelo de secrets Edge vs agente: [edge-function-security.md](edge-function-security.md)
- Formulas / tipos: [certificados-es.md](certificados-es.md) · [certificates-en.md](certificates-en.md)
- Multichain v2 GoldRush: env `GOLDRUSH_API_KEY` en EC2 (ver [deployment-guide.md](deployment-guide.md))
