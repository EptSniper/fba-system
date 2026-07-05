import { NextResponse } from "next/server";
import { getDealHints, supabaseConfigured } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. Fresh deal-watch hints (TOP100_DEAL_WATCH_PLAN.md T3) — the "look here first"
// brands the nightly deal watch derived and the scout consumes as its first discovery pass.
// Same three-state envelope as the other /api/ops routes (not configured / fetch failed /
// genuinely empty).
export async function GET() {
  if (!supabaseConfigured()) {
    return NextResponse.json({ connected: false, hints: [] });
  }
  const hints = await getDealHints(50);
  if (hints === null) {
    return NextResponse.json({ connected: false, hints: [], error: "Could not reach Supabase." }, { status: 503 });
  }
  return NextResponse.json({ connected: true, hints });
}
