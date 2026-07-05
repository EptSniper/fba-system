// lib/proposals.ts — pure parser for learning-hub/tracking/brain-proposals.md (CC2 /proposals
// page). Written by scout/propose_updates.py's render_report() (see that file's exact string
// format — this parser matches it line-for-line, not a guess). Read-only: this module and the
// page that uses it NEVER write to the file or to ai-brain.json.
//
// "Applied" convention (defined here since propose_updates.py only ever appends PENDING runs —
// no applied-marker convention existed before CC2): a human marks a bullet applied by appending
// " — **APPLIED YYYY-MM-DD**" to its line. brain-proposals.md's own header instructions were
// updated to say so explicitly.

export type ProposalId = string;

// Shared with lib/proposal-drafts.ts's ledger (that module imports these types from here —
// this file stays a pure, fs-free parser; proposal-drafts.ts owns the actual fs reads/writes).
export type DraftPayload = {
  key: string;
  previousValue: unknown;
  proposedValue: unknown;
  rationale: string;
};

export type DecisionAction = "rejected" | "approved_no_draft" | "staged" | "confirmed" | "discarded";

export type ProposalStatus =
  | { state: "pending" }
  | { state: "rejected" }
  | { state: "approved_no_draft"; reason: string }
  | { state: "staged"; draft: DraftPayload }
  | { state: "confirmed"; draft: DraftPayload }
  | { state: "discarded" };

export type ProposalItem = {
  id: ProposalId; // stable across reads: `${runDate}::${indexWithinRun}` — see proposalId() below
  kind: string; // "data-driven" | "knowledge-driven" | "outcome-driven" | ...
  finding: string;
  sampleSize: number | null;
  confidence: string | null;
  brainKey: string | null;
  applied: boolean;
  appliedDate: string | null;
};

// A proposal has no ID of its own in brain-proposals.md (just an array position within a run
// block) — this file is append-only and bullets are never reordered/removed, so
// `${runDate}::${indexWithinRun}` is stable in practice. lib/proposal-drafts.ts's ledger keys
// its decision events on this same id.
export function proposalId(runDate: string, indexWithinRun: number): string {
  return `${runDate}::${indexWithinRun}`;
}

export type ProposalRun = {
  date: string; // e.g. "2026-07-02 04:31 UTC", verbatim from the "## ... — proposal run" header
  proposals: ProposalItem[];
  empty: boolean; // "No proposals this run."
};

const RUN_HEADER_RE = /^##\s+(.+?)\s+—\s+proposal run\s*$/;
const BULLET_RE = /^-\s+\*\*\[([^\]]+)\]\*\*\s+(.*)$/;
const META_RE = /\(sample size:\s*(\d+),\s*confidence:\s*([^,)]+)(?:,\s*key:\s*`([^`]+)`)?\)\s*$/;
const APPLIED_RE = /\s+—\s+\*\*APPLIED\s+(\d{4}-\d{2}-\d{2})\*\*\s*$/i;

function parseBullet(line: string, id: string): ProposalItem | null {
  const m = BULLET_RE.exec(line.trim());
  if (!m) return null;
  const kind = m[1];
  let rest = m[2];

  let applied = false;
  let appliedDate: string | null = null;
  const appliedMatch = APPLIED_RE.exec(rest);
  if (appliedMatch) {
    applied = true;
    appliedDate = appliedMatch[1];
    rest = rest.slice(0, appliedMatch.index);
  }

  const metaMatch = META_RE.exec(rest);
  const sampleSize = metaMatch ? Number(metaMatch[1]) : null;
  const confidence = metaMatch ? metaMatch[2].trim() : null;
  const brainKey = metaMatch?.[3] ?? null;
  const finding = (metaMatch ? rest.slice(0, metaMatch.index) : rest).trim();

  return { id, kind, finding, sampleSize, confidence, brainKey, applied, appliedDate };
}

export function parseProposals(markdown: string): ProposalRun[] {
  const lines = markdown.split(/\r?\n/);
  const runs: ProposalRun[] = [];
  let current: ProposalRun | null = null;

  for (const line of lines) {
    const headerMatch = RUN_HEADER_RE.exec(line.trim());
    if (headerMatch) {
      current = { date: headerMatch[1], proposals: [], empty: false };
      runs.push(current);
      continue;
    }
    if (!current) continue;
    if (line.trim() === "No proposals this run.") {
      current.empty = true;
      continue;
    }
    const item = parseBullet(line, proposalId(current.date, current.proposals.length));
    if (item) current.proposals.push(item);
  }

  // File is append-only (oldest first) — most-recent run first for display.
  return runs.reverse();
}

// Merges the markdown's own legacy "applied" marker with the ledger's richer per-proposal
// status (approve/reject/staged draft/confirmed/discarded) — the markdown-level marker is a
// hand-edit convention that predates the ledger and stays valid (a human can still mark
// something applied by hand), so it wins over "pending" if the ledger has nothing newer.
export function effectiveStatus(item: ProposalItem, ledgerStatus: ProposalStatus | undefined): ProposalStatus {
  if (ledgerStatus && ledgerStatus.state !== "pending") return ledgerStatus;
  if (item.applied) return { state: "confirmed", draft: { key: item.brainKey ?? "", previousValue: undefined, proposedValue: undefined, rationale: `Marked applied by hand on ${item.appliedDate}.` } };
  return { state: "pending" };
}

export function pendingCount(runs: ProposalRun[], ledgerStatuses?: Map<ProposalId, ProposalStatus>): number {
  return runs.reduce(
    (sum, r) => sum + r.proposals.filter((p) => effectiveStatus(p, ledgerStatuses?.get(p.id)).state === "pending").length,
    0,
  );
}
