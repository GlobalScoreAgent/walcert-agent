export type WashResult = {
  wash_trading_risk: "low" | "medium" | "high";
  circular_patterns: boolean;
  bidirectional_pair_share: number;
  ping_pong_pairs: number;
};

type CompactTransfer = {
  ts?: string;
  from?: string;
  to?: string;
  value?: number;
  value_usd?: number;
  chain?: string;
};

function parseTs(ts?: string): number {
  if (!ts) return 0;
  const n = Date.parse(ts);
  return Number.isNaN(n) ? 0 : n;
}

/** Detect ping-pong and circular patterns from compact transfers. */
export function analyzeWashCircular(
  wallet: string,
  transfers: CompactTransfer[],
): WashResult {
  const w = wallet.toLowerCase();
  const sorted = [...transfers].sort((a, b) => parseTs(a.ts) - parseTs(b.ts));

  // Prefer value_usd when present (Activity v2)
  const val = (t: CompactTransfer) => {
    const u = (t as { value_usd?: number }).value_usd;
    if (u != null && Number(u) > 0) return Math.abs(Number(u));
    return Math.abs(Number(t.value) || 0);
  };

  const pairVol = new Map<string, { in: number; out: number; count: number }>();
  let totalVol = 0;

  for (const t of sorted) {
    const from = (t.from || "").toLowerCase();
    const to = (t.to || "").toLowerCase();
    const value = val(t);
    totalVol += value;
    let other = "";
    let dir: "in" | "out" = "out";
    if (to === w) {
      other = from;
      dir = "in";
    } else if (from === w) {
      other = to;
      dir = "out";
    } else continue;
    if (!other) continue;
    const key = other;
    const cur = pairVol.get(key) || { in: 0, out: 0, count: 0 };
    if (dir === "in") cur.in += value;
    else cur.out += value;
    cur.count += 1;
    pairVol.set(key, cur);
  }

  let bidirectionalVol = 0;
  let pingPongPairs = 0;
  const WINDOW_MS = 6 * 60 * 60 * 1000; // 6h

  for (const [other, v] of pairVol) {
    if (v.in > 0 && v.out > 0) {
      bidirectionalVol += Math.min(v.in, v.out) * 2;
      const related = sorted.filter((t) => {
        const f = (t.from || "").toLowerCase();
        const to = (t.to || "").toLowerCase();
        return (f === w && to === other) || (f === other && to === w);
      });
      let hits = 0;
      for (let i = 0; i < related.length - 1; i++) {
        const a = related[i];
        const b = related[i + 1];
        const aFrom = (a.from || "").toLowerCase();
        const bFrom = (b.from || "").toLowerCase();
        const dt = Math.abs(parseTs(b.ts) - parseTs(a.ts));
        const reverse = aFrom !== bFrom;
        const va = val(a);
        const vb = val(b);
        const similar = va === 0 || vb === 0
          ? true
          : Math.abs(va - vb) / Math.max(va, vb) < 0.15;
        if (reverse && dt < WINDOW_MS && similar) hits++;
      }
      if (hits >= 2 || (v.count >= 4 && Math.min(v.in, v.out) / Math.max(v.in, v.out, 1e-9) > 0.5)) {
        pingPongPairs++;
      }
    }
  }

  const bidShare = totalVol > 0 ? bidirectionalVol / totalVol : 0;
  let circular = pingPongPairs > 0 || bidShare > 0.35;
  let risk: "low" | "medium" | "high" = "low";
  if (pingPongPairs >= 3 || bidShare > 0.55) risk = "high";
  else if (pingPongPairs >= 1 || bidShare > 0.25) risk = "medium";

  if (!circular && sorted.length >= 4) {
    const outs = sorted.filter((t) => (t.from || "").toLowerCase() === w);
    const ins = sorted.filter((t) => (t.to || "").toLowerCase() === w);
    for (const o of outs.slice(0, 40)) {
      const mid = (o.to || "").toLowerCase();
      const t0 = parseTs(o.ts);
      for (const i of ins) {
        const back = (i.from || "").toLowerCase();
        if (back === mid && parseTs(i.ts) > t0 && parseTs(i.ts) - t0 < WINDOW_MS) {
          circular = true;
          if (risk === "low") risk = "medium";
          break;
        }
      }
      if (circular) break;
    }
  }

  return {
    wash_trading_risk: risk,
    circular_patterns: circular,
    bidirectional_pair_share: Math.round(bidShare * 1000) / 1000,
    ping_pong_pairs: pingPongPairs,
  };
}
