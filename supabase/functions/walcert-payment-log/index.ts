import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient } from "./_shared/client.ts";

const FUNCTION_SLUG = "walcert-payment-log";

function lower(v: unknown): string | null {
  const s = (v ?? "").toString().trim();
  return s ? s.toLowerCase() : null;
}

function str(v: unknown): string | null {
  const s = (v ?? "").toString().trim();
  return s ? s : null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }

  // A 401 here never inserts anything (same rule as certificate logging).
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

  // Require at least one identifying field of the settlement.
  if (!body.tx_hash && !body.payer && !body.network) {
    return jsonResponse(
      { error: "bad_request", message: "missing payment identifiers" },
      400,
    );
  }

  const row = {
    certificate_id: str(body.certificate_id),
    certificate_type: str(body.certificate_type),
    wallet: lower(body.wallet),
    network: str(body.network),
    scheme: str(body.scheme),
    asset: lower(body.asset),
    pay_to: lower(body.pay_to),
    payer: lower(body.payer),
    amount: str(body.amount),
    price: str(body.price),
    nonce: str(body.nonce),
    tx_hash: str(body.tx_hash),
    success: body.success === true,
    facilitator: str(body.facilitator),
    settle_response: body.settle_response ?? null,
    payment_requirements: body.payment_requirements ?? null,
    payment_payload: body.payment_payload ?? null,
  };

  try {
    const client = getServiceClient();
    const { data, error } = await client
      .schema("walcert")
      .from("x402_payments")
      .insert(row)
      .select("id")
      .single();

    if (error) {
      console.error(`${FUNCTION_SLUG} insert error`, error.message || error);
      return jsonResponse({ ok: false, error: "insert_failed" }, 500);
    }
    return jsonResponse({ ok: true, id: data?.id ?? null });
  } catch (e) {
    console.error(`${FUNCTION_SLUG} exception`, e instanceof Error ? e.message : e);
    return jsonResponse({ ok: false, error: "unexpected" }, 500);
  }
});
