export type Grade = "A" | "B" | "C" | "D" | "F";

export type Bilingual = { eng: string; esp: string };

const GRADE_LABELS: Record<Grade, Bilingual> = {
  A: { eng: "Excellent", esp: "Excelente" },
  B: { eng: "Good", esp: "Bueno" },
  C: { eng: "Acceptable", esp: "Aceptable" },
  D: { eng: "Weak", esp: "Débil" },
  F: { eng: "Poor / High risk", esp: "Deficiente / Alto riesgo" },
};

export function gradeLabel(grade: Grade): Bilingual {
  return GRADE_LABELS[grade];
}

export function issuer() {
  const agentId = Deno.env.get("WALCERT_ERC8004_AGENT_ID") || "9699";
  const wallet = Deno.env.get("WALCERT_AGENT_WALLET") ||
    "0xF4D938200445B0Df0f028af6d90D016147AEd095";
  return {
    name: "Walcert Agent",
    erc8004_agent_id: `eip155:42220:${wallet}`,
    agent_id: agentId,
    version: "1.0",
  };
}

export const PROVIDER =
  "Powered by Global Score Agent. We provide specialized scoring for autonomous agents with daily indices. Contact us or visit our website: globalscoreagent.com";

export async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hash = await globalThis.crypto.subtle.digest("SHA-256", data);
  return "0x" +
    [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function buildCertificate(params: {
  type: "ORIGINS" | "ACTIVITY" | "MULTICHAIN" | "PORTFOLIO";
  wallet: string;
  chain_id?: number;
  analyzed_at: string;
  grade: Grade;
  summary: { eng: string; esp: string };
  details: Record<string, unknown>;
  strengths: Bilingual[];
  concerns: Bilingual[];
}) {
  const certificate_id = globalThis.crypto.randomUUID();
  const base = {
    certificate_id,
    type: params.type,
    version: "1.0",
    wallet: params.wallet.toLowerCase(),
    chain_id: params.chain_id ?? 42220,
    analyzed_at: params.analyzed_at,
    analysis_mode: "hot",
    issuer: issuer(),
    provider: PROVIDER,
    grade: params.grade,
    grade_label: gradeLabel(params.grade),
    summary: params.summary,
    details: params.details,
    strengths: params.strengths,
    concerns: params.concerns,
  };
  const canonical = JSON.stringify(base);
  const data_hash = await sha256Hex(canonical);
  return { ...base, data_hash };
}

export function parseRequestBody(body: unknown): {
  wallet: string;
  analyzed_at: string;
  payload: Record<string, unknown>;
} {
  if (!body || typeof body !== "object") throw new Error("invalid_body");
  const b = body as Record<string, unknown>;
  const payload = (b.payload && typeof b.payload === "object"
    ? b.payload
    : b.analysis && typeof b.analysis === "object"
    ? b.analysis
    : b) as Record<string, unknown>;
  const wallet = String(b.wallet || payload.wallet || "").toLowerCase();
  if (!/^0x[a-f0-9]{40}$/.test(wallet)) throw new Error("invalid_wallet");
  const analyzed_at = String(
    b.analyzed_at || payload.analyzed_at || new Date().toISOString(),
  );
  return { wallet, analyzed_at, payload };
}

export function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86_400_000));
}
