/**
 * Multichain v2 — GoldRush footprint + intensity grade (canonical from chains[]).
 */

import type { Grade } from "./certificate.ts";
import { sha256Hex } from "./certificate.ts";
import {
  CORE_ECOSYSTEM_LIST_VERSION,
  normalizeCoreSlug,
} from "./core_ecosystems.ts";
import { ecosystemFamilyFromChainName } from "./chain_families.ts";

export const FORMULA_VERSION = "multichain-v2.1";

const DORMANT_DAYS = 180;
const CONSISTENCY_SPAN_DAYS = 90;

const KNOWN_L2 = new Set([
  "base-mainnet",
  "arbitrum-mainnet",
  "optimism-mainnet",
  "matic-mainnet",
  "polygon-mainnet",
  "zora-mainnet",
  "scroll-mainnet",
  "linea-mainnet",
]);

export type ChainRow = {
  name?: string;
  chain?: string;
  chain_id?: number | null;
  label?: string;
  category_label?: string;
  category?: string;
  is_testnet?: boolean;
  is_appchain?: boolean;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  first_transaction?: string | null;
  last_transaction?: string | null;
  span_days?: number;
  tx_count?: number;
  transfer_count?: number;
  gas_spent_quote?: number | null;
  intensity_sampled?: boolean;
};

export type MultichainV2Metrics = {
  core_ecosystem_list_version: string;
  total_chains_mainnet: number;
  total_chains_testnet: number;
  ecosystem_count: number;
  l2_or_appchain_count: number;
  activity_span_days: number;
  active_chains_30d: number;
  active_chains_90d: number;
  dormant_ratio: number;
  consistency_score: number;
  recency_score: number;
  footprint_concentration: number;
  core_ecosystems: string[];
  core_ecosystem_count: number;
  intensity: {
    chains_sampled: number;
    sampled_chains: string[];
    total_tx_count: number;
    tx_hhi: number;
    primary_chain: string | null;
    weighted_activity_score: number;
    gas_footprint_quote: number | null;
  };
  chains: Array<Record<string, unknown>>;
};

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

function parseTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

function daysBetween(aMs: number | null, bMs: number | null): number {
  if (aMs == null || bMs == null) return 0;
  return Math.max(0, Math.floor((bMs - aMs) / 86_400_000));
}

export function computeMultichainV2Metrics(
  chainsIn: ChainRow[],
): MultichainV2Metrics {
  const now = Date.now();
  const mainnets = chainsIn.filter((c) => !c.is_testnet);
  const testnets = chainsIn.filter((c) => c.is_testnet);
  const enriched: Array<Record<string, unknown>> = [];
  let firstAll: number | null = null;
  let lastAll: number | null = null;
  const categories = new Set<string>();
  const coreSet: string[] = [];
  const coreSeen = new Set<string>();
  let l2Count = 0;

  for (const raw of mainnets) {
    const name = String(raw.name || raw.chain || "").toLowerCase();
    let first = parseTs(
      (raw.first_seen_at || raw.first_transaction || undefined) ?? undefined,
    );
    let last = parseTs(
      (raw.last_seen_at || raw.last_transaction || undefined) ?? undefined,
    );
    if (first != null && last == null) last = first;
    if (last != null && first == null) first = last;
    const span = daysBetween(first, last);
    const sinceLast = last != null
      ? Math.max(0, Math.floor((now - last) / 86_400_000))
      : null;
    const is_recent_30d = sinceLast != null && sinceLast <= 30;
    const is_recent_90d = sinceLast != null && sinceLast <= 90;
    const is_dormant = sinceLast != null && sinceLast > DORMANT_DAYS;
    if (first != null && (firstAll == null || first < firstAll)) firstAll = first;
    if (last != null && (lastAll == null || last > lastAll)) lastAll = last;
    const family = ecosystemFamilyFromChainName(name);
    if (family) categories.add(family);
    const isApp = Boolean(raw.is_appchain) || KNOWN_L2.has(name);
    if (isApp) l2Count++;
    const slug = normalizeCoreSlug(name);
    if (slug && !coreSeen.has(slug)) {
      coreSeen.add(slug);
      coreSet.push(slug);
    }
    enriched.push({
      name,
      chain_id: raw.chain_id ?? null,
      label: raw.label || name,
      category_label: raw.category_label || raw.category || null,
      ecosystem_family: family,
      is_testnet: false,
      is_appchain: Boolean(raw.is_appchain),
      is_l2_or_appchain: isApp,
      first_seen_at: raw.first_seen_at || raw.first_transaction || null,
      last_seen_at: raw.last_seen_at || raw.last_transaction || null,
      span_days: span,
      is_recent_30d,
      is_recent_90d,
      is_dormant,
      tx_count: Number(raw.tx_count) || 0,
      transfer_count: Number(raw.transfer_count) || 0,
      gas_spent_quote: raw.gas_spent_quote ?? null,
      intensity_sampled: Boolean(raw.intensity_sampled),
    });
  }
  coreSet.sort();

  const n = enriched.length;
  const span_days = daysBetween(firstAll, lastAll);
  const active_30 = enriched.filter((r) => r.is_recent_30d).length;
  const active_90 = enriched.filter((r) => r.is_recent_90d).length;
  const dormant_n = enriched.filter((r) => r.is_dormant).length;
  const dormant_ratio = n ? Math.round((dormant_n / n) * 10000) / 10000 : 0;
  const consistent_n = enriched.filter(
    (r) => Number(r.span_days || 0) > CONSISTENCY_SPAN_DAYS,
  ).length;
  const consistency_score = n
    ? Math.round((consistent_n / n) * 10000) / 10000
    : 0;
  let recencySum = 0;
  for (const r of enriched) {
    if (r.is_recent_30d) recencySum += 1;
    else if (r.is_recent_90d) recencySum += 0.5;
  }
  const recency_score = n ? Math.round((recencySum / n) * 10000) / 10000 : 0;

  const spans = enriched.map((r) => Math.max(0, Number(r.span_days || 0)));
  const totalSpan = spans.reduce((a, b) => a + b, 0);
  let hhi = 0;
  if (totalSpan > 0) {
    for (const s of spans) {
      const share = s / totalSpan;
      hhi += share * share;
    }
  } else if (n > 0) {
    const share = 1 / n;
    hhi = n * share * share;
  }

  const sampled = enriched.filter((r) => r.intensity_sampled);
  const txCounts = sampled.map((r) => Math.max(0, Number(r.tx_count || 0)));
  const total_tx = txCounts.reduce((a, b) => a + b, 0);
  let tx_hhi = 0;
  if (total_tx > 0) {
    for (const t of txCounts) {
      const share = t / total_tx;
      tx_hhi += share * share;
    }
  } else if (sampled.length > 0) {
    const share = 1 / sampled.length;
    tx_hhi = sampled.length * share * share;
  }

  let weighted = 0;
  if (sampled.length > 0) {
    const maxTx = Math.max(...txCounts, 0);
    for (const r of sampled) {
      const tx = Number(r.tx_count || 0);
      const wTx = maxTx > 0 ? tx / maxTx : 0;
      const wRec = r.is_recent_30d ? 1 : r.is_recent_90d ? 0.5 : 0.15;
      weighted += wTx * wRec;
    }
    weighted = Math.round((weighted / sampled.length) * 10000) / 10000;
  }

  let primary: Record<string, unknown> | null = null;
  if (sampled.length) {
    primary = sampled.reduce((best, cur) => {
      const bt = Number(best.tx_count || 0);
      const ct = Number(cur.tx_count || 0);
      if (ct > bt) return cur;
      if (ct === bt && Number(cur.span_days || 0) > Number(best.span_days || 0)) {
        return cur;
      }
      return best;
    });
  }

  let gasTotal = 0;
  let gasAny = false;
  for (const r of sampled) {
    if (r.gas_spent_quote != null && Number.isFinite(Number(r.gas_spent_quote))) {
      gasTotal += Number(r.gas_spent_quote);
      gasAny = true;
    }
  }

  return {
    core_ecosystem_list_version: CORE_ECOSYSTEM_LIST_VERSION,
    total_chains_mainnet: n,
    total_chains_testnet: testnets.length,
    ecosystem_count: categories.size,
    l2_or_appchain_count: l2Count,
    activity_span_days: span_days,
    active_chains_30d: active_30,
    active_chains_90d: active_90,
    dormant_ratio,
    consistency_score,
    recency_score,
    footprint_concentration: Math.round(hhi * 10000) / 10000,
    core_ecosystems: coreSet,
    core_ecosystem_count: coreSet.length,
    intensity: {
      chains_sampled: sampled.length,
      sampled_chains: sampled.map((r) => String(r.name || "")),
      total_tx_count: total_tx,
      tx_hhi: Math.round(tx_hhi * 10000) / 10000,
      primary_chain: primary ? String(primary.name || "") : null,
      weighted_activity_score: weighted,
      gas_footprint_quote: gasAny ? Math.round(gasTotal * 10000) / 10000 : null,
    },
    chains: enriched,
  };
}

export function assignGradeMultichainV2(
  m: MultichainV2Metrics,
): { grade: Grade; breakdown: GradeBreakdown } {
  const mainnets = m.total_chains_mainnet;
  const ecosystems = m.ecosystem_count;
  const span = m.activity_span_days;
  const cons = m.consistency_score;
  const rec = m.recency_score;
  const core = m.core_ecosystem_count;
  const a30 = m.active_chains_30d;
  const dorm = m.dormant_ratio;
  const totalTx = m.intensity.total_tx_count;
  const txHhi = m.intensity.tx_hhi;
  const onlyTestnets = mainnets === 0 && m.total_chains_testnet > 0;

  const inputs = {
    total_chains_mainnet: mainnets,
    ecosystem_count: ecosystems,
    activity_span_days: span,
    consistency_score: cons,
    recency_score: rec,
    core_ecosystem_count: core,
    active_chains_30d: a30,
    dormant_ratio: dorm,
    total_tx_count: totalTx,
    tx_hhi: txHhi,
    subject_type: "entity",
  };

  const rules_evaluated: GradeBreakdown["rules_evaluated"] = [];

  const ruleF = {
    rule: "F",
    passed:
      mainnets === 0 ||
      onlyTestnets ||
      (mainnets === 1 && span < 30 && totalTx < 5),
    conditions: [
      { name: "mainnets_eq_0", passed: mainnets === 0, detail: String(mainnets) },
      { name: "only_testnets", passed: onlyTestnets },
      {
        name: "single_shallow",
        passed: mainnets === 1 && span < 30 && totalTx < 5,
        detail: `span=${span} tx=${totalTx}`,
      },
    ],
  };
  rules_evaluated.push(ruleF);

  const ruleD = {
    rule: "D",
    passed:
      mainnets === 1 ||
      (dorm > 0.75 && a30 === 0) ||
      totalTx === 0,
    conditions: [
      { name: "mainnets_eq_1", passed: mainnets === 1, detail: String(mainnets) },
      {
        name: "mostly_dormant",
        passed: dorm > 0.75 && a30 === 0,
        detail: `dorm=${dorm} a30=${a30}`,
      },
      { name: "total_tx_eq_0", passed: totalTx === 0, detail: String(totalTx) },
    ],
  };
  rules_evaluated.push(ruleD);

  const ruleA = {
    rule: "A",
    passed:
      mainnets >= 5 &&
      ecosystems >= 3 &&
      span >= 365 &&
      cons >= 0.5 &&
      rec >= 0.35 &&
      core >= 2 &&
      totalTx >= 50 &&
      txHhi <= 0.7,
    conditions: [
      { name: "mainnets_ge_5", passed: mainnets >= 5, detail: String(mainnets) },
      { name: "ecosystems_ge_3", passed: ecosystems >= 3, detail: String(ecosystems) },
      { name: "span_ge_365", passed: span >= 365, detail: String(span) },
      { name: "cons_ge_0_50", passed: cons >= 0.5, detail: String(cons) },
      { name: "rec_ge_0_35", passed: rec >= 0.35, detail: String(rec) },
      { name: "core_ge_2", passed: core >= 2, detail: String(core) },
      { name: "tx_ge_50", passed: totalTx >= 50, detail: String(totalTx) },
      { name: "tx_hhi_le_0_70", passed: txHhi <= 0.7, detail: String(txHhi) },
    ],
  };
  rules_evaluated.push(ruleA);

  const ruleB = {
    rule: "B",
    passed:
      mainnets >= 3 &&
      ecosystems >= 2 &&
      span >= 180 &&
      cons >= 0.4 &&
      totalTx >= 15,
    conditions: [
      { name: "mainnets_ge_3", passed: mainnets >= 3, detail: String(mainnets) },
      { name: "ecosystems_ge_2", passed: ecosystems >= 2, detail: String(ecosystems) },
      { name: "span_ge_180", passed: span >= 180, detail: String(span) },
      { name: "cons_ge_0_40", passed: cons >= 0.4, detail: String(cons) },
      { name: "tx_ge_15", passed: totalTx >= 15, detail: String(totalTx) },
    ],
  };
  rules_evaluated.push(ruleB);

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
