import type { Grade } from "./certificate.ts";
import type { LabelHit } from "./labels.ts";
import { daysSince } from "./certificate.ts";
import type { WashResult } from "./wash.ts";

export function gradeOrigins(input: {
  cex_pct: number;
  bridge_pct: number;
  unique_senders: number;
  mixing_risk: "low" | "medium" | "high";
  first_funding_age_days: number | null;
  sanctions_hit: boolean;
}): Grade {
  if (input.sanctions_hit || input.mixing_risk === "high") return "F";
  const age = input.first_funding_age_days ?? 0;
  const diversity = input.unique_senders;
  if (input.cex_pct <= 40 && diversity >= 10 && input.mixing_risk === "low" && age >= 365) {
    return "A";
  }
  if (input.cex_pct <= 70 && diversity >= 5 && input.mixing_risk === "low") return "B";
  if (input.mixing_risk === "medium" || (input.cex_pct > 85 && diversity <= 2)) return "D";
  if (input.cex_pct > 90 && diversity <= 1 && age < 30) return "D";
  return "C";
}

export function gradeActivity(input: {
  unique_counterparties: number;
  cex_pct: number;
  wash: WashResult;
  sanctions_hit: boolean;
  mixer_hit: boolean;
}): Grade {
  if (input.sanctions_hit || input.wash.wash_trading_risk === "high") return "F";
  if (input.wash.circular_patterns && input.wash.wash_trading_risk === "medium") return "D";
  if (input.mixer_hit) return "D";
  const u = input.unique_counterparties;
  if (u >= 25 && input.wash.wash_trading_risk === "low" && !input.wash.circular_patterns) {
    return "A";
  }
  if (u >= 12 && input.wash.wash_trading_risk === "low") return "B";
  if (u < 3 || input.cex_pct > 60) return "D";
  return "C";
}

export function gradeMultichain(input: {
  chain_count: number;
  activity_span_days: number;
}): Grade {
  const n = input.chain_count;
  const span = input.activity_span_days;
  if (n >= 4 && span >= 365) return "A";
  if (n >= 3 && span >= 180) return "B";
  if (n >= 2) return "C";
  if (n === 1 && span >= 30) return "D";
  return "F";
}

export function summarizeLabels(hits: Map<string, LabelHit>) {
  let ofac = 0, mixer = 0, cex = 0, bridge = 0;
  for (const h of hits.values()) {
    if (h.kind === "ofac") ofac++;
    else if (h.kind === "mixer") mixer++;
    else if (h.kind === "cex") cex++;
    else if (h.kind === "bridge") bridge++;
  }
  return { ofac, mixer, cex, bridge };
}

export { daysSince };
