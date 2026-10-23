import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  type ChainAddressItem,
  type QualityHit,
  type QualityKind,
  chainIdFromSlug,
  fetchWalpulseQualityLookup,
  slugFromChainId,
} from "./walpulse_quality_lookup.ts";

/** @deprecated Prefer QualityHit — kept as alias for scoring modules. */
export type LabelHit = QualityHit;
export type { QualityHit, QualityKind, ChainAddressItem };

const CHAIN_ALIASES: Record<string, string[]> = {
  bsc: ["bsc", "bnb"],
  bnb: ["bsc", "bnb"],
  eth: ["eth", "ethereum"],
  ethereum: ["eth", "ethereum"],
  celo: ["celo"],
  base: ["base"],
  arbitrum: ["arbitrum"],
  optimism: ["optimism"],
  polygon: ["polygon"],
};

export function mapChain(chain: string | null | undefined): string {
  const c = (chain || "").toLowerCase();
  if (c === "bsc") return "bnb";
  if (c === "eth") return "ethereum";
  return c || "unknown";
}

export function chainVariants(chain: string | null | undefined): string[] {
  const mapped = mapChain(chain);
  return CHAIN_ALIASES[mapped] ?? [mapped];
}

export function getServiceClient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  return createClient(url, key);
}

export function buildLookupItems(params: {
  addresses?: string[];
  pairs?: Array<{ address: string; chain_id?: number | null; chain?: string | null }>;
  defaultChains?: string[];
}): ChainAddressItem[] {
  const out = new Map<string, ChainAddressItem>();
  for (const p of params.pairs || []) {
    const address = String(p.address || "").toLowerCase();
    if (!address.startsWith("0x")) continue;
    let chain_id = p.chain_id != null ? Number(p.chain_id) : NaN;
    if (!Number.isFinite(chain_id) || chain_id <= 0) {
      const fromSlug = chainIdFromSlug(mapChain(p.chain || ""));
      if (fromSlug == null) continue;
      chain_id = fromSlug;
    }
    out.set(`${chain_id}:${address}`, { chain_id, address });
  }
  const defaults = (params.defaultChains || [])
    .map((c) => chainIdFromSlug(mapChain(c)))
    .filter((id): id is number => id != null);
  for (const raw of params.addresses || []) {
    const address = String(raw || "").toLowerCase();
    if (!address.startsWith("0x")) continue;
    for (const chain_id of defaults) {
      out.set(`${chain_id}:${address}`, { chain_id, address });
    }
  }
  return [...out.values()];
}

/**
 * Quality labels via Walpulse iq-v1 (include_kleros).
 * GSA walcert_lookup_labels fallback removed (cutover 2026-10-22).
 */
export async function lookupLabels(
  _client: SupabaseClient,
  addresses: string[],
  chains: string[],
  pairs?: Array<{ address: string; chain_id?: number | null; chain?: string | null }>,
): Promise<Map<string, QualityHit>> {
  const items = buildLookupItems({
    addresses,
    pairs,
    defaultChains: chains,
  });

  const { byAddress, meta } = await fetchWalpulseQualityLookup(items, {
    includeKleros: true,
  });
  if (meta.error && meta.error !== "disabled") {
    console.error("walpulse quality-lookup meta", meta);
  }
  return byAddress;
}

export function summarizeQualityHits(hits: Map<string, QualityHit>): {
  ofac: number;
  mixer: number;
  cex: number;
  bridge: number;
  airdrop: number;
  protocol: number;
  kleros: number;
  kleros_risk: number;
  sourcify: number;
} {
  let ofac = 0, mixer = 0, cex = 0, bridge = 0, airdrop = 0, protocol = 0;
  let kleros = 0, kleros_risk = 0, sourcify = 0;
  for (const h of hits.values()) {
    if (h.kind === "ofac") ofac++;
    else if (h.kind === "mixer") mixer++;
    else if (h.kind === "cex") cex++;
    else if (h.kind === "bridge") bridge++;
    else if (h.kind === "airdrop") airdrop++;
    else if (h.kind === "protocol") protocol++;
    if (h.kleros_hit) kleros++;
    if (h.kleros_risk) kleros_risk++;
    if (h.sourcify_verified) sourcify++;
  }
  return { ofac, mixer, cex, bridge, airdrop, protocol, kleros, kleros_risk, sourcify };
}

/** @deprecated use summarizeQualityHits */
export function summarizeLabels(hits: Map<string, QualityHit>) {
  const s = summarizeQualityHits(hits);
  return { ofac: s.ofac, mixer: s.mixer, cex: s.cex, bridge: s.bridge };
}

export { slugFromChainId, chainIdFromSlug };
