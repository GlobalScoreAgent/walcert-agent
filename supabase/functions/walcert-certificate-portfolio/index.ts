import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import {
  computePortfolioMetrics,
  gradePortfolio,
  type PortfolioPosition,
} from "./_shared/portfolio_metrics.ts";
import { logCertificateRequest } from "./_shared/logging.ts";

const FUNCTION_SLUG = "walcert-certificate-portfolio";
const CERT_TYPE = "portfolio";

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
    const positions = (
      (payload.positions as PortfolioPosition[]) ||
      (payload.top_positions as PortfolioPosition[]) ||
      []
    );

    const metrics = computePortfolioMetrics(positions);
    const grade = gradePortfolio(metrics);

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (metrics.liquid_ratio >= 60) strengths.push({ eng: "Good liquidity", esp: "Buena liquidez" });
    if ((metrics.category_distribution.meme_or_other || 0) <= 15) {
      strengths.push({ eng: "Low meme exposure", esp: "Baja exposición a memes" });
    }
    if (metrics.defi_exposure_pct >= 10) strengths.push({ eng: "Real DeFi presence", esp: "Presencia DeFi real" });
    if (metrics.total_value_usd < 2000) {
      concerns.push({ eng: "Portfolio size still moderate", esp: "Tamaño de portafolio todavía moderado" });
    }
    if (metrics.concentration.top1_share > 0.7) {
      concerns.push({ eng: "High concentration in a single asset", esp: "Alta concentración en un solo activo" });
    }
    if ((metrics.category_distribution.meme_or_other || 0) > 40) {
      concerns.push({ eng: "High exposure to speculative assets", esp: "Exposición elevada a activos especulativos" });
    }
    if (metrics.spam_filtered_count > 0) {
      concerns.push({ eng: "Spam/unpriced positions filtered out", esp: "Posiciones spam/unpriced filtradas" });
    }

    const summary = {
      eng: `Portfolio ~$${metrics.total_value_usd} with ${metrics.liquid_ratio}% liquid and top-1 share ${(metrics.concentration.top1_share * 100).toFixed(0)}%.`,
      esp: `Portafolio ~$${metrics.total_value_usd} con ${metrics.liquid_ratio}% líquido y concentración top-1 ${(metrics.concentration.top1_share * 100).toFixed(0)}%.`,
    };

    const cert = await buildCertificate({
      type: "PORTFOLIO",
      wallet,
      analyzed_at,
      grade,
      summary,
      details: {
        total_value_usd: metrics.total_value_usd,
        liquid_ratio: metrics.liquid_ratio,
        category_distribution: metrics.category_distribution,
        concentration: metrics.concentration,
        dust_filtered_count: metrics.dust_filtered_count,
        spam_filtered_count: metrics.spam_filtered_count,
        defi_exposure_pct: metrics.defi_exposure_pct,
        positions_used: metrics.positions_used,
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
    console.error("portfolio scoring error", e);
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
