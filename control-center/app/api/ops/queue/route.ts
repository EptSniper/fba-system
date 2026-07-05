import { NextResponse } from "next/server";
import { buildQueue } from "@/lib/queue-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Read-only. The Review Queue's data as JSON, for the client component's own re-fetches
// (e.g. a future "refresh" affordance — no client calls this yet; app/queue/page.tsx's initial
// server render calls lib/queue-server.ts buildQueue() directly). Import the QueueItem types
// from @/lib/queue-server, not from this route.

export async function GET() {
  const { connected, items } = await buildQueue();
  if (!connected) {
    return NextResponse.json({ connected: false, items: [] });
  }
  return NextResponse.json({ connected: true, items });
}
