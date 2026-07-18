import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import { gradeMultichain } from "./_shared/grades.ts";
import { logCertificateRequest } from "./_shared/logging.ts";

const FUNCTION_SLUG = "walcert-certificate-multichain";
const CERT_TYPE = "multichain";

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }
  const authErr = await requireAgentSecret(req);
  if (authErr) return authErr;

  // Parse first: invalid payloads (400) are handled by the agent and NOT logged.
  let wallet: string;
  let analyzed_at: string;
  let payload: Record<string, unknown>;
  try {
    const body = await readJsonBody(req);
    ({ wallet, analyzed_at, payload } = parseRequestBody(body));
  } catch (e) {
    const msg = e instanceof Error ? e.message : "invalid_body";
    return jsonResponse({ error: "bad_request", message: msg }, 400);
  }

  const client = getServiceClient();

  try {
    const chains = (payload.chains as Array<Record<string, unknown>>) || [];
    const chain_count = Number(
      payload.total_chains_with_activity ?? chains.length,
    );
    const activity_span_days = Number(payload.activity_span_days) || 0;
    const main_chains = chains
      .map((c) => String(c.chain || "").toLowerCase())
      .filter(Boolean)
      .slice(0, 8);

    const grade = gradeMultichain({ chain_count, activity_span_days });

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (chain_count >= 3) strengths.push({ eng: "Good multi-chain coverage", esp: "Buena cobertura multi-chain" });
    if (activity_span_days >= 365) strengths.push({ eng: "High activity longevity", esp: "Alta longevidad de actividad" });
    if (chain_count <= 1) concerns.push({ eng: "Presence limited to few chains", esp: "Presencia limitada a pocas chains" });
    if (activity_span_days < 30) concerns.push({ eng: "Very recent activity or short span", esp: "Actividad muy reciente o span corto" });

    const summary = {
      eng: `Multi-chain presence across ${chain_count} networks with ${activity_span_days} days activity span.`,
      esp: `Presencia multi-chain en ${chain_count} redes con span de actividad de ${activity_span_days} días.`,
    };

    const cert = await buildCertificate({
      type: "MULTICHAIN",
      wallet,
      analyzed_at,
      grade,
      summary,
      details: {
        total_chains_with_activity: chain_count,
        activity_span_days,
        main_chains,
      },
      strengths,
      concerns,
    });

    await logCertificateRequest(client, {
      certificate_id: cert.certificate_id,
      certificate_type: CERT_TYPE,
      function_slug: FUNCTION_SLUG,
      wallet,
      chain_id: cert.chain_id,
      status: "ok",
      grade: cert.grade,
      grade_label: cert.grade_label.eng,
      data_hash: cert.data_hash,
      analyzed_at,
      request_payload: payload,
      certificate: cert,
    });

    return jsonResponse(cert);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "scoring_failed";
    console.error("multichain scoring error", e);
    await logCertificateRequest(client, {
      certificate_type: CERT_TYPE,
      function_slug: FUNCTION_SLUG,
      wallet,
      status: "error",
      analyzed_at,
      request_payload: payload,
      error_message: msg,
    });
    return jsonResponse({ error: "scoring_failed", message: msg }, 500);
  }
});
