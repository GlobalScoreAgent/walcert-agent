import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

/** Service-role client. The key lives only inside the Edge runtime. */
export function getServiceClient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  return createClient(url, key);
}
