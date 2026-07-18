import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export type LabelHit = {
  kind: "ofac" | "mixer" | "cex" | "bridge";
  name: string;
  chain: string;
};

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

const PRIORITY: Record<LabelHit["kind"], number> = {
  ofac: 0,
  mixer: 1,
  cex: 2,
  bridge: 3,
};

/** Priority: ofac > mixer > cex > bridge via SECURITY DEFINER RPC */
export async function lookupLabels(
  client: SupabaseClient,
  addresses: string[],
  chains: string[],
): Promise<Map<string, LabelHit>> {
  const result = new Map<string, LabelHit>();
  const addrs = [...new Set(addresses.map((a) => a.toLowerCase()).filter((a) => a.startsWith("0x")))];
  if (addrs.length === 0) return result;

  const chainSet = new Set<string>();
  for (const c of chains) {
    for (const v of chainVariants(c)) chainSet.add(v);
  }
  const chainList = [...chainSet].filter(Boolean);

  // Always resolve without chain filter first (addresses are global enough for hot path),
  // then prefer hits whose chain matches when available.
  const { data, error } = await client
    .schema("walcert")
    .rpc("walcert_lookup_labels", {
      addrs,
      chains: null,
    });

  if (error) {
    console.error("walcert_lookup_labels error", error.message || error);
    return result;
  }

  const hits = pickBest(data || []);
  if (!chainList.length) return hits;

  // Re-query with chain filter and merge (prefer chain-specific names)
  const { data: scoped } = await client
    .schema("walcert")
    .rpc("walcert_lookup_labels", {
      addrs,
      chains: chainList,
    });
  if (scoped?.length) {
    for (const [addr, hit] of pickBest(scoped)) {
      hits.set(addr, hit);
    }
  }
  return hits;
}

function pickBest(
  rows: Array<{ kind?: string; address?: string; name?: string; chain?: string }>,
): Map<string, LabelHit> {
  const result = new Map<string, LabelHit>();
  for (const row of rows) {
    const kind = row.kind as LabelHit["kind"];
    const addr = (row.address || "").toLowerCase();
    if (!addr || !kind || !(kind in PRIORITY)) continue;
    const existing = result.get(addr);
    if (!existing || PRIORITY[kind] < PRIORITY[existing.kind]) {
      result.set(addr, {
        kind,
        name: String(row.name || kind),
        chain: row.chain || "",
      });
    }
  }
  return result;
}
