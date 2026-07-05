// lib/proposal-drafts.ts — SERVER-ONLY append-only ledger for human decisions on
// brain-proposals.md findings (approve/reject/stage-a-draft/confirm/discard). Mirrors
// events.jsonl's append-only pattern rather than mutating brain-proposals.md itself —
// that file stays append-only-by-scout-only, so there's no risk of a concurrent write
// corrupting it.
//
// Proposal identity (`${runDate}::${indexWithinRun}`) and the DraftPayload/DecisionAction/
// ProposalStatus shapes are owned by lib/proposals.ts (a pure, fs-free module) — this ledger
// only imports the types and keys its events on the same id.
import fs from "node:fs";
import { hubTrackingPath } from "./events-server";
import type { DecisionAction, DraftPayload, ProposalId, ProposalStatus } from "./proposals";

export type { ProposalId, DraftPayload, DecisionAction, ProposalStatus };

const LEDGER_PATH = hubTrackingPath("brain-proposal-decisions.jsonl");

export type DecisionEvent = {
  id: string;
  ts: string;
  proposalId: ProposalId;
  action: DecisionAction;
  draft?: DraftPayload;
  reason?: string;
};

export function appendDecisionEvent(event: Omit<DecisionEvent, "id" | "ts">): DecisionEvent {
  const full: DecisionEvent = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: new Date().toISOString(),
    ...event,
  };
  fs.appendFileSync(LEDGER_PATH, JSON.stringify(full) + "\n", "utf8");
  return full;
}

export function readAllDecisionEvents(): DecisionEvent[] {
  let raw: string;
  try {
    raw = fs.readFileSync(LEDGER_PATH, "utf8");
  } catch {
    return []; // no ledger yet — every proposal is "pending", not an error
  }
  const events: DecisionEvent[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      events.push(JSON.parse(line) as DecisionEvent);
    } catch {
      // one corrupt line never discards the rest of the ledger
    }
  }
  return events;
}

// Latest event per proposal wins — a reject-then-re-approve, or a discard-then-re-approve,
// is a legitimate real sequence (a human changing their mind), not a conflict to resolve.
export function statusMap(events: DecisionEvent[]): Map<ProposalId, ProposalStatus> {
  const latest = new Map<ProposalId, DecisionEvent>();
  for (const e of events) latest.set(e.proposalId, e); // file is append-only chronological
  const result = new Map<ProposalId, ProposalStatus>();
  for (const [id, e] of latest) {
    switch (e.action) {
      case "rejected":
        result.set(id, { state: "rejected" });
        break;
      case "approved_no_draft":
        result.set(id, { state: "approved_no_draft", reason: e.reason ?? "No draft available." });
        break;
      case "staged":
        if (e.draft) result.set(id, { state: "staged", draft: e.draft });
        break;
      case "confirmed":
        if (e.draft) result.set(id, { state: "confirmed", draft: e.draft });
        break;
      case "discarded":
        result.set(id, { state: "discarded" });
        break;
    }
  }
  return result;
}
