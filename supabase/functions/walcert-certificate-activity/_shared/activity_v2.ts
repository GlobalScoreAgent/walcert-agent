/**
 * Activity v2 — signals + grade_breakdown.
 * Uses agent-priced transfers (value_usd). Labels from Edge RPC.
 */

import type { Grade } from "./certificate.ts";
import type { LabelHit } from "./labels.ts";
import type { WashResult } from "./wash.ts";
import { sha256Hex } from "./certificate.ts";

export const FORMULA_VERSION = "activity-v2.2";

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

export function washScore(wash: WashResult): number {
  let s = 0;
  if (wash.wash_trading_risk === "high") s = 0.85;
  else if (wash.wash_trading_risk === "medium") s = 0.45;
  else s = 0.1;
  if (wash.circular_patterns) s = Math.min(1, s + 0.15);
  s = Math.max(s, Math.min(1, wash.bidirectional_pair_share));
  if (wash.ping_pong_pairs >= 3) s = Math.max(s, 0.8);
  return Math.round(s * 1000) / 1000;
}

export function computeCexPercents(params: {
  wallet: string;
  transfers: Array<Record<string, unknown>>;
  hits: Map<string, LabelHit>;
}): { cex_pct_txs: number; cex_pct_value: number; priced_usd: number } {
  const w = params.wallet.toLowerCase();
  let cexTx = 0;
  let totalTx = 0;
  let cexUsd = 0;
  let totalUsd = 0;
  for (const t of params.transfers) {
    const f = String(t.from || "").toLowerCase();
    const to = String(t.to || "").toLowerCase();
    if (f !== w && to !== w) continue;
    totalTx++;
    const other = to === w ? f : to;
    const usdRaw = t.value_usd ?? t.value;
    const usd = Number(usdRaw);
    const priced = Number.isFinite(usd) && usd > 0 ? usd : 0;
    totalUsd += priced;
    if (other && params.hits.get(other)?.kind === "cex") {
      cexTx++;
      cexUsd += priced;
    }
  }
  const cex_pct_txs = totalTx > 0 ? Math.round((1000 * cexTx) / totalTx) / 10 : 0;
  const cex_pct_value = totalUsd > 0
    ? Math.round((1000 * cexUsd) / totalUsd) / 10
    : cex_pct_txs;
  return { cex_pct_txs, cex_pct_value, priced_usd: totalUsd };
}

export function computeKindPercents(params: {
  wallet: string;
  transfers: Array<Record<string, unknown>>;
  hits: Map<string, LabelHit>;
  kind: LabelHit["kind"];
}): { pct_txs: number; pct_value: number } {
  const w = params.wallet.toLowerCase();
  let kindTx = 0;
  let totalTx = 0;
  let kindUsd = 0;
  let totalUsd = 0;
  for (const t of params.transfers) {
    const f = String(t.from || "").toLowerCase();
    const to = String(t.to || "").toLowerCase();
    if (f !== w && to !== w) continue;
    totalTx++;
    const other = to === w ? f : to;
    const usdRaw = t.value_usd ?? t.value;
    const usd = Number(usdRaw);
    const priced = Number.isFinite(usd) && usd > 0 ? usd : 0;
    totalUsd += priced;
    if (other && params.hits.get(other)?.kind === params.kind) {
      kindTx++;
      kindUsd += priced;
    }
  }
  const pct_txs = totalTx > 0 ? Math.round((1000 * kindTx) / totalTx) / 10 : 0;
  const pct_value = totalUsd > 0
    ? Math.round((1000 * kindUsd) / totalUsd) / 10
    : pct_txs;
  return { pct_txs, pct_value };
}

export function qualityFlagsFromHits(hits: Map<string, LabelHit>): {
  kleros_risk_hit: boolean;
  sourcify_verified_counterparty_pct: number;
} {
  let kleros_risk_hit = false;
  let labeled = 0;
  let sourcify = 0;
  for (const h of hits.values()) {
    labeled++;
    if (h.kleros_risk) kleros_risk_hit = true;
    if (h.sourcify_verified) sourcify++;
  }
  return {
    kleros_risk_hit,
    sourcify_verified_counterparty_pct: labeled > 0
      ? Math.round((1000 * sourcify) / labeled) / 10
      : 0,
  };
}

export function assignGradeActivityV2(input: {
  unique_counterparties: number;
  cex_pct: number;
  counterparty_hhi: number;
  wash: WashResult;
  wash_score: number;
  bot_like_score: number;
  velocity_txs_per_day: number;
  sanctions_hit: boolean;
  mixer_hit: boolean;
  airdrop_pct?: number;
  kleros_risk_hit?: boolean;
}): { grade: Grade; breakdown: GradeBreakdown } {
  const u = input.unique_counterparties;
  const hhi = input.counterparty_hhi;
  const bot = input.bot_like_score;
  const washRisk = input.wash.wash_trading_risk;
  const circular = input.wash.circular_patterns;
  const airdrop_pct = Number(input.airdrop_pct) || 0;
  const kleros_risk_hit = Boolean(input.kleros_risk_hit);

  const inputs = {
    unique_counterparties: u,
    cex_pct: input.cex_pct,
    counterparty_hhi: hhi,
    wash_trading_risk: washRisk,
    circular_patterns: circular,
    wash_score: input.wash_score,
    bot_like_score: bot,
    velocity_txs_per_day: input.velocity_txs_per_day,
    sanctions_hit: input.sanctions_hit,
    mixer_hit: input.mixer_hit,
    airdrop_pct,
    kleros_risk_hit,
    subject_type: "entity",
  };

  const rules_evaluated: GradeBreakdown["rules_evaluated"] = [];

  const ruleF = {
    rule: "F",
    passed:
      input.sanctions_hit ||
      washRisk === "high" ||
      bot >= 0.8 ||
      input.wash_score >= 0.75,
    conditions: [
      { name: "sanctions", passed: input.sanctions_hit },
      { name: "wash_high", passed: washRisk === "high", detail: washRisk },
      { name: "bot_ge_0_8", passed: bot >= 0.8, detail: String(bot) },
      {
        name: "wash_score_ge_0_75",
        passed: input.wash_score >= 0.75,
        detail: String(input.wash_score),
      },
    ],
  };
  rules_evaluated.push(ruleF);

  const ruleD = {
    rule: "D",
    passed:
      input.mixer_hit ||
      (circular && washRisk === "medium") ||
      u < 3 ||
      input.cex_pct > 60 ||
      hhi > 0.70 ||
      bot >= 0.55 ||
      airdrop_pct > 70,
    conditions: [
      { name: "mixer", passed: input.mixer_hit },
      {
        name: "circular_and_wash_medium",
        passed: circular && washRisk === "medium",
      },
      { name: "unique_lt_3", passed: u < 3, detail: String(u) },
      { name: "cex_gt_60", passed: input.cex_pct > 60, detail: String(input.cex_pct) },
      { name: "hhi_gt_0_70", passed: hhi > 0.70, detail: String(hhi) },
      { name: "bot_ge_0_55", passed: bot >= 0.55, detail: String(bot) },
      { name: "airdrop_gt_70", passed: airdrop_pct > 70, detail: String(airdrop_pct) },
    ],
  };
  rules_evaluated.push(ruleD);

  const ruleA = {
    rule: "A",
    passed:
      u >= 25 &&
      washRisk === "low" &&
      !circular &&
      hhi <= 0.25 &&
      bot < 0.35 &&
      input.velocity_txs_per_day <= 40 &&
      airdrop_pct <= 40 &&
      !kleros_risk_hit,
    conditions: [
      { name: "unique_ge_25", passed: u >= 25, detail: String(u) },
      { name: "wash_low", passed: washRisk === "low" },
      { name: "no_circular", passed: !circular },
      { name: "hhi_le_0_25", passed: hhi <= 0.25, detail: String(hhi) },
      { name: "bot_lt_0_35", passed: bot < 0.35, detail: String(bot) },
      {
        name: "velocity_le_40",
        passed: input.velocity_txs_per_day <= 40,
        detail: String(input.velocity_txs_per_day),
      },
      { name: "airdrop_pct_le_40", passed: airdrop_pct <= 40, detail: String(airdrop_pct) },
      { name: "no_kleros_risk", passed: !kleros_risk_hit },
    ],
  };
  rules_evaluated.push(ruleA);

  const ruleB = {
    rule: "B",
    passed:
      u >= 12 &&
      washRisk === "low" &&
      hhi <= 0.35 &&
      bot < 0.5 &&
      airdrop_pct <= 60,
    conditions: [
      { name: "unique_ge_12", passed: u >= 12, detail: String(u) },
      { name: "wash_low", passed: washRisk === "low" },
      { name: "hhi_le_0_35", passed: hhi <= 0.35, detail: String(hhi) },
      { name: "bot_lt_0_5", passed: bot < 0.5, detail: String(bot) },
      { name: "airdrop_pct_le_60", passed: airdrop_pct <= 60, detail: String(airdrop_pct) },
    ],
  };
  rules_evaluated.push(ruleB);

  // Order F → D → A → B → C (D before A so severe cases don't get A)
  let grade: Grade = "C";
  let applied = "C";
  for (const r of [ruleF, ruleD, ruleA, ruleB]) {
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
