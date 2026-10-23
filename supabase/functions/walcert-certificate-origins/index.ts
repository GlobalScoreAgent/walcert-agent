import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import { getServiceClient, lookupLabels, mapChain } from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import { logCertificateRequest, parseAccessMeta } from "./_shared/logging.ts";
import {
  FORMULA_VERSION,
  assignGradeOriginsV2,
  computeOriginsSignals,
  inputsHash,
  type Inflow,
} from "./_shared/origins_v2.ts";

const FUNCTION_SLUG = "walcert-certificate-origins";
const CERT_TYPE = "origins";

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
    const inflowsRaw = (payload.inflows as Inflow[]) || [];
    const sendersRaw = (payload.senders as Array<Record<string, unknown>>) || [];
    const topSenders = (payload.top_senders as Array<Record<string, unknown>>) || [];
    const senders = sendersRaw.length ? sendersRaw : topSenders;

    const addresses = [
      ...new Set([
        ...inflowsRaw.map((s) => String(s.from || "").toLowerCase()).filter(Boolean),
        ...senders.map((s) => String(s.address || "").toLowerCase()).filter(Boolean),
      ]),
    ];

    const chains = [
      ...new Set(
        [
          ...inflowsRaw.map((s) => {
            const id = Number(s.chain_id);
            if (id === 1) return "ethereum";
            if (id === 56) return "bnb";
            if (id === 8453) return "base";
            if (id === 42161) return "arbitrum";
            if (id === 137) return "polygon";
            if (id === 42220) return "celo";
            if (id === 100) return "gnosis";
            if (id === 10) return "optimism";
            return "";
          }),
          ...senders.map((s) => mapChain(String(s.chain || ""))),
        ].filter(Boolean),
      ),
    ];
    const chainsAnalyzed = (payload.chains_analyzed as Array<Record<string, unknown>>) || [];
    for (const c of chainsAnalyzed) {
      chains.push(mapChain(String(c.chain || "")));
    }

    const pairs = [
      ...inflowsRaw.map((s) => ({
        address: String(s.from || "").toLowerCase(),
        chain_id: Number(s.chain_id) || null,
        chain: null as string | null,
      })),
      ...senders.map((s) => ({
        address: String(s.address || "").toLowerCase(),
        chain_id: Number(s.chain_id) || null,
        chain: String(s.chain || "") || null,
      })),
    ].filter((p) => p.address.startsWith("0x"));

    const hits = await lookupLabels(client, addresses, chains, pairs);

    // Prefer inflows path (v2); fall back to empty inflows → still grade from senders via synthetic inflows
    let inflows = inflowsRaw;
    if (!inflows.length && senders.length) {
      inflows = senders.map((s) => ({
        from: String(s.address || "").toLowerCase(),
        usd: Number(s.total_value_usd) || 0,
        usd_method: "legacy_sender",
        asset_category: "external",
        chain_id: Number(s.chain_id) || undefined,
      }));
    }

    const computed = computeOriginsSignals({
      inflows,
      hits,
      analyzed_at,
    });

    const { grade, breakdown } = assignGradeOriginsV2({
      cex_pct: computed.cex_pct,
      unique_senders: computed.unique_senders,
      mixing_risk: computed.mixing_risk,
      first_funding_age_days: computed.first_funding_age_days,
      sanctions_hit: computed.sanctions_hit,
      hhi: computed.hhi,
      top1_pct: computed.top1_pct,
      airdrop_pct: computed.airdrop_pct,
      kleros_risk_hit: computed.kleros_risk_hit,
    });

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (computed.mixing_risk === "low") {
      strengths.push({ eng: "Low mixing risk", esp: "Bajo riesgo de mixing" });
    }
    if (computed.unique_senders >= 5 && computed.hhi <= 0.55) {
      strengths.push({
        eng: "Acceptable sender diversity",
        esp: "Diversidad de senders aceptable",
      });
    }
    if ((computed.first_funding_age_days ?? 0) >= 365) {
      strengths.push({ eng: "Long-standing funding", esp: "Funding antiguo" });
    }
    if (computed.protocol_pct >= 15 && computed.mixing_risk === "low") {
      strengths.push({
        eng: "Meaningful protocol / DeFi funding share",
        esp: "Participación relevante de funding vía protocolos / DeFi",
      });
    }
    if (computed.sourcify_verified_sender_pct >= 30) {
      strengths.push({
        eng: `Sourcify-verified senders among labeled (~${computed.sourcify_verified_sender_pct}%)`,
        esp: `Senders verificados en Sourcify entre labeled (~${computed.sourcify_verified_sender_pct}%)`,
      });
    }
    if (computed.cex_pct >= 50) {
      concerns.push({
        eng: "Significant CEX dependency",
        esp: "Dependencia relevante de CEX",
      });
    }
    if (computed.airdrop_pct >= 40) {
      concerns.push({
        eng: `High airdrop / reward funding share (~${computed.airdrop_pct}%)`,
        esp: `Alta participación de funding tipo airdrop/reward (~${computed.airdrop_pct}%)`,
      });
    }
    if (computed.kleros_risk_hit) {
      concerns.push({
        eng: "Kleros Scout risk tags on funding counterparties",
        esp: "Tags de riesgo Kleros Scout en contrapartes de funding",
      });
    }
    if (computed.mixing_risk === "high") {
      concerns.push({
        eng: "Mixer interaction detected",
        esp: "Interacción con mixer detectada",
      });
    }
    if (computed.sanctions_hit) {
      concerns.push({
        eng: "Match with OFAC-sanctioned address",
        esp: "Coincidencia con dirección sancionada (OFAC)",
      });
    }
    if (computed.top1_pct >= 70 || computed.hhi >= 0.70) {
      concerns.push({
        eng:
          `Extreme funding concentration among priced inflows (top1 ${computed.top1_pct}%, HHI ${computed.hhi})`,
        esp:
          `Concentración extrema de funding en inflows priced (top1 ${computed.top1_pct}%, HHI ${computed.hhi})`,
      });
    }

    const coverage = computed.priced_coverage_pct;
    const vr = computed.value_relevant_inflows;
    const vrPriced = computed.value_relevant_priced;
    const pricedNote =
      ` HHI/top1 on priced USD; priced coverage ~${coverage}% of value-relevant inflows` +
      ` (${vrPriced}/${vr} native/ERC-20 amount>0; NFTs excluded from denominator).`;

    const summary = {
      eng: computed.sanctions_hit
        ? "Funding linked to OFAC-sanctioned addresses."
        : `Funding origins show ${computed.main_origin_type} dominance with ${computed.unique_senders} unique senders and ${computed.mixing_risk} mixing risk.${pricedNote} (${FORMULA_VERSION})`,
      esp: computed.sanctions_hit
        ? "Orígenes vinculados a direcciones sancionadas (OFAC)."
        : `Los orígenes muestran dominancia ${computed.main_origin_type}, ${computed.unique_senders} senders únicos y riesgo de mixing ${computed.mixing_risk}. HHI/top1 sobre USD priced; cobertura priced ~${coverage}% de inflows value-relevant (${vrPriced}/${vr} native/ERC-20 amount>0; NFTs fuera del denominador). (${FORMULA_VERSION})`,
    };

    const signals = computed.signals as Record<string, unknown>;
    const hash = await inputsHash({
      wallet,
      networks: payload.networks || [],
      total_inflows: inflows.length,
      priced: payload.priced_inflows,
      value_relevant: computed.value_relevant_inflows,
      value_relevant_priced: computed.value_relevant_priced,
      priced_coverage_pct: computed.priced_coverage_pct,
      unique_senders: computed.unique_senders,
      total_usd: payload.total_value_usd_priced,
      formula: FORMULA_VERSION,
    });

    const cert = await buildCertificate({
      type: "ORIGINS",
      wallet,
      analyzed_at,
      grade,
      summary,
      version: "2.0",
      formula_version: FORMULA_VERSION,
      grade_breakdown: breakdown,
      inputs_hash: hash,
      details: {
        main_origin_type: computed.main_origin_type,
        cex_percentage: computed.cex_pct,
        bridge_percentage: computed.bridge_pct,
        unique_senders: computed.unique_senders,
        mixing_risk: computed.mixing_risk,
        first_funding_age_days: computed.first_funding_age_days,
        sanctions_hit: computed.sanctions_hit,
        hhi: signals.hhi,
        hhi_value_relevant_priced: computed.hhi_value_relevant_priced,
        concentration: signals.concentration,
        pricing_coverage: signals.pricing_coverage,
        value_relevant_inflows: computed.value_relevant_inflows,
        value_relevant_priced: computed.value_relevant_priced,
        value_relevant_unpriced: computed.value_relevant_unpriced,
        priced_coverage_pct: computed.priced_coverage_pct,
        category_percentages: signals.category_percentages,
        cex_quality: signals.cex_quality,
        temporal_funding: signals.temporal_funding,
        direct_exposure: signals.direct_exposure,
        quality_enrichment: signals.quality_enrichment,
        organic_vs_synthetic: signals.organic_vs_synthetic,
        formula_version: FORMULA_VERSION,
        priced_inflows: payload.priced_inflows ?? null,
        unpriced_inflows: payload.unpriced_inflows ?? null,
        total_value_usd_priced: payload.total_value_usd_priced ?? null,
        airdrop_percentage: computed.airdrop_pct,
        protocol_percentage: computed.protocol_pct,
        label_hits: {
          ofac: computed.sanctions_hit ? 1 : 0,
          mixer: (signals.direct_exposure as { mixer_hits?: number })?.mixer_hits || 0,
          cex: 0,
          bridge: 0,
          airdrop: computed.airdrop_pct > 0 ? 1 : 0,
          protocol: computed.protocol_pct > 0 ? 1 : 0,
          kleros_risk: computed.kleros_risk_hit ? 1 : 0,
        },
      },
      strengths,
      concerns,
    });

    await logCertificateRequest(client, {
      certificate_id: cert.certificate_id as string,
      certificate_type: CERT_TYPE,
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
    console.error("origins scoring error", e);
    await logCertificateRequest(client, {
      certificate_type: CERT_TYPE,
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
