/**
 * Origins v2 — 9 signals + grade_breakdown (ORIGO-compatible rules, entity thresholds).
 * Uses priced `analysis.inflows` from the agent (DefiLlama). Does not re-price.
 */

import type { Grade } from "./certificate.ts";
import type { LabelHit } from "./labels.ts";
import { daysSince, sha256Hex } from "./certificate.ts";

export const FORMULA_VERSION = "origins-v2.3";

const AIRDROP_RE = /FAUCET|AIRDROP|REWARD|POINT/i;

const CEX_HIGH_QUALITY = /coinbase|kraken|gemini|bitstamp|revolut|okx/i;
const CEX_HIGH_RISK = /ftx|bitfinex|hotbit|changenow|fixedfloat|simpleswap/i;

const VALUE_RELEVANT_CATS = new Set(["external", "erc20"]);

/** Tie-break when two categories share the same %. */
const MAIN_ORIGIN_TIE_ORDER = [
  "cex",
  "bridge",
  "mixer",
  "organic",
  "protocol",
  "dex",
  "ofac",
  "airdrop",
  "synthetic",
  "unknown",
  "other",
];

export function mainOriginFromPercentages(
  category_percentages: Record<string, number>,
): string {
  let best = "other";
  let bestVal = -1;
  let bestRank = 999;
  for (const [k, raw] of Object.entries(category_percentages)) {
    const v = Number(raw) || 0;
    if (v <= 0) continue;
    const idx = MAIN_ORIGIN_TIE_ORDER.indexOf(k);
    const rank = idx < 0 ? 100 : idx;
    if (v > bestVal || (v === bestVal && rank < bestRank)) {
      bestVal = v;
      best = k;
      bestRank = rank;
    }
  }
  return bestVal > 0 ? best : "other";
}

export type Inflow = {
  from?: string;
  usd?: number | null;
  usd_method?: string;
  amount?: number;
  ts?: string | null;
  asset_category?: string;
  symbol?: string | null;
  contract?: string | null;
  chain_id?: number;
};

/** Native / ERC-20 with amount > 0 (excludes NFT and zero-amount). */
export function isValueRelevantInflow(row: Inflow): boolean {
  const cat = String(row.asset_category || "external").toLowerCase();
  const amount = Number(row.amount);
  return VALUE_RELEVANT_CATS.has(cat) && Number.isFinite(amount) && amount > 0;
}

export type GradeBreakdown = {
  formula_version: string;
  subject_type: "entity";
  applied_rule: string;
  grade: Grade;
  inputs: Record<string, unknown>;
  rules_evaluated: Array<{
    rule: string;
    passed: boolean;
    conditions: Array<{ name: string; passed: boolean; detail?: string }>;
  }>;
};

function usdOf(row: Inflow): number {
  const v = row.usd;
  if (v == null) return 0;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function computeOriginsSignals(params: {
  inflows: Inflow[];
  hits: Map<string, LabelHit>;
  analyzed_at?: string;
}): {
  signals: Record<string, unknown>;
  unique_senders: number;
  first_funding_age_days: number | null;
  first_funding: Record<string, unknown> | null;
  mixing_risk: "low" | "medium" | "high";
  sanctions_hit: boolean;
  cex_pct: number;
  bridge_pct: number;
  airdrop_pct: number;
  protocol_pct: number;
  kleros_risk_hit: boolean;
  sourcify_verified_sender_pct: number;
  main_origin_type: string;
  hhi: number;
  top1_pct: number;
  value_relevant_inflows: number;
  value_relevant_priced: number;
  value_relevant_unpriced: number;
  priced_coverage_pct: number;
  hhi_value_relevant_priced: number;
} {
  const { inflows, hits } = params;
  const bySenderUsd = new Map<string, number>();
  const bySenderUsdVr = new Map<string, number>();
  const categoryUsd: Record<string, number> = {
    cex: 0,
    bridge: 0,
    mixer: 0,
    ofac: 0,
    airdrop: 0,
    protocol: 0,
    synthetic: 0,
    organic: 0,
    unknown: 0,
    dex: 0,
  };
  let mixerHits = 0;
  let ofacHits = 0;
  let klerosRiskHits = 0;
  let klerosHits = 0;
  let sourcifySenders = 0;
  let value_relevant_inflows = 0;
  let value_relevant_priced = 0;
  const organicCounts = {
    labeled: 0,
    synthetic_nft: 0,
    synthetic_airdrop_reward: 0,
    organic_or_unknown: 0,
    unknown: 0,
  };
  const timestamps: number[] = [];
  let firstFunding: Record<string, unknown> | null = null;
  let earliest = Infinity;

  const senders = new Set<string>();

  for (const row of inflows) {
    const frm = String(row.from || "").toLowerCase();
    if (!frm) continue;
    senders.add(frm);
    const usd = usdOf(row);
    bySenderUsd.set(frm, (bySenderUsd.get(frm) || 0) + usd);

    const valueRelevant = isValueRelevantInflow(row);
    if (valueRelevant) {
      value_relevant_inflows++;
      if (usd > 0) {
        value_relevant_priced++;
        bySenderUsdVr.set(frm, (bySenderUsdVr.get(frm) || 0) + usd);
      }
    }

    const hit = hits.get(frm);
    const cat = String(row.asset_category || "external").toLowerCase();
    const symbol = String(row.symbol || "");

    if (hit?.kind === "mixer") mixerHits++;
    if (hit?.kind === "ofac") ofacHits++;
    if (hit?.kleros_risk) klerosRiskHits++;
    if (hit?.kleros_hit) klerosHits++;
    if (hit?.sourcify_verified) sourcifySenders++;

    if (hit) {
      organicCounts.labeled++;
      if (hit.kind === "cex") categoryUsd.cex += usd;
      else if (hit.kind === "bridge") categoryUsd.bridge += usd;
      else if (hit.kind === "mixer") categoryUsd.mixer += usd;
      else if (hit.kind === "ofac") categoryUsd.ofac += usd;
      else if (hit.kind === "airdrop") categoryUsd.airdrop += usd;
      else if (hit.kind === "protocol") categoryUsd.protocol += usd;
      else {
        organicCounts.organic_or_unknown++;
        categoryUsd.organic += usd;
      }
    } else if (cat === "erc721" || cat === "erc1155") {
      organicCounts.synthetic_nft++;
      categoryUsd.synthetic += usd;
    } else if (AIRDROP_RE.test(symbol)) {
      organicCounts.synthetic_airdrop_reward++;
      categoryUsd.airdrop += usd;
    } else if (cat === "external") {
      organicCounts.organic_or_unknown++;
      categoryUsd.organic += usd;
    } else {
      organicCounts.unknown++;
      categoryUsd.unknown += usd;
    }

    if (row.ts) {
      const t = Date.parse(row.ts);
      if (!Number.isNaN(t)) {
        timestamps.push(t);
        if (t < earliest) {
          earliest = t;
          firstFunding = {
            timestamp: new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z"),
            from: frm,
            value_usd_estimate: usd || null,
            kind: hit?.kind || "unknown",
            symbol: symbol || null,
            chain_id: row.chain_id ?? null,
          };
        }
      }
    }
  }

  const value_relevant_unpriced = Math.max(
    0,
    value_relevant_inflows - value_relevant_priced,
  );
  const priced_coverage_pct = value_relevant_inflows > 0
    ? Math.round((1000 * value_relevant_priced) / value_relevant_inflows) / 10
    : 0;

  const totalUsd = [...bySenderUsd.values()].reduce((a, b) => a + b, 0);
  const pct = (v: number) =>
    totalUsd > 0 ? Math.round((1000 * v) / totalUsd) / 10 : 0;

  const category_percentages: Record<string, number> = {};
  for (const [k, v] of Object.entries(categoryUsd)) {
    category_percentages[k] = pct(v);
  }

  // HHI over sender USD shares (all priced USD — grade)
  let hhi = 0;
  const shares: number[] = [];
  if (totalUsd > 0) {
    for (const u of bySenderUsd.values()) {
      const s = u / totalUsd;
      shares.push(s);
      hhi += s * s;
    }
  }
  shares.sort((a, b) => b - a);
  const top1 = shares[0] || 0;
  const top3 = (shares[0] || 0) + (shares[1] || 0) + (shares[2] || 0);

  // HHI over value-relevant priced only (details / audit)
  const totalUsdVr = [...bySenderUsdVr.values()].reduce((a, b) => a + b, 0);
  let hhiVr = 0;
  if (totalUsdVr > 0) {
    for (const u of bySenderUsdVr.values()) {
      const s = u / totalUsdVr;
      hhiVr += s * s;
    }
  }
  const hhi_value_relevant_priced = Math.round(hhiVr * 10000) / 10000;

  // CEX quality
  let cexQuality = {
    regulated_high_quality_usd: 0,
    high_risk_usd: 0,
    standard_usd: 0,
    unknown_usd: 0,
  };
  for (const [addr, u] of bySenderUsd) {
    const hit = hits.get(addr);
    if (hit?.kind !== "cex") continue;
    const name = hit.name || "";
    const institution = (hit.spellbook_categories || []).includes("institution");
    if (institution || CEX_HIGH_QUALITY.test(name)) {
      cexQuality.regulated_high_quality_usd += u;
    } else if (CEX_HIGH_RISK.test(name)) cexQuality.high_risk_usd += u;
    else if (name) cexQuality.standard_usd += u;
    else cexQuality.unknown_usd += u;
  }

  // Temporal
  timestamps.sort((a, b) => a - b);
  let temporal: Record<string, unknown> = {
    pattern: "insufficient_data",
    span_days: 0,
    median_gap_hours: null,
    burst_score: null,
  };
  if (timestamps.length >= 2) {
    const spanMs = timestamps[timestamps.length - 1] - timestamps[0];
    const spanDays = spanMs / 86_400_000;
    const gaps: number[] = [];
    for (let i = 1; i < timestamps.length; i++) {
      gaps.push((timestamps[i] - timestamps[i - 1]) / 3_600_000);
    }
    gaps.sort((a, b) => a - b);
    const mid = Math.floor(gaps.length / 2);
    const median =
      gaps.length % 2 ? gaps[mid] : (gaps[mid - 1] + gaps[mid]) / 2;
    const burstFrac = gaps.filter((g) => g < 24).length / gaps.length;
    let pattern = "mixed";
    if ((spanDays < 3 && timestamps.length >= 5) || (median < 12 && timestamps.length >= 8)) {
      pattern = "burst";
    } else if (spanDays >= 30 && median >= 24) {
      pattern = "gradual";
    }
    temporal = {
      pattern,
      span_days: Math.round(spanDays * 10) / 10,
      median_gap_hours: Math.round(median * 10) / 10,
      burst_score: Math.round(burstFrac * 1000) / 1000,
    };
  }

  const unique_senders = senders.size;
  let mixing_risk: "low" | "medium" | "high" = "low";
  if (mixerHits > 0 || ofacHits > 0) mixing_risk = "high";
  else if (unique_senders <= 1) mixing_risk = "medium";

  const sanctions_hit = ofacHits > 0;
  const age = firstFunding?.timestamp
    ? daysSince(String(firstFunding.timestamp))
    : null;

  const cex_pct = category_percentages.cex || 0;
  const bridge_pct = category_percentages.bridge || 0;
  const airdrop_pct = category_percentages.airdrop || 0;
  const protocol_pct = category_percentages.protocol || 0;
  const main_origin_type = mainOriginFromPercentages(category_percentages);
  const hhiRounded = Math.round(hhi * 10000) / 10000;
  const top1_pct = Math.round(top1 * 1000) / 10;
  const labeledSenders = [...senders].filter((a) => hits.has(a)).length;
  const sourcify_verified_sender_pct = labeledSenders > 0
    ? Math.round((1000 * sourcifySenders) / labeledSenders) / 10
    : 0;
  const kleros_risk_hit = klerosRiskHits > 0;
  const label_source_coverage_pct = unique_senders > 0
    ? Math.round((1000 * labeledSenders) / unique_senders) / 10
    : 0;

  return {
    signals: {
      category_percentages,
      unique_senders,
      hhi: hhiRounded,
      hhi_value_relevant_priced,
      concentration: {
        top1_pct,
        top3_pct: Math.round(top3 * 1000) / 10,
        top1_share: Math.round(top1 * 1000) / 1000,
        top3_share: Math.round(top3 * 1000) / 1000,
        basis: "priced_usd",
        hhi_value_relevant_priced,
        basis_value_relevant: "priced_usd_value_relevant",
      },
      pricing_coverage: {
        value_relevant_inflows,
        value_relevant_priced,
        value_relevant_unpriced,
        priced_coverage_pct,
      },
      cex_quality: cexQuality,
      temporal_funding: temporal,
      direct_exposure: {
        mixer_hits: mixerHits,
        ofac_hits: ofacHits,
        sanctions_hit,
        mixing_risk,
        kleros_hits: klerosHits,
        kleros_risk_hits: klerosRiskHits,
        kleros_risk_hit,
      },
      quality_enrichment: {
        sourcify_verified_sender_pct,
        label_source_coverage_pct,
        airdrop_pct,
        protocol_pct,
      },
      organic_vs_synthetic: organicCounts,
      first_funding_age_days: age,
    },
    unique_senders,
    first_funding_age_days: age,
    first_funding: firstFunding,
    mixing_risk,
    sanctions_hit,
    cex_pct,
    bridge_pct,
    airdrop_pct,
    protocol_pct,
    kleros_risk_hit,
    sourcify_verified_sender_pct,
    main_origin_type,
    hhi: hhiRounded,
    top1_pct,
    value_relevant_inflows,
    value_relevant_priced,
    value_relevant_unpriced,
    priced_coverage_pct,
    hhi_value_relevant_priced,
  };
}

export function assignGradeOriginsV2(input: {
  cex_pct: number;
  unique_senders: number;
  mixing_risk: "low" | "medium" | "high";
  first_funding_age_days: number | null;
  sanctions_hit: boolean;
  ofac_hits?: number;
  hhi?: number;
  top1_pct?: number;
  airdrop_pct?: number;
  kleros_risk_hit?: boolean;
}): { grade: Grade; breakdown: GradeBreakdown } {
  const age = input.first_funding_age_days ?? 0;
  const unique = input.unique_senders;
  const hhi = Number(input.hhi) || 0;
  const top1_pct = Number(input.top1_pct) || 0;
  const airdrop_pct = Number(input.airdrop_pct) || 0;
  const kleros_risk_hit = Boolean(input.kleros_risk_hit);
  // entity thresholds
  const aUnique = 10;
  const bUnique = 5;

  const inputs = {
    cex_pct: input.cex_pct,
    unique_senders: unique,
    mixing_risk: input.mixing_risk,
    first_funding_age_days: age,
    sanctions_hit: input.sanctions_hit,
    hhi,
    top1_pct,
    airdrop_pct,
    kleros_risk_hit,
    subject_type: "entity",
    thresholds: { a_unique: aUnique, b_unique: bUnique },
  };

  const rules_evaluated: GradeBreakdown["rules_evaluated"] = [];

  const ruleF = {
    rule: "F",
    passed: input.sanctions_hit || input.mixing_risk === "high",
    conditions: [
      {
        name: "sanctions_or_high_mixing",
        passed: input.sanctions_hit || input.mixing_risk === "high",
        detail: `sanctions=${input.sanctions_hit} mixing=${input.mixing_risk}`,
      },
    ],
  };
  rules_evaluated.push(ruleF);

  const ruleA = {
    rule: "A",
    passed:
      input.cex_pct <= 40 &&
      unique >= aUnique &&
      input.mixing_risk === "low" &&
      age >= 365 &&
      top1_pct <= 60 &&
      hhi <= 0.55 &&
      airdrop_pct <= 40 &&
      !kleros_risk_hit,
    conditions: [
      { name: "cex_pct_le_40", passed: input.cex_pct <= 40, detail: String(input.cex_pct) },
      { name: "unique_ge_10", passed: unique >= aUnique, detail: String(unique) },
      { name: "mixing_low", passed: input.mixing_risk === "low" },
      { name: "age_ge_365", passed: age >= 365, detail: String(age) },
      { name: "top1_pct_le_60", passed: top1_pct <= 60, detail: String(top1_pct) },
      { name: "hhi_le_0_55", passed: hhi <= 0.55, detail: String(hhi) },
      { name: "airdrop_pct_le_40", passed: airdrop_pct <= 40, detail: String(airdrop_pct) },
      { name: "no_kleros_risk", passed: !kleros_risk_hit },
    ],
  };
  rules_evaluated.push(ruleA);

  const ruleB = {
    rule: "B",
    passed:
      input.cex_pct <= 70 &&
      unique >= bUnique &&
      input.mixing_risk === "low" &&
      top1_pct <= 80 &&
      hhi <= 0.70 &&
      airdrop_pct <= 70,
    conditions: [
      { name: "cex_pct_le_70", passed: input.cex_pct <= 70, detail: String(input.cex_pct) },
      { name: "unique_ge_5", passed: unique >= bUnique, detail: String(unique) },
      { name: "mixing_low", passed: input.mixing_risk === "low" },
      { name: "top1_pct_le_80", passed: top1_pct <= 80, detail: String(top1_pct) },
      { name: "hhi_le_0_70", passed: hhi <= 0.70, detail: String(hhi) },
      { name: "airdrop_pct_le_70", passed: airdrop_pct <= 70, detail: String(airdrop_pct) },
    ],
  };
  rules_evaluated.push(ruleB);

  const ruleD = {
    rule: "D",
    passed:
      input.mixing_risk === "medium" ||
      (input.cex_pct > 85 && unique <= 2) ||
      top1_pct >= 95 ||
      hhi >= 0.90 ||
      (airdrop_pct >= 80 && unique <= 3),
    conditions: [
      { name: "mixing_medium", passed: input.mixing_risk === "medium" },
      {
        name: "cex_gt_85_and_unique_le_2",
        passed: input.cex_pct > 85 && unique <= 2,
        detail: `cex=${input.cex_pct} unique=${unique}`,
      },
      {
        name: "top1_pct_ge_95",
        passed: top1_pct >= 95,
        detail: String(top1_pct),
      },
      { name: "hhi_ge_0_90", passed: hhi >= 0.90, detail: String(hhi) },
      {
        name: "airdrop_dominated",
        passed: airdrop_pct >= 80 && unique <= 3,
        detail: `airdrop=${airdrop_pct} unique=${unique}`,
      },
    ],
  };
  rules_evaluated.push(ruleD);

  let grade: Grade = "C";
  let applied = "C";
  for (const r of [ruleF, ruleA, ruleB, ruleD]) {
    if (r.passed) {
      grade = r.rule as Grade;
      applied = r.rule;
      break;
    }
  }
  rules_evaluated.push({
    rule: "C",
    passed: applied === "C",
    conditions: [{ name: "default", passed: applied === "C" }],
  });

  return {
    grade,
    breakdown: {
      formula_version: FORMULA_VERSION,
      subject_type: "entity",
      applied_rule: applied,
      grade,
      inputs,
      rules_evaluated,
    },
  };
}

export async function inputsHash(parts: unknown): Promise<string> {
  return sha256Hex(JSON.stringify(parts));
}
