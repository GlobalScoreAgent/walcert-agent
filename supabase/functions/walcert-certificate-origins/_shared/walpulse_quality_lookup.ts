/**
 * Walpulse quality-lookup client (contract iq-v1, cache-only).
 * Auth: anon key (Authorization + apikey) + X-Walcert-Secret.
 */

export type QualityKind =
  | "ofac"
  | "mixer"
  | "cex"
  | "bridge"
  | "airdrop"
  | "protocol";

export type QualityHit = {
  kind: QualityKind;
  name: string;
  chain: string;
  sourcify_verified: boolean;
  spellbook_categories: string[];
  kleros: unknown | null;
  kleros_hit: boolean;
  kleros_risk: boolean;
  source: "walpulse" | "gsa";
};

export type ChainAddressItem = {
  chain_id: number;
  address: string;
};

export const KIND_PRIORITY: Record<QualityKind, number> = {
  ofac: 0,
  mixer: 1,
  cex: 2,
  bridge: 3,
  airdrop: 4,
  protocol: 5,
};

const KIND_SET = new Set<string>(Object.keys(KIND_PRIORITY));

/** Tags treated as high-risk for soft grade gates (block A). */
const KLEROS_RISK_RE =
  /scam|phish|hack|exploit|ransomware|darknet|mixer|tornado|sanction|ofac|fraud|rug|malware|stolen/i;

export const CHAIN_ID_BY_SLUG: Record<string, number> = {
  ethereum: 1,
  eth: 1,
  optimism: 10,
  bnb: 56,
  bsc: 56,
  gnosis: 100,
  polygon: 137,
  base: 8453,
  arbitrum: 42161,
  celo: 42220,
};

export const SLUG_BY_CHAIN_ID: Record<number, string> = {
  1: "ethereum",
  10: "optimism",
  56: "bnb",
  100: "gnosis",
  137: "polygon",
  8453: "base",
  42161: "arbitrum",
  42220: "celo",
};

export function chainIdFromSlug(slug: string | null | undefined): number | null {
  const s = (slug || "").toLowerCase().trim();
  if (!s) return null;
  return CHAIN_ID_BY_SLUG[s] ?? null;
}

export function slugFromChainId(chainId: number): string {
  return SLUG_BY_CHAIN_ID[chainId] || String(chainId);
}

function flattenStrings(value: unknown, out: string[] = []): string[] {
  if (value == null) return out;
  if (typeof value === "string") {
    out.push(value);
    return out;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    out.push(String(value));
    return out;
  }
  if (Array.isArray(value)) {
    for (const v of value) flattenStrings(v, out);
    return out;
  }
  if (typeof value === "object") {
    for (const v of Object.values(value as Record<string, unknown>)) {
      flattenStrings(v, out);
    }
  }
  return out;
}

export function klerosLooksRisky(kleros: unknown): boolean {
  if (kleros == null) return false;
  return flattenStrings(kleros).some((s) => KLEROS_RISK_RE.test(s));
}

type IqResultItem = {
  chain_id?: number;
  address?: string;
  categories?: string[];
  cex_name?: string | null;
  spellbook?: Array<{ category?: string; name?: string }> | null;
  sourcify?: unknown;
  kleros?: unknown;
  cache_status?: string;
};

function pickKind(categories: string[] | undefined): QualityKind | null {
  if (!categories?.length) return null;
  let best: QualityKind | null = null;
  let bestPri = 999;
  for (const raw of categories) {
    const k = String(raw || "").toLowerCase();
    if (!KIND_SET.has(k)) continue;
    const kind = k as QualityKind;
    const pri = KIND_PRIORITY[kind];
    if (pri < bestPri) {
      bestPri = pri;
      best = kind;
    }
  }
  return best;
}

export function mapIqItemToHit(item: IqResultItem): QualityHit | null {
  const addr = String(item.address || "").toLowerCase();
  if (!addr.startsWith("0x")) return null;
  const chainId = Number(item.chain_id) || 0;
  const kind = pickKind(item.categories);
  const spellbook_categories = (item.spellbook || [])
    .map((s) => String(s?.category || "").toLowerCase())
    .filter(Boolean);
  const kleros = item.kleros ?? null;
  const kleros_hit = kleros != null;
  const kleros_risk = klerosLooksRisky(kleros);
  const sourcify_verified = item.sourcify != null;

  // Soft kind from kleros text only if categories empty
  let resolved = kind;
  if (!resolved && kleros_hit) {
    const flat = flattenStrings(kleros).join(" ").toLowerCase();
    if (/\bofac\b|sanction/.test(flat)) resolved = "ofac";
    else if (/\bmixer\b|tornado/.test(flat)) resolved = "mixer";
    else if (/\bcex\b|exchange|binance|coinbase|okx|kraken/.test(flat)) {
      resolved = "cex";
    } else if (/\bbridge\b/.test(flat)) resolved = "bridge";
    else if (/\bairdrop\b|faucet/.test(flat)) resolved = "airdrop";
    else if (/\bprotocol\b|defi|dex\b/.test(flat)) resolved = "protocol";
  }

  if (!resolved && !sourcify_verified && !kleros_hit && !spellbook_categories.length) {
    return null;
  }

  const name =
    (item.cex_name && String(item.cex_name)) ||
    (item.spellbook?.[0]?.name && String(item.spellbook[0].name)) ||
    resolved ||
    "labeled";

  return {
    kind: resolved || "protocol",
    name,
    chain: slugFromChainId(chainId),
    sourcify_verified,
    spellbook_categories,
    kleros,
    kleros_hit,
    kleros_risk,
    source: "walpulse",
  };
}

function preferHit(a: QualityHit, b: QualityHit): QualityHit {
  const pa = KIND_PRIORITY[a.kind];
  const pb = KIND_PRIORITY[b.kind];
  if (pa !== pb) return pa < pb ? a : b;
  // Prefer walpulse, then richer metadata
  if (a.source !== b.source) return a.source === "walpulse" ? a : b;
  if (a.kleros_risk !== b.kleros_risk) return a.kleros_risk ? a : b;
  if (a.sourcify_verified !== b.sourcify_verified) {
    return a.sourcify_verified ? a : b;
  }
  return a;
}

export function mergeHitsByAddress(
  hits: Iterable<QualityHit>,
  addressKey: (h: QualityHit) => string,
): Map<string, QualityHit> {
  const out = new Map<string, QualityHit>();
  for (const h of hits) {
    const key = addressKey(h);
    if (!key) continue;
    const prev = out.get(key);
    out.set(key, prev ? preferHit(prev, h) : h);
  }
  return out;
}

const DEFAULT_URL = "https://api.walpulse.com/functions/v1/quality-lookup";
const CHUNK = 100;
const TIMEOUT_MS = 5000;

export type QualityLookupMeta = {
  requested: number;
  returned: number;
  hits: number;
  missing: number;
  partial: boolean;
  error?: string;
};

export async function fetchWalpulseQualityLookup(
  items: ChainAddressItem[],
  opts?: { includeKleros?: boolean },
): Promise<{ byAddress: Map<string, QualityHit>; meta: QualityLookupMeta }> {
  const empty = new Map<string, QualityHit>();
  const meta: QualityLookupMeta = {
    requested: 0,
    returned: 0,
    hits: 0,
    missing: 0,
    partial: false,
  };

  const enabledRaw = (Deno.env.get("WALPULSE_QUALITY_LOOKUP_ENABLED") || "")
    .toLowerCase()
    .trim();
  const anon = Deno.env.get("WALPULSE_ANON_KEY") || "";
  const secret = Deno.env.get("WALCERT_QUALITY_LOOKUP_SECRET") || "";
  const url = Deno.env.get("WALPULSE_QUALITY_LOOKUP_URL") || DEFAULT_URL;
  const secretsOk = anon.length >= 16 && secret.length >= 8;
  // Explicit false/off wins; otherwise auto-on when secrets are configured.
  if (enabledRaw === "0" || enabledRaw === "false" || enabledRaw === "no") {
    meta.error = "disabled";
    return { byAddress: empty, meta };
  }
  if (
    enabledRaw !== "1" &&
    enabledRaw !== "true" &&
    enabledRaw !== "yes" &&
    !secretsOk
  ) {
    meta.error = "disabled";
    return { byAddress: empty, meta };
  }
  if (!secretsOk) {
    meta.error = "secrets_missing";
    console.error("walpulse quality-lookup: secrets missing or too short");
    return { byAddress: empty, meta };
  }

  const dedupe = new Map<string, ChainAddressItem>();
  for (const it of items) {
    const address = String(it.address || "").toLowerCase();
    const chain_id = Number(it.chain_id);
    if (!address.startsWith("0x") || !Number.isFinite(chain_id) || chain_id <= 0) {
      continue;
    }
    dedupe.set(`${chain_id}:${address}`, { chain_id, address });
  }
  const unique = [...dedupe.values()];
  meta.requested = unique.length;
  if (!unique.length) return { byAddress: empty, meta };

  const includeKleros = opts?.includeKleros !== false;
  const collected: QualityHit[] = [];
  const addrForHit = new Map<QualityHit, string>();

  for (let i = 0; i < unique.length; i += CHUNK) {
    const chunk = unique.slice(i, i + CHUNK);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
      const res = await fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${anon}`,
          apikey: anon,
          "X-Walcert-Secret": secret,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ items: chunk, include_kleros: includeKleros }),
        signal: controller.signal,
      });
      clearTimeout(timer);

      if (!res.ok) {
        const body = await res.text().catch(() => "");
        console.error(
          "walpulse quality-lookup http",
          res.status,
          body.slice(0, 300),
        );
        meta.error = `http_${res.status}`;
        meta.partial = true;
        continue;
      }

      const json = await res.json() as {
        ok?: boolean;
        partial?: boolean;
        results?: IqResultItem[];
        meta?: {
          items_returned?: number;
          hits?: number;
          missing?: number;
        };
      };
      if (json.partial) meta.partial = true;
      meta.returned += Number(json.meta?.items_returned) || (json.results?.length || 0);
      meta.hits += Number(json.meta?.hits) || 0;
      meta.missing += Number(json.meta?.missing) || 0;

      for (const row of json.results || []) {
        const hit = mapIqItemToHit(row);
        if (!hit) continue;
        const addr = String(row.address || "").toLowerCase();
        collected.push(hit);
        addrForHit.set(hit, addr);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("walpulse quality-lookup error", msg);
      meta.error = "fetch_failed";
      meta.partial = true;
    }
  }

  const byAddress = mergeHitsByAddress(collected, (h) => addrForHit.get(h) || "");
  return { byAddress, meta };
}
