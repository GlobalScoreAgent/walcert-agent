import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

export type CertificateRequestRow = {
  certificate_id?: string | null;
  certificate_type: string;
  function_slug: string;
  wallet: string;
  chain_id?: number | null;
  status: "ok" | "error";
  grade?: string | null;
  grade_label?: string | null;
  data_hash?: string | null;
  analyzed_at?: string | null;
  request_payload: unknown;
  certificate?: unknown | null;
  error_message?: string | null;
  access_channel?: string | null;
  marketplace?: string | null;
  billing?: string | null;
};

export type WalcertAccessMeta = {
  access_channel?: string;
  marketplace?: string | null;
  billing?: string;
};

/** Extract attribution meta from the agent → Edge request body. */
export function parseAccessMeta(body: unknown): WalcertAccessMeta {
  if (!body || typeof body !== "object") {
    return { access_channel: "direct", marketplace: null, billing: "x402" };
  }
  const raw = (body as Record<string, unknown>)._walcert_access;
  if (!raw || typeof raw !== "object") {
    return { access_channel: "direct", marketplace: null, billing: "x402" };
  }
  const m = raw as Record<string, unknown>;
  const channelRaw = String(m.access_channel || "direct").toLowerCase();
  const channel =
    channelRaw === "internal" || channelRaw === "summit"
      ? channelRaw
      : "direct";
  const billing = String(m.billing || "x402").toLowerCase();
  const marketplace =
    m.marketplace == null || m.marketplace === ""
      ? null
      : String(m.marketplace).toLowerCase();
  // Persist marketplace for internal (ACP) and summit (bsg2026) channels.
  const keepMarketplace = channel === "internal" || channel === "summit";
  return {
    access_channel: channel,
    marketplace: keepMarketplace ? marketplace : null,
    billing: ["x402", "marketplace", "free"].includes(billing) ? billing : "x402",
  };
}

/**
 * Best-effort insert of one processed request into walcert.certificate_requests.
 * Never throws: a logging failure must not break the response to the agent.
 */
export async function logCertificateRequest(
  client: SupabaseClient,
  row: CertificateRequestRow,
): Promise<void> {
  try {
    const { error } = await client
      .schema("walcert")
      .from("certificate_requests")
      .insert({
        certificate_id: row.certificate_id ?? null,
        certificate_type: row.certificate_type,
        function_slug: row.function_slug,
        wallet: row.wallet.toLowerCase(),
        chain_id: row.chain_id ?? null,
        status: row.status,
        grade: row.grade ?? null,
        grade_label: row.grade_label ?? null,
        data_hash: row.data_hash ?? null,
        analyzed_at: row.analyzed_at ?? null,
        request_payload: row.request_payload ?? {},
        certificate: row.certificate ?? null,
        error_message: row.error_message ?? null,
        access_channel: row.access_channel ?? "direct",
        marketplace: row.marketplace ?? null,
        billing: row.billing ?? "x402",
      });
    if (error) {
      console.error("logCertificateRequest insert error", error.message || error);
    }
  } catch (e) {
    console.error("logCertificateRequest exception", e instanceof Error ? e.message : e);
  }
}
