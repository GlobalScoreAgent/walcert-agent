import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  getServiceClient,
  lookupLabels,
  mapChain,
} from "../_shared/labels.ts";

const MAX_ADDRESSES = 500;
const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      Connection: "keep-alive",
      ...CORS_HEADERS,
    },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return jsonResponse({ success: false, error: "method_not_allowed" }, 405);
  }

  let body: Record<string, unknown>;
  try {
    const text = await req.text();
    if (!text || text.length > 1_500_000) {
      return jsonResponse({ success: false, error: "invalid_body_size" }, 400);
    }
    body = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return jsonResponse({ success: false, error: "invalid_json" }, 400);
  }

  const rawAddresses = body.addresses;
  if (!Array.isArray(rawAddresses) || rawAddresses.length === 0) {
    return jsonResponse(
      { success: false, error: "addresses_required" },
      400,
    );
  }
  if (rawAddresses.length > MAX_ADDRESSES) {
    return jsonResponse(
      {
        success: false,
        error: "too_many_addresses",
        message: `Maximum ${MAX_ADDRESSES} addresses per request`,
      },
      400,
    );
  }

  const addresses = [
    ...new Set(
      rawAddresses
        .map((a) => String(a || "").trim().toLowerCase())
        .filter((a) => a.startsWith("0x") && a.length === 42),
    ),
  ];

  if (addresses.length === 0) {
    return jsonResponse(
      { success: false, error: "no_valid_addresses" },
      400,
    );
  }

  const rawChains = Array.isArray(body.chains) ? body.chains : [];
  const chains = rawChains
    .map((c) => mapChain(String(c || "")))
    .filter(Boolean);

  try {
    const client = getServiceClient();
    // Labels via Walpulse quality-lookup (iq-v1). Requires Edge secrets:
    // WALPULSE_QUALITY_LOOKUP_ENABLED, WALPULSE_ANON_KEY, WALCERT_QUALITY_LOOKUP_SECRET.
    const hitMap = await lookupLabels(client, addresses, chains);
    const hits = [...hitMap.entries()].map(([address, hit]) => ({
      address,
      kind: hit.kind,
      name: hit.name,
      chain: hit.chain,
      sourcify_verified: hit.sourcify_verified,
      kleros_hit: hit.kleros_hit,
      kleros_risk: hit.kleros_risk,
      spellbook_categories: hit.spellbook_categories,
      source: hit.source,
    }));
    const found = new Set(hitMap.keys());
    const not_found = addresses.filter((a) => !found.has(a));

    return jsonResponse({
      success: true,
      data: {
        provider: "walpulse_quality_lookup",
        contract: "iq-v1",
        hits,
        not_found,
        queried: addresses.length,
      },
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "lookup_failed";
    console.error("api-wallet-labels error", e);
    return jsonResponse(
      { success: false, error: "lookup_failed", message: msg },
      500,
    );
  }
});
