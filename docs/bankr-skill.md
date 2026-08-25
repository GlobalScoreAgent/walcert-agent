# Walcert × Bankr (skill, not Cloud wrap)

Product decision: vault ADR
`08 - Decisiones/2026-08-24 - Integración Walcert en Bankr (skill, no Cloud wrap)`.
Evaluation: `03 - Walcert/2026-08-23 - Evaluación Bankr`.

Bankr is an **agent runtime**, not a seller catalog. Integration v1 is a **thin skill**
that calls the public Walcert API. It is **not** an x402 Cloud deploy and **not** an
internal-marketplace adapter.

The skill body is **host-agnostic** (`SKILL.md`). The same file is the OpenClaw v1
surface (`metadata.openclaw`). Bankr-only metadata lives in `catalog.json`.

## Repo layout

```
skills/walcert/
  SKILL.md
  catalog.json
  references/api.md
  references/x402-rails.md
```

**Bankr cannot fetch the private `walcert-agent` repo.** The public install target is
[`GlobalScoreAgent/walcert-skill`](https://github.com/GlobalScoreAgent/walcert-skill)
(same folder). Keep both copies in sync when you edit the skill.

Install (Bankr terminal):

```
install the walcert skill from https://github.com/GlobalScoreAgent/walcert-skill/tree/main/skills/walcert
```

## Allowed

- Instruct the Bankr agent to call:
  - `POST https://walcert.globalscoreagent.com/v1/preview/{origins|activity}`
  - `POST https://walcert.globalscoreagent.com/v1/certificates/{type}` (x402)
  - `POST https://walcert.globalscoreagent.com/v1/verify`
- Prefer **Base** (`eip155:8453`) for the paid 402. BNB Permit2 + NFT `claim` only if
  the host can settle `eip155:56` (see `references/x402-rails.md`).
- Discover PR: [BankrBot/skills#668](https://github.com/BankrBot/skills/pull/668).
  Public GitHub source of truth for install: `walcert-skill`.

## Forbidden (ADR)

- Deploying or proxying certificates on `https://x402.bankr.bot/...`.
- Adding `bankr` to `WALCERT_INTERNAL_MARKETPLACES` or using `WALCERT_INTERNAL_API_KEY`.
- Putting Edge/owner/monitor secrets on Bankr infrastructure.

## Runtime

No FastAPI / Edge / payTo / agentId change. Paid traffic looks like any public x402
client: `access_channel=direct`, `billing=x402`.

## Smoke (operator, needs a Bankr account)

1. In [bankr.bot/terminal](https://bankr.bot/terminal), install from the GitHub URL above.
2. Ask for a **preview** of `origins` on a test wallet (no payment).
3. Optional: pay **$0.05 USDC on Base** for a full certificate. Do not use Owner/Monitor/payTo as the buyer unless it is a conscious smoke.

OpenClaw: same `SKILL.md`. ClawHub: `clawhub skill publish ./skills/walcert --slug walcert --name Walcert --owner <owner> --categories finance,agents --topics "x402,wallet,certificates"` (requires `clawhub login`).

Bankr Discover PR: https://github.com/BankrBot/skills/pull/668.
