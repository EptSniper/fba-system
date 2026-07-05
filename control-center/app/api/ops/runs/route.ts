import { NextResponse } from "next/server";
import { getRecentRuns, supabaseConfigured } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. Runs health panel (CC1) — last run status, tokens, leads written. Honest
// "not connected" when Supabase isn't configured; honest [] (not fabricated) when it is
// configured but the scout has genuinely never run yet.
export async function GET() {
  if (!supabaseConfigured()) {
    return NextResponse.json({ connected: false, runs: [] });
  }
  const runs = await getRecentRuns(14);
  if (runs === null) {
    return NextResponse.json({ connected: false, runs: [], error: "Could not reach Supabase." }, { status: 503 });
  }
  return NextResponse.json({ connected: true, runs });
}
