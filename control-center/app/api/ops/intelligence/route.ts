import { NextResponse } from "next/server";
import { buildIntelligenceData } from "@/lib/intelligence-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. The /intelligence page's training + collection chart data as JSON, for the
// client component's own re-fetches — app/intelligence/page.tsx's initial server render calls
// buildIntelligenceData() directly (lib/intelligence-server.ts), same split as the Review
// Queue's app/api/ops/queue/route.ts + lib/queue-server.ts.

export async function GET() {
  const data = await buildIntelligenceData();
  if (!data.connected) {
    return NextResponse.json(data, { status: "error" in data ? 503 : 200 });
  }
  return NextResponse.json(data);
}
