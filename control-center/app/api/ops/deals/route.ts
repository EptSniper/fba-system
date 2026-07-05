import { NextResponse } from "next/server";
import { getSupabaseDeals, supabaseConfigured } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. Live Supabase deals (CC1) — the collected-feed rows from scout/deals/
// (Slickdeals/Best Buy), independent of the local hub-data/deals.json snapshot the
// /deals page already reads (that one describes the FEATURE's honest not-yet-built
// status; this one is the raw collected rows once migration 003 + collect.py run).
export async function GET() {
  if (!supabaseConfigured()) {
    return NextResponse.json({ connected: false, deals: [] });
  }
  const deals = await getSupabaseDeals(200);
  if (deals === null) {
    return NextResponse.json({ connected: false, deals: [], error: "Could not reach Supabase." }, { status: 503 });
  }
  return NextResponse.json({ connected: true, deals });
}
