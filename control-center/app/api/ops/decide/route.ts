import { NextResponse } from "next/server";
import {
  recordDealMatchVerdict,
  recordLeadDecision,
  supabaseConfigured,
} from "@/lib/supabase-server";
import { appendEvent, hubMissing } from "@/lib/events-server";
import { isReasonCode, REASON_CODES } from "@/lib/reason-codes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The Review Queue's ONLY write path (CC1). Human-only because middleware.ts requires
// operator Basic auth on every request (and refuses to serve a Supabase-configured deployment
// without auth) — not because of any assumption about who calls it. Every decision requires a
// reason code; free text is optional, never a substitute.

const KINDS = ["lead", "deal_match"] as const;
type Kind = (typeof KINDS)[number];

const VERDICTS = ["approve", "reject", "watch"] as const;
type Verdict = (typeof VERDICTS)[number];

function isKind(v: unknown): v is Kind {
  return typeof v === "string" && (KINDS as readonly string[]).includes(v);
}
function isVerdict(v: unknown): v is Verdict {
  return typeof v === "string" && (VERDICTS as readonly string[]).includes(v);
}
function positiveInt(v: unknown): number | null {
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isInteger(n) && n > 0 ? n : null;
}

export async function POST(req: Request) {
  if (!supabaseConfigured()) {
    return NextResponse.json(
      { error: "Supabase isn't configured (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY) — the Review Queue has nothing to decide against yet." },
      { status: 503 },
    );
  }

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

  const kind = body.kind;
  if (!isKind(kind)) {
    return NextResponse.json({ error: `kind must be one of: ${KINDS.join(", ")}` }, { status: 400 });
  }
  const id = positiveInt(body.id);
  if (id === null) {
    return NextResponse.json({ error: "id must be a positive integer." }, { status: 400 });
  }
  const verdict = body.verdict;
  if (!isVerdict(verdict)) {
    return NextResponse.json({ error: `verdict must be one of: ${VERDICTS.join(", ")}` }, { status: 400 });
  }
  const reasonCode = body.reasonCode;
  if (!isReasonCode(reasonCode)) {
    return NextResponse.json(
      { error: `reasonCode must be one of: ${REASON_CODES.map((r) => r.code).join(", ")}` },
      { status: 400 },
    );
  }
  const reasonText = typeof body.reasonText === "string" ? body.reasonText.trim().slice(0, 500) : "";
  const reason = reasonText ? `${reasonCode}: ${reasonText}` : reasonCode;
  const brand = typeof body.brand === "string" && body.brand.trim() ? body.brand.trim() : null;

  // deal_matches.human_verdict is only ever "approve" | "reject" | null (migration 003) — there
  // is no "watch" state for a match verification, unlike a lead's buy/wait/pass decision.
  if (kind === "deal_match" && verdict === "watch") {
    return NextResponse.json(
      { error: "A deal match can only be approved or rejected, not watched — it's a same-product verification, not a buy decision." },
      { status: 400 },
    );
  }

  let supabaseWritten: boolean;
  if (kind === "lead") {
    const decision = verdict === "approve" ? "buy" : verdict === "reject" ? "pass" : "wait";
    supabaseWritten = await recordLeadDecision({ leadId: id, decision, reason, reasonCode, brand });
  } else {
    supabaseWritten = await recordDealMatchVerdict(id, verdict as "approve" | "reject", reason);
  }

  // The Supabase write is the decision of record; the events.jsonl ledger line is its local
  // mirror. If Supabase failed, NOTHING is recorded and the caller gets an honest error —
  // appending a ledger event for a decision that never took effect would permanently
  // over-count human decisions once the retry succeeds (Code Review 2026-07-03, Finding #7).
  if (!supabaseWritten) {
    return NextResponse.json(
      { error: "Could not write the decision to Supabase — nothing was recorded. The item stays in the queue; try again." },
      { status: 502 },
    );
  }

  const payload = { kind, id, verdict, reasonCode, reasonText: reasonText || undefined };
  const event = hubMissing() ? null : appendEvent("decision", payload);

  return NextResponse.json({ ok: true, supabaseWritten, event });
}
