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
};

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
      });
    if (error) {
      console.error("logCertificateRequest insert error", error.message || error);
    }
  } catch (e) {
    console.error("logCertificateRequest exception", e instanceof Error ? e.message : e);
  }
}
