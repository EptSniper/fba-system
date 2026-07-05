import { NextResponse } from "next/server";
import { hubTrackingPath, readTextFile } from "@/lib/events-server";
import { parseProposals } from "@/lib/proposals";
import { appendDecisionEvent } from "@/lib/proposal-drafts";
import { draftProposalEdit } from "@/lib/anthropic-draft";
import { getByPath, readBrainRaw } from "@/lib/brain-writer";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Approve/reject a brain-proposals.md finding (the human-approval step the user asked for).
// Reject is immediate. Approve triggers drafting RIGHT AWAY (a real Claude call) but never
// writes to ai-brain.json here — that only happens via /api/ops/proposals/confirm, a second,
// separate human click on the staged draft. Never invents a key to edit: drafting is only
// attempted when propose_updates.py already named one (see lib/anthropic-draft.ts).
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
  const verdict = body.verdict;
  if (verdict !== "approve" && verdict !== "reject") {
    return NextResponse.json({ error: 'verdict must be "approve" or "reject".' }, { status: 400 });
  }

  const markdown = readTextFile(hubTrackingPath("brain-proposals.md"));
  if (markdown === null) return NextResponse.json({ error: "Could not read brain-proposals.md." }, { status: 503 });

  const item = parseProposals(markdown).flatMap((r) => r.proposals).find((p) => p.id === proposalId);
  if (!item) return NextResponse.json({ error: `No proposal with id "${proposalId}".` }, { status: 404 });

  if (verdict === "reject") {
    appendDecisionEvent({ proposalId, action: "rejected" });
    return NextResponse.json({ ok: true, status: { state: "rejected" } });
  }

  if (!item.brainKey) {
    const reason = "propose_updates.py didn't identify a specific ai-brain.json key for this finding — drafting is only attempted when one is.";
    appendDecisionEvent({ proposalId, action: "approved_no_draft", reason });
    return NextResponse.json({ ok: true, status: { state: "approved_no_draft", reason } });
  }

  const brain = readBrainRaw();
  if (!brain) return NextResponse.json({ error: "Could not read ai-brain.json." }, { status: 503 });
  const currentValue = getByPath(brain, item.brainKey);

  const result = await draftProposalEdit(
    { kind: item.kind, finding: item.finding, sampleSize: item.sampleSize, confidence: item.confidence, brainKey: item.brainKey },
    currentValue,
  );

  if (result.status !== "ok") {
    appendDecisionEvent({ proposalId, action: "approved_no_draft", reason: result.reason });
    return NextResponse.json({ ok: true, status: { state: "approved_no_draft", reason: result.reason } });
  }

  const draft = { key: item.brainKey, previousValue: currentValue, proposedValue: result.proposedValue, rationale: result.rationale };
  appendDecisionEvent({ proposalId, action: "staged", draft });
  return NextResponse.json({ ok: true, status: { state: "staged", draft } });
}
