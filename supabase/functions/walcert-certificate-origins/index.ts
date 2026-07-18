import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient, lookupLabels, mapChain } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody, daysSince } from "./_shared/certificate.ts";
import { gradeOrigins, summarizeLabels } from "./_shared/grades.ts";
import { logCertificateRequest } from "./_shared/logging.ts";

const FUNCTION_SLUG = "walcert-certificate-origins";
const CERT_TYPE = "origins";

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
    const sendersRaw = (payload.senders as Array<Record<string, unknown>>) || [];
    const topSenders = (payload.top_senders as Array<Record<string, unknown>>) || [];
    const senders = sendersRaw.length ? sendersRaw : topSenders;

    const addresses = senders.map((s) => String(s.address || "").toLowerCase()).filter(Boolean);
    const chains = [
      ...new Set(
        senders.map((s) => mapChain(String(s.chain || ""))).filter(Boolean),
      ),
    ];
    const chainsAnalyzed = (payload.chains_analyzed as Array<Record<string, unknown>>) || [];
    for (const c of chainsAnalyzed) {
      chains.push(mapChain(String(c.chain || "")));
    }

    const hits = await lookupLabels(client, addresses, chains);
    const summaryHits = summarizeLabels(hits);

    let totalUsd = 0;
    let cexUsd = 0;
    let bridgeUsd = 0;
    let mixerHits = 0;
    for (const s of senders) {
      const addr = String(s.address || "").toLowerCase();
      const usd = Number(s.total_value_usd) || 0;
      totalUsd += usd;
      const hit = hits.get(addr);
      if (hit?.kind === "cex") cexUsd += usd;
      if (hit?.kind === "bridge") bridgeUsd += usd;
      if (hit?.kind === "mixer") mixerHits++;
    }

    const firstFunding = payload.first_funding as Record<string, unknown> | null;
    if (firstFunding?.from) {
      const ff = String(firstFunding.from).toLowerCase();
      const hit = hits.get(ff);
      if (hit?.kind === "cex" && totalUsd <= 0) {
        // keep percentages from value-weighted senders
      }
    }

    const cex_pct = totalUsd > 0 ? Math.round((1000 * cexUsd) / totalUsd) / 10 : 0;
    const bridge_pct = totalUsd > 0 ? Math.round((1000 * bridgeUsd) / totalUsd) / 10 : 0;
    const unique_senders = Number(
      (payload.origin_summary as Record<string, unknown>)?.unique_senders ??
        addresses.length,
    );
    const age = daysSince(
      firstFunding?.timestamp ? String(firstFunding.timestamp) : null,
    );

    let mixing_risk: "low" | "medium" | "high" = "low";
    if (mixerHits > 0 || summaryHits.mixer > 0) mixing_risk = "high";
    else if (unique_senders <= 1) mixing_risk = "medium";

    const sanctions_hit = summaryHits.ofac > 0 ||
      (firstFunding?.from
        ? hits.get(String(firstFunding.from).toLowerCase())?.kind === "ofac"
        : false);

    let main_origin_type = "other";
    if (cex_pct >= bridge_pct && cex_pct > 0) main_origin_type = "cex";
    else if (bridge_pct > 0) main_origin_type = "bridge";
    else if (mixing_risk === "high") main_origin_type = "mixer";

    const grade = gradeOrigins({
      cex_pct,
      bridge_pct,
      unique_senders,
      mixing_risk,
      first_funding_age_days: age,
      sanctions_hit,
    });

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (mixing_risk === "low") strengths.push({ eng: "Low mixing risk", esp: "Bajo riesgo de mixing" });
    if (unique_senders >= 5) strengths.push({ eng: "Acceptable sender diversity", esp: "Diversidad de senders aceptable" });
    if (age && age >= 365) strengths.push({ eng: "Long-standing funding", esp: "Funding antiguo" });
    if (cex_pct >= 50) concerns.push({ eng: "Significant CEX dependency", esp: "Dependencia relevante de CEX" });
    if (mixing_risk === "high") concerns.push({ eng: "Mixer interaction detected", esp: "Interacción con mixer detectada" });
    if (sanctions_hit) concerns.push({ eng: "Match with OFAC-sanctioned address", esp: "Coincidencia con dirección sancionada (OFAC)" });

    const summary = {
      eng: sanctions_hit
        ? "Funding linked to OFAC-sanctioned addresses."
        : `Funding origins show ${main_origin_type} dominance with ${unique_senders} unique senders and ${mixing_risk} mixing risk.`,
      esp: sanctions_hit
        ? "Orígenes vinculados a direcciones sancionadas (OFAC)."
        : `Los orígenes muestran dominancia ${main_origin_type}, ${unique_senders} senders únicos y riesgo de mixing ${mixing_risk}.`,
    };

    const cert = await buildCertificate({
      type: "ORIGINS",
      wallet,
      analyzed_at,
      grade,
      summary,
      details: {
        main_origin_type,
        cex_percentage: cex_pct,
        bridge_percentage: bridge_pct,
        unique_senders,
        mixing_risk,
        first_funding_age_days: age,
        sanctions_hit,
        label_hits: summaryHits,
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
    console.error("origins scoring error", e);
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
