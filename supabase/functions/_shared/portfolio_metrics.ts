export type PortfolioPosition = {
  name?: string;
  symbol?: string;
  value_usd?: number;
  category?: string;
  classification?: string;
  position_type?: string | null;
  protocol?: string | null;
  flags?: Record<string, unknown> | null;
  verified?: boolean | null;
};

export type PortfolioMetrics = {
  total_value_usd: number;
  liquid_ratio: number;
  category_distribution: Record<string, number>;
  concentration: { top1_share: number; hhi: number };
  dust_filtered_count: number;
  spam_filtered_count: number;
  defi_exposure_pct: number;
  positions_used: number;
};

const STABLE = new Set(["USDC", "USDT", "DAI", "CUSD", "USDM", "EURC", "USDCE"]);
const BLUE = new Set([
  "ETH", "WETH", "BTC", "WBTC", "CELO", "MATIC", "POL", "ARB", "OP", "BNB", "SOL",
]);

const DUST = 1.0;

function classify(p: PortfolioPosition): { category: string; locked: boolean; spam: boolean; unpriced: boolean } {
  const value = Number(p.value_usd);
  const unpriced = !Number.isFinite(value) || value <= 0;
  const flags = p.flags || {};
  const spam = Boolean(
    flags.is_trash || flags.trash || flags.spam ||
      (p.verified === false && (p.category === "meme_or_other" || !p.category)),
  );
  const ptype = String(p.position_type || p.protocol || "").toLowerCase();
  const sym = String(p.symbol || "").toUpperCase();
  const name = String(p.name || "").toLowerCase();

  let category = p.category || "meme_or_other";
  let locked = p.classification === "locked";

  if (
    ptype.includes("liquidity") || ptype.includes("pool") || ptype.includes("lp") ||
    name.includes("pool") || sym.includes("LP")
  ) {
    category = "defi_lp";
    locked = locked || ptype.includes("staked") || ptype.includes("locked");
  } else if (ptype.includes("staked") || ptype.includes("locked") || ptype.includes("deposit")) {
    locked = true;
    if (category === "meme_or_other" || !p.category) category = "meme_or_other";
  } else if (STABLE.has(sym) || sym.includes("USD")) {
    category = "stablecoin";
  } else if (BLUE.has(sym)) {
    category = "bluechip";
  }

  return { category, locked, spam, unpriced };
}

export function computePortfolioMetrics(positions: PortfolioPosition[]): PortfolioMetrics {
  let dust_filtered_count = 0;
  let spam_filtered_count = 0;
  const usable: Array<PortfolioPosition & { category: string; locked: boolean; value: number }> = [];

  for (const p of positions) {
    const c = classify(p);
    const value = Number(p.value_usd) || 0;
    if (c.unpriced || c.spam) {
      spam_filtered_count++;
      continue;
    }
    if (value < DUST) {
      dust_filtered_count++;
      continue;
    }
    usable.push({ ...p, category: c.category, locked: c.locked, value });
  }

  const total = usable.reduce((s, p) => s + p.value, 0);
  const locked = usable.filter((p) => p.locked).reduce((s, p) => s + p.value, 0);
  const liquid = total - locked;
  const cats: Record<string, number> = {
    stablecoin: 0,
    bluechip: 0,
    defi_lp: 0,
    meme_or_other: 0,
  };
  for (const p of usable) {
    const k = cats[p.category] !== undefined ? p.category : "meme_or_other";
    cats[k] += p.value;
  }
  const dist: Record<string, number> = {};
  for (const [k, v] of Object.entries(cats)) {
    dist[k] = total > 0 ? Math.round((1000 * v) / total) / 10 : 0;
  }

  const sorted = [...usable].sort((a, b) => b.value - a.value);
  const top1 = sorted[0]?.value || 0;
  const top1_share = total > 0 ? top1 / total : 0;
  let hhi = 0;
  if (total > 0) {
    for (const p of usable) {
      const s = p.value / total;
      hhi += s * s;
    }
  }

  const defi = usable
    .filter((p) => p.category === "defi_lp" || p.locked)
    .reduce((s, p) => s + p.value, 0);

  return {
    total_value_usd: Math.round(total * 100) / 100,
    liquid_ratio: total > 0 ? Math.round((1000 * liquid) / total) / 10 : 0,
    category_distribution: dist,
    concentration: {
      top1_share: Math.round(top1_share * 1000) / 1000,
      hhi: Math.round(hhi * 1000) / 1000,
    },
    dust_filtered_count,
    spam_filtered_count,
    defi_exposure_pct: total > 0 ? Math.round((1000 * defi) / total) / 10 : 0,
    positions_used: usable.length,
  };
}

export function gradePortfolio(m: PortfolioMetrics): "A" | "B" | "C" | "D" | "F" {
  const meme = m.category_distribution.meme_or_other || 0;
  const size = m.total_value_usd;
  const liq = m.liquid_ratio;
  const conc = m.concentration.top1_share;
  const hhi = m.concentration.hhi;

  if (size < 10 || (meme > 85 && size < 500)) return "F";
  if (size < 100 || meme > 70 || conc > 0.92) return "D";
  if (size >= 10000 && liq >= 60 && meme <= 15 && conc <= 0.55 && hhi <= 0.4) return "A";
  if (size >= 2000 && liq >= 50 && meme <= 30 && conc <= 0.7) return "B";
  return "C";
}
