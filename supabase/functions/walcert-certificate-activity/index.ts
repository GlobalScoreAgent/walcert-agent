import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { requireAgentSecret, jsonResponse, readJsonBody } from "./_shared/auth.ts";
import {
  getServiceClient,
  lookupLabels,
  mapChain,
  summarizeQualityHits,
} from "./_shared/labels.ts";
import { buildCertificate, parseRequestBody } from "./_shared/certificate.ts";
import { analyzeWashCircular } from "./_shared/wash.ts";
import { logCertificateRequest, parseAccessMeta } from "./_shared/logging.ts";
import {
  FORMULA_VERSION,
  assignGradeActivityV2,
  computeCexPercents,
  computeKindPercents,
  inputsHash,
  qualityFlagsFromHits,
  washScore,
} from "./_shared/activity_v2.ts";

const FUNCTION_SLUG = "walcert-certificate-activity";
const CERT_TYPE = "activity";

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

    const pairs = [
      ...counterparties.map((c) => ({
        address: String(c.address || "").toLowerCase(),
        chain_id: Number(c.chain_id) || null,
        chain: String(c.chain || "") || null,
      })),
      ...transfers.flatMap((t) => {
        const chain = String(t.chain || "") || null;
        const chain_id = Number(t.chain_id) || null;
        return [
          { address: String(t.from || "").toLowerCase(), chain_id, chain },
          { address: String(t.to || "").toLowerCase(), chain_id, chain },
        ];
      }),
    ].filter((p) => p.address.startsWith("0x"));

    const hits = await lookupLabels(client, addresses, chains, pairs);
    const summaryHits = summarizeQualityHits(hits);
    const qflags = qualityFlagsFromHits(hits);

    const wash = analyzeWashCircular(
      wallet,
      transfers.map((t) => ({
        ts: t.ts ? String(t.ts) : undefined,
        from: t.from ? String(t.from) : undefined,
        to: t.to ? String(t.to) : undefined,
        value: Number(t.value_usd ?? t.value) || 0,
        value_usd: t.value_usd != null ? Number(t.value_usd) : undefined,
        chain: t.chain ? String(t.chain) : undefined,
      })),
    );
    const wscore = washScore(wash);

    const { cex_pct_txs, cex_pct_value, priced_usd } = computeCexPercents({
      wallet,
      transfers,
      hits,
    });
    const cex_pct = priced_usd > 0 ? cex_pct_value : cex_pct_txs;
    const airdropKind = computeKindPercents({
      wallet,
      transfers,
      hits,
      kind: "airdrop",
    });
    const protocolKind = computeKindPercents({
      wallet,
      transfers,
      hits,
      kind: "protocol",
    });
    const airdrop_pct = priced_usd > 0 ? airdropKind.pct_value : airdropKind.pct_txs;
    const protocol_pct = priced_usd > 0 ? protocolKind.pct_value : protocolKind.pct_txs;

    const unique_counterparties = Number(
      payload.unique_counterparties ?? counterparties.length,
    );
    const counterparty_hhi = Number(payload.counterparty_hhi ?? 0);
    const bot_like_score = Number(
      payload.bot_like_score ??
        (payload.behavior_signals as Record<string, unknown> | undefined)
          ?.bot_like_score ??
        0,
    );
    const velocity = Number(payload.velocity_txs_per_day ?? 0);
    const sanctions_hit = summaryHits.ofac > 0;
    const mixer_hit = summaryHits.mixer > 0;

    const { grade, breakdown } = assignGradeActivityV2({
      unique_counterparties,
      cex_pct,
      counterparty_hhi,
      wash,
      wash_score: wscore,
      bot_like_score,
      velocity_txs_per_day: velocity,
      sanctions_hit,
      mixer_hit,
      airdrop_pct,
      kleros_risk_hit: qflags.kleros_risk_hit,
    });

    const strengths: { eng: string; esp: string }[] = [];
    const concerns: { eng: string; esp: string }[] = [];
    if (!wash.circular_patterns) {
      strengths.push({
        eng: "No evident circular patterns",
        esp: "Sin patrones circulares evidentes",
      });
    }
    if (unique_counterparties >= 10 && counterparty_hhi <= 0.35) {
      strengths.push({
        eng: "Acceptable counterparty diversity",
        esp: "Diversidad de contrapartes aceptable",
      });
    }
    if (wash.wash_trading_risk === "low") {
      strengths.push({ eng: "Low wash trading risk", esp: "Bajo riesgo de wash trading" });
    }
    if (protocol_pct >= 15 && wash.wash_trading_risk === "low") {
      strengths.push({
        eng: "Meaningful protocol counterparty share",
        esp: "Participación relevante de contrapartes protocolo",
      });
    }
    if (qflags.sourcify_verified_counterparty_pct >= 30) {
      strengths.push({
        eng: `Sourcify-verified counterparties among labeled (~${qflags.sourcify_verified_counterparty_pct}%)`,
        esp: `Contrapartes verificadas en Sourcify entre labeled (~${qflags.sourcify_verified_counterparty_pct}%)`,
      });
    }
    if (cex_pct >= 20) {
      concerns.push({
        eng: "CEX interaction still significant",
        esp: "Interacción con CEX todavía relevante",
      });
    }
    if (airdrop_pct >= 40) {
      concerns.push({
        eng: `High airdrop / reward counterparty share (~${airdrop_pct}%)`,
        esp: `Alta participación de contrapartes airdrop/reward (~${airdrop_pct}%)`,
      });
    }
    if (qflags.kleros_risk_hit) {
      concerns.push({
        eng: "Kleros Scout risk tags on counterparties",
        esp: "Tags de riesgo Kleros Scout en contrapartes",
      });
    }
    if (wash.circular_patterns) {
      concerns.push({ eng: "Circular patterns detected", esp: "Patrones circulares detectados" });
    }
    if (wash.wash_trading_risk !== "low") {
      concerns.push({ eng: "Wash trading signals", esp: "Señales de wash trading" });
    }
    if (sanctions_hit) {
      concerns.push({
        eng: "Interaction with OFAC-sanctioned address",
        esp: "Interacción con dirección sancionada (OFAC)",
      });
    }
    if (mixer_hit) {
      concerns.push({ eng: "Mixer interaction", esp: "Interacción con mixer" });
    }
    if (bot_like_score >= 0.55) {
      concerns.push({ eng: "Bot-like activity pattern", esp: "Patrón de actividad tipo bot" });
    }
    if (counterparty_hhi > 0.45) {
      concerns.push({
        eng: `High volume concentration across counterparties (HHI ${counterparty_hhi})`,
        esp: `Alta concentración de volumen entre contrapartes (HHI ${counterparty_hhi})`,
      });
    }

    const windowDays = payload.window_days || 15;
    const concentrationNote =
      counterparty_hhi > 0.45
        ? ` Volume is highly concentrated (HHI ${counterparty_hhi}) despite ${unique_counterparties} counterparties.`
        : "";
    const summary = {
      eng:
        `Recent activity (${windowDays}d) shows ${unique_counterparties} counterparties with ${wash.wash_trading_risk} wash risk.${concentrationNote} (${FORMULA_VERSION})`,
      esp:
        `La actividad reciente (${windowDays}d) muestra ${unique_counterparties} contrapartes con riesgo de wash ${wash.wash_trading_risk}.${
          counterparty_hhi > 0.45
            ? ` El volumen está muy concentrado (HHI ${counterparty_hhi}) pese a ${unique_counterparties} contrapartes.`
            : ""
        } (${FORMULA_VERSION})`,
    };

    const hash = await inputsHash({
      wallet,
      window_days: payload.window_days,
      total_transfers: payload.total_transfers,
      unique_counterparties,
      hhi: counterparty_hhi,
      cex_pct_value,
      cex_pct_txs,
      formula: FORMULA_VERSION,
    });

    const cert = await buildCertificate({
      type: "ACTIVITY",
      wallet,
      analyzed_at,
      grade,
      summary,
      version: "2.0",
      formula_version: FORMULA_VERSION,
      grade_breakdown: breakdown,
      inputs_hash: hash,
      details: {
        window_days: Number(payload.window_days) || 15,
        unique_counterparties,
        counterparty_hhi,
        cex_interaction_percentage: cex_pct,
        cex_interaction_pct_value: cex_pct_value,
        cex_interaction_pct_txs: cex_pct_txs,
        reciprocity_ratio: payload.reciprocity_ratio ?? null,
        net_to_gross_ratio: payload.net_to_gross_ratio ?? null,
        velocity_txs_per_day: velocity,
        burstiness_score: payload.burstiness_score ?? null,
        token_diversity: payload.token_diversity ?? null,
        bot_like_score,
        wash_trading_risk: wash.wash_trading_risk,
        circular_patterns: wash.circular_patterns,
        wash_score: wscore,
        bidirectional_pair_share: wash.bidirectional_pair_share,
        nft_transfer_pct: payload.nft_transfer_pct ?? null,
        fungible_transfer_pct: payload.fungible_transfer_pct ?? null,
        nft_vs_fungible_ratio: payload.nft_vs_fungible_ratio ?? null,
        sanctions_hit,
        mixer_hit,
        airdrop_percentage: airdrop_pct,
        protocol_percentage: protocol_pct,
        kleros_risk_hit: qflags.kleros_risk_hit,
        sourcify_verified_counterparty_pct: qflags.sourcify_verified_counterparty_pct,
        formula_version: FORMULA_VERSION,
        priced_transfers: payload.priced_transfers ?? null,
        unpriced_transfers: payload.unpriced_transfers ?? null,
        label_hits: summaryHits,
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
    console.error("activity scoring error", e);
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
