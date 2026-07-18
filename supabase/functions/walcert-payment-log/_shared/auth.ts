export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      Connection: "keep-alive",
    },
  });
}

async function resolveExpectedSecret(): Promise<string> {
  const fromEnv = (Deno.env.get("EDGE_SHARED_SECRET") ?? "").trim();
  if (fromEnv.length >= 16) return fromEnv;

  try {
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    const url = Deno.env.get("SUPABASE_URL") ?? "";
    const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
    if (!url || !key) return "";
    const client = createClient(url, key);
    const { data } = await client
      .schema("walcert")
      .from("edge_config")
      .select("value")
      .eq("key", "EDGE_SHARED_SECRET")
      .maybeSingle();
    return (data?.value ?? "").trim();
  } catch {
    return "";
  }
}

export async function requireAgentSecret(req: Request): Promise<Response | null> {
  const expected = await resolveExpectedSecret();
  if (!expected || expected.length < 16) {
    return jsonResponse(
      { error: "misconfigured", message: "Server secret not configured" },
      500,
    );
  }
  const header = req.headers.get("Authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  const alt = (req.headers.get("X-Walcert-Agent-Secret") ?? "").trim();
  const provided = token || alt;
  if (!provided || provided !== expected) {
    return jsonResponse(
      { error: "unauthorized", message: "Invalid or missing agent credentials" },
      401,
    );
  }
  return null;
}

export async function readJsonBody(req: Request): Promise<unknown> {
  const text = await req.text();
  if (!text || text.length > 1_500_000) {
    throw new Error("invalid_body_size");
  }
  return JSON.parse(text);
}
