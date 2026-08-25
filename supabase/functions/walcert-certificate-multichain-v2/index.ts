import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import {
  FORMULA_VERSION,
  assignGradeMultichainV2,
  computeMultichainV2Metrics,
  inputsHash,
  type ChainRow,
} from "./_shared/multichain_v2.ts";
import { logCertificateRequest, parseAccessMeta } from "./_shared/logging.ts";

const FUNCTION_SLUG = "walcert-certificate-multichain-v2";

function accessScope(channel: string): string {
  if (channel === "summit") return "summit";
  if (channel === "internal") return "internal";
  return "public";
}

function logCertificateType(channel: string): string {
  return channel === "summit" ? "multichain_v2" : "multichain";
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405);
  }
  const authErr = await requireAgentSecret(req);
  if (authErr) return authErr;

  let wallet: string;
  let analyzed_at: string;
  let payload: Record<string, unknown>;
  let access = parseAccessMeta(null);
  try {
    const body = await readJsonBody(req);
    access = parseAccessMeta(body);
    ({ wallet, analyzed_at, payload } = parseRequestBody(body));
  } catch (e) {
    const msg = e instanceof Error ? e.message : "invalid_body";
    return jsonResponse({ error: "bad_request", message: msg }, 400);
  }

  const client = getServiceClient();

  try {
    const chains = ((payload.chains as ChainRow[]) || []).map((c) => ({
      name: c.name || c.chain,
      chain: c.chain,
      chain_id: c.chain_id,
      label: c.label,
      category_label: c.category_label || c.category,
      is_testnet: c.is_testnet,
      is_appchain: c.is_appchain,
      first_seen_at: c.first_seen_at,
      last_seen_at: c.last_seen_at,
      first_transaction: c.first_transaction,
      last_transaction: c.last_transaction,
      tx_count: c.tx_count,
      transfer_count: c.transfer_count,
      gas_spent_quote: c.gas_spent_quote,
      intensity_sampled: c.intensity_sampled,
    }));

    const metrics = computeMultichainV2Metrics(chains);
    // Prefer agent intensity block if present (already merged into chains)
    const intensityPayload = payload.intensity as Record<string, unknown> | undefined;
    if (intensityPayload && typeof intensityPayload === "object") {
      if (intensityPayload.total_tx_count != null) {
        metrics.intensity.total_tx_count = Number(intensityPayload.total_tx_count) ||
          metrics.intensity.total_tx_count;
      }
      if (intensityPayload.tx_hhi != null) {
        metrics.intensity.tx_hhi = Number(intensityPayload.tx_hhi) ||
          metrics.intensity.tx_hhi;
      }
      if (intensityPayload.weighted_activity_score != null) {
        metrics.intensity.weighted_activity_score =
          Number(intensityPayload.weighted_activity_score) ||
          metrics.intensity.weighted_activity_score;
      }
      if (intensityPayload.primary_chain) {
        metrics.intensity.primary_chain = String(intensityPayload.primary_chain);
      }
      if (intensityPayload.gas_footprint_quote != null) {
        metrics.intensity.gas_footprint_quote = Number(
          intensityPayload.gas_footprint_quote,
        );
      }
    }

    const { grade, breakdown } = assignGradeMultichainV2(metrics);
    const ihash = await inputsHash(breakdown.inputs);

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (metrics.total_chains_mainnet >= 4) {
      strengths.push({
        eng: "Broad multi-chain footprint",
        esp: "Footprint multi-chain amplio",
      });
    }
    if (metrics.intensity.total_tx_count >= 50) {
      strengths.push({
        eng: "Meaningful activity intensity on sampled chains",
        esp: "Intensidad de actividad relevante en chains muestreadas",
      });
    }
    if (metrics.core_ecosystem_count >= 2) {
      strengths.push({
        eng: "Presence in multiple core ecosystems",
        esp: "Presencia en varios ecosistemas core",
      });
    }
    if (metrics.total_chains_mainnet <= 1) {
      concerns.push({
        eng: "Limited to few mainnets",
        esp: "Limitado a pocos mainnets",
      });
    }
    if (metrics.intensity.total_tx_count < 15) {
      concerns.push({
        eng: "Low transaction intensity on sampled chains",
        esp: "Baja intensidad de transacciones en chains muestreadas",
      });
    }
    if (metrics.dormant_ratio > 0.5) {
      concerns.push({
        eng: "High share of dormant chains",
        esp: "Alta proporción de chains dormidas",
      });
    }

    const summary = {
      eng:
        `Multichain v2: ${metrics.total_chains_mainnet} mainnets, ` +
        `${metrics.intensity.total_tx_count} txs on ${metrics.intensity.chains_sampled} sampled chains, ` +
        `span ${metrics.activity_span_days}d.`,
      esp:
        `Multichain v2: ${metrics.total_chains_mainnet} mainnets, ` +
        `${metrics.intensity.total_tx_count} txs en ${metrics.intensity.chains_sampled} chains muestreadas, ` +
        `span ${metrics.activity_span_days}d.`,
    };

    const channel = String(access.access_channel || "direct");
    const certType = logCertificateType(channel);

    const cert = await buildCertificate({
      type: "MULTICHAIN",
      wallet,
      analyzed_at,
      grade,
      summary,
      version: "2.0",
      formula_version: FORMULA_VERSION,
      grade_breakdown: breakdown,
      inputs_hash: ihash,
      details: {
        provider: "goldrush",
        access_scope: accessScope(channel),
        core_ecosystem_list_version: metrics.core_ecosystem_list_version,
        total_chains_mainnet: metrics.total_chains_mainnet,
        total_chains_testnet: metrics.total_chains_testnet,
        ecosystem_count: metrics.ecosystem_count,
        l2_or_appchain_count: metrics.l2_or_appchain_count,
        activity_span_days: metrics.activity_span_days,
        active_chains_30d: metrics.active_chains_30d,
        active_chains_90d: metrics.active_chains_90d,
        dormant_ratio: metrics.dormant_ratio,
        consistency_score: metrics.consistency_score,
        recency_score: metrics.recency_score,
        footprint_concentration: metrics.footprint_concentration,
        core_ecosystems: metrics.core_ecosystems,
        core_ecosystem_count: metrics.core_ecosystem_count,
        intensity: metrics.intensity,
        chains: metrics.chains,
      },
      strengths,
      concerns,
    });

    await logCertificateRequest(client, {
      certificate_id: cert.certificate_id as string,
      certificate_type: certType,
      function_slug: FUNCTION_SLUG,
      wallet,
      chain_id: cert.chain_id as number,
      status: "ok",
      grade: cert.grade as string,
      grade_label: (cert.grade_label as { eng: string }).eng,
      data_hash: cert.data_hash as string,
      analyzed_at,
      request_payload: payload,
      certificate: cert,
      access_channel: access.access_channel,
      marketplace: access.marketplace,
      billing: access.billing,
    });

    return jsonResponse(cert);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "scoring_failed";
    console.error("multichain v2 scoring error", e);
    await logCertificateRequest(client, {
      certificate_type: logCertificateType(String(access.access_channel || "direct")),
      function_slug: FUNCTION_SLUG,
      wallet,
      status: "error",
      analyzed_at,
      request_payload: payload,
      error_message: msg,
      access_channel: access.access_channel,
      marketplace: access.marketplace,
      billing: access.billing,
    });
    return jsonResponse({ error: "scoring_failed", message: msg }, 500);
  }
});
