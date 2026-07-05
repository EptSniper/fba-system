import { NextResponse } from "next/server";
import { getSupabaseLeads, supabaseConfigured } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. Live Supabase leads (CC1) as JSON. NOTE: app/leads/page.tsx does NOT call this —
// it's a server component that calls getSupabaseLeads() directly and renders the Supabase and
// local-ledger panels separately. This route exists for external/manual reads (curl, future
// client refresh); no client code fetches it today.
export async function GET() {
  if (!supabaseConfigured()) {
    return NextResponse.json({ connected: false, leads: [] });
  }
  const leads = await getSupabaseLeads(200);
  if (leads === null) {
    return NextResponse.json({ connected: false, leads: [], error: "Could not reach Supabase." }, { status: 503 });
  }
  return NextResponse.json({ connected: true, leads });
}
