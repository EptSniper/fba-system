import { NextResponse } from "next/server";
import { appendDecisionEvent, readAllDecisionEvents, statusMap } from "@/lib/proposal-drafts";
import { applyBrainEdit } from "@/lib/brain-writer";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The second, separate human click that actually writes to ai-brain.json — /api/ops/
// proposals/decide only ever DRAFTS an edit, never applies one. This route requires a
// "staged" draft to already exist for the proposal; confirming re-validates the draft's
// value against the CURRENT brain state (applyBrainEdit's own type-family check) before
// writing, and never appends a "confirmed" ledger event if the write itself failed — a
// phantom "confirmed" record for an edit that never landed would be exactly the kind of
// ledger/reality split Code Review 2026-07-03 Finding #7 already fixed once elsewhere.
export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    const parsed: unknown = await req.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return NextResponse.json({ error: "Body must be a JSON object." }, { status: 400 });
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const proposalId = typeof body.proposalId === "string" ? body.proposalId : null;
  if (!proposalId) return NextResponse.json({ error: "proposalId is required." }, { status: 400 });
  const action = body.action;
  if (action !== "confirm" && action !== "discard") {
    return NextResponse.json({ error: 'action must be "confirm" or "discard".' }, { status: 400 });
  }

  const status = statusMap(readAllDecisionEvents()).get(proposalId);
  if (!status || status.state !== "staged") {
    return NextResponse.json({ error: "No staged draft exists for this proposal — approve it first." }, { status: 400 });
  }

  if (action === "discard") {
    appendDecisionEvent({ proposalId, action: "discarded" });
    return NextResponse.json({ ok: true, status: { state: "discarded" } });
  }

  const result = applyBrainEdit(status.draft.key, status.draft.proposedValue);
  if (!result.ok) {
    return NextResponse.json({ error: `Could not apply the edit: ${result.error}` }, { status: 502 });
  }

  appendDecisionEvent({ proposalId, action: "confirmed", draft: status.draft });
  return NextResponse.json({ ok: true, status: { state: "confirmed", draft: status.draft } });
}
