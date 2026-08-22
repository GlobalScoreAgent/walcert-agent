import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient } from "./_shared/client.ts";

const FUNCTION_SLUG = "walcert-certificate-onchain";

function str(v: unknown): string | null {
  const s = (v ?? "").toString().trim();
  return s ? s : null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }

  // Un 401 aqui nunca toca la BD (misma regla que el resto de Edge Functions).
  const authErr = await requireAgentSecret(req);
  if (authErr) return authErr;

  let body: Record<string, unknown>;
  try {
    const parsed = await readJsonBody(req);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("body_not_object");
    }
    body = parsed as Record<string, unknown>;
  } catch (e) {
    const msg = e instanceof Error ? e.message : "invalid_body";
    return jsonResponse({ error: "bad_request", message: msg }, 400);
  }

  const certificateId = str(body.certificate_id);
  const onchain = body.onchain;
  if (
    !certificateId ||
    onchain === undefined ||
    onchain === null ||
    typeof onchain !== "object"
  ) {
    return jsonResponse(
      { error: "bad_request", message: "certificate_id and onchain required" },
      400,
    );
  }

  const onchainObj = onchain as Record<string, unknown>;
  const receiptBnb = body.receipt_bnb;
  const update: Record<string, unknown> = {
    onchain: onchainObj,
    signature: body.signature ?? null,
    onchain_tx_hash: str(body.tx_hash) ?? str(onchainObj.tx_hash),
    onchain_updated_at: new Date().toISOString(),
  };
  if (receiptBnb && typeof receiptBnb === "object") {
    update.receipt_bnb = receiptBnb;
    const dh = str((receiptBnb as Record<string, unknown>).data_hash);
    if (dh) update.data_hash = dh;
  }

  try {
    const client = getServiceClient();
    const { data, error } = await client
      .schema("walcert")
      .from("certificate_requests")
      .update(update)
      .eq("certificate_id", certificateId)
      .select("id");

    if (error) {
      console.error(`${FUNCTION_SLUG} update error`, error.message || error);
      return jsonResponse({ ok: false, error: "update_failed" }, 500);
    }
    return jsonResponse({ ok: true, updated: data?.length ?? 0 });
  } catch (e) {
    console.error(`${FUNCTION_SLUG} exception`, e instanceof Error ? e.message : e);
    return jsonResponse({ ok: false, error: "unexpected" }, 500);
  }
});
