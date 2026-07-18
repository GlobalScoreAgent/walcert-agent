import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient, lookupLabels, mapChain } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import { gradeActivity, summarizeLabels } from "./_shared/grades.ts";
import { analyzeWashCircular } from "./_shared/wash.ts";
import { logCertificateRequest } from "./_shared/logging.ts";

const FUNCTION_SLUG = "walcert-certificate-activity";
const CERT_TYPE = "activity";

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
    const counterpartiesRaw =
      (payload.counterparties as Array<Record<string, unknown>>) || [];
    const top = (payload.top_counterparties as Array<Record<string, unknown>>) || [];
    const counterparties = counterpartiesRaw.length ? counterpartiesRaw : top;

    const transfers = (payload.transfers as Array<Record<string, unknown>>) || [];
    const addresses = counterparties
      .map((c) => String(c.address || "").toLowerCase())
      .filter(Boolean);
    for (const t of transfers) {
      addresses.push(String(t.from || "").toLowerCase());
      addresses.push(String(t.to || "").toLowerCase());
    }

    const chains: string[] = [];
    for (const c of (payload.chains_analyzed as Array<Record<string, unknown>>) || []) {
      chains.push(mapChain(String(c.chain || "")));
    }
    for (const t of transfers) {
      chains.push(mapChain(String(t.chain || "")));
    }

    const hits = await lookupLabels(client, addresses, chains);
    const summaryHits = summarizeLabels(hits);

    const wash = analyzeWashCircular(
      wallet,
      transfers.map((t) => ({
        ts: t.ts ? String(t.ts) : undefined,
        from: t.from ? String(t.from) : undefined,
        to: t.to ? String(t.to) : undefined,
        value: Number(t.value) || 0,
        chain: t.chain ? String(t.chain) : undefined,
      })),
    );

    let cexTx = 0;
    const totalTx = Number(payload.total_transfers) || transfers.length || 1;
    for (const c of counterparties) {
      const addr = String(c.address || "").toLowerCase();
      if (hits.get(addr)?.kind === "cex") {
        cexTx += Number(c.tx_count) || 1;
      }
    }
    // Also count transfers touching cex
    let cexFromTransfers = 0;
    for (const t of transfers) {
      const f = String(t.from || "").toLowerCase();
      const to = String(t.to || "").toLowerCase();
      if (hits.get(f)?.kind === "cex" || hits.get(to)?.kind === "cex") cexFromTransfers++;
    }
    const cex_pct = Math.round(
      (1000 * Math.max(cexTx, cexFromTransfers)) / Math.max(totalTx, 1),
    ) / 10;

    const unique_counterparties = Number(
      payload.unique_counterparties ?? counterparties.length,
    );
    const sanctions_hit = summaryHits.ofac > 0;
    const mixer_hit = summaryHits.mixer > 0;

    const grade = gradeActivity({
      unique_counterparties,
      cex_pct,
      wash,
      sanctions_hit,
      mixer_hit,
    });

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (!wash.circular_patterns) strengths.push({ eng: "No evident circular patterns", esp: "Sin patrones circulares evidentes" });
    if (unique_counterparties >= 10) strengths.push({ eng: "Acceptable counterparty diversity", esp: "Diversidad de contrapartes aceptable" });
    if (wash.wash_trading_risk === "low") strengths.push({ eng: "Low wash trading risk", esp: "Bajo riesgo de wash trading" });
    if (cex_pct >= 20) concerns.push({ eng: "CEX interaction still significant", esp: "Interacción con CEX todavía relevante" });
    if (wash.circular_patterns) concerns.push({ eng: "Circular patterns detected", esp: "Patrones circulares detectados" });
    if (wash.wash_trading_risk !== "low") concerns.push({ eng: "Wash trading signals", esp: "Señales de wash trading" });
    if (sanctions_hit) concerns.push({ eng: "Interaction with OFAC-sanctioned address", esp: "Interacción con dirección sancionada (OFAC)" });
    if (mixer_hit) concerns.push({ eng: "Mixer interaction", esp: "Interacción con mixer" });

    const summary = {
      eng: `Recent activity shows ${unique_counterparties} counterparties with ${wash.wash_trading_risk} wash risk.`,
      esp: `La actividad reciente muestra ${unique_counterparties} contrapartes con riesgo de wash ${wash.wash_trading_risk}.`,
    };

    const cert = await buildCertificate({
      type: "ACTIVITY",
      wallet,
      analyzed_at,
      grade,
      summary,
      details: {
        window_days: Number(payload.window_days) || 7,
        unique_counterparties,
        cex_interaction_percentage: cex_pct,
        wash_trading_risk: wash.wash_trading_risk,
        circular_patterns: wash.circular_patterns,
        bidirectional_pair_share: wash.bidirectional_pair_share,
        sanctions_hit,
        mixer_hit,
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
    console.error("activity scoring error", e);
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
