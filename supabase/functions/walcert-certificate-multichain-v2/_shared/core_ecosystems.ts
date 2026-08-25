/** Mirror of app/providers/core_ecosystems.py — bump CORE_ECOSYSTEM_LIST_VERSION together. */

export const CORE_ECOSYSTEM_LIST_VERSION = "2026-07-26";

export const CORE_ECOSYSTEMS = new Set([
  "eth",
  "base",
  "celo",
  "arbitrum",
  "optimism",
  "polygon",
]);

const ALIASES: Record<string, string> = {
  ethereum: "eth",
  matic: "polygon",
};

export function normalizeCoreSlug(chain: string): string | null {
  let key = (chain || "").toLowerCase().trim();
  if (key.endsWith("-mainnet")) key = key.slice(0, -"-mainnet".length);
  if (ALIASES[key]) key = ALIASES[key];
  return CORE_ECOSYSTEMS.has(key) ? key : null;
}
