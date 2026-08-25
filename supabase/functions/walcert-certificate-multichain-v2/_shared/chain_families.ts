/**
 * Chain → ecosystem family map for Multichain v2.1 (mirrors Python chain_families).
 */

const FAMILY_RULES: Array<[string, string]> = [
  ["arbitrum", "ethereum"],
  ["optimism", "ethereum"],
  ["base", "ethereum"],
  ["zksync", "ethereum"],
  ["zk-sync", "ethereum"],
  ["scroll", "ethereum"],
  ["linea", "ethereum"],
  ["zora", "ethereum"],
  ["blast", "ethereum"],
  ["mode", "ethereum"],
  ["eth", "ethereum"],
  ["ethereum", "ethereum"],
  ["matic", "polygon"],
  ["polygon", "polygon"],
  ["bsc", "bnb"],
  ["binance", "bnb"],
  ["bnb", "bnb"],
  ["avalanche", "avalanche"],
  ["avax", "avalanche"],
  ["celo", "celo"],
  ["gnosis", "gnosis"],
  ["xdai", "gnosis"],
  ["fantom", "fantom"],
  ["ftm", "fantom"],
  ["moonbeam", "polkadot"],
  ["moonriver", "polkadot"],
  ["solana", "solana"],
  ["cosmos", "cosmos"],
  ["osmosis", "cosmos"],
  ["near", "near"],
  ["tron", "tron"],
];

export function ecosystemFamilyFromChainName(name: string | null | undefined): string | null {
  const raw = String(name || "").trim().toLowerCase();
  if (!raw) return null;
  const sorted = [...FAMILY_RULES].sort((a, b) => b[0].length - a[0].length);
  for (const [key, family] of sorted) {
    if (
      raw === key ||
      raw.startsWith(key + "-") ||
      raw.includes("-" + key + "-") ||
      raw.endsWith("-" + key)
    ) {
      return family;
    }
    if (raw.split("-").includes(key)) return family;
  }
  const slug = raw.replace(/_/g, "-");
  return `other:${slug}`;
}
