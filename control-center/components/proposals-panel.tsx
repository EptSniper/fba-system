"use client";

import * as React from "react";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { ProposalRun, ProposalStatus, ProposalId } from "@/lib/proposals";
import { effectiveStatus } from "@/lib/proposals";

const kindTone: Record<string, "info" | "accent" | "warn"> = {
  "data-driven": "info",
  "knowledge-driven": "accent",
  "outcome-driven": "warn",
};

function jsonPreview(v: unknown): string {
  if (v === undefined) return "—";
  return JSON.stringify(v);
}

export function ProposalsPanel({
  runs,
  initialStatuses,
}: {
  runs: ProposalRun[];
  initialStatuses: Record<ProposalId, ProposalStatus>;
}) {
  const [statuses, setStatuses] = React.useState(initialStatuses);
  const [busyId, setBusyId] = React.useState<ProposalId | null>(null);
  const [errorFor, setErrorFor] = React.useState<Record<ProposalId, string>>({});

  async function decide(id: ProposalId, verdict: "approve" | "reject") {
    setBusyId(id);
    setErrorFor((e) => ({ ...e, [id]: "" }));
    try {
      const res = await fetch("/api/ops/proposals/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposalId: id, verdict }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorFor((e) => ({ ...e, [id]: data.error ?? "Could not record the decision." }));
        return;
      }
      setStatuses((s) => ({ ...s, [id]: data.status }));
    } catch {
      setErrorFor((e) => ({ ...e, [id]: "Network error — is the dev server running?" }));
    } finally {
      setBusyId(null);
    }
  }

  async function resolveStaged(id: ProposalId, action: "confirm" | "discard") {
    setBusyId(id);
    setErrorFor((e) => ({ ...e, [id]: "" }));
    try {
      const res = await fetch("/api/ops/proposals/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposalId: id, action }),
      });
      const data = await res.json();
      if (!res.ok) {
        setErrorFor((e) => ({ ...e, [id]: data.error ?? "Could not resolve the draft." }));
        return;
      }
      setStatuses((s) => ({ ...s, [id]: data.status }));
    } catch {
      setErrorFor((e) => ({ ...e, [id]: "Network error — is the dev server running?" }));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {runs.map((run) => (
        <div key={run.date} className="surface overflow-hidden">
          <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
            <span className="num text-[11px] text-faint">{run.date}</span>
            <span className="num text-[11px] text-faint">{run.proposals.length} finding{run.proposals.length === 1 ? "" : "s"}</span>
          </header>
          <div className="p-3">
            {run.empty ? (
              <p className="text-sm text-muted">No proposals this run.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-line text-sm">
                {run.proposals.map((p) => {
                  const status = effectiveStatus(p, statuses[p.id]);
                  const busy = busyId === p.id;
                  const err = errorFor[p.id];
                  return (
                    <li key={p.id} className="flex flex-col gap-1.5 py-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <Badge tone={kindTone[p.kind] ?? "muted"}>{p.kind}</Badge>
                        <StatusBadge status={status} />
                      </div>
                      <p className="text-ink">{p.finding}</p>
                      <p className="num text-xs text-faint">
                        sample size: {p.sampleSize ?? "—"} · confidence: {p.confidence ?? "—"}
                        {p.brainKey ? <> · key: <code>{p.brainKey}</code></> : null}
                      </p>

                      {status.state === "pending" ? (
                        <div className="flex gap-2 pt-1">
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => decide(p.id, "approve")}
                            className="cursor-pointer rounded border border-profit/40 px-2 py-1 text-xs text-profit transition-colors hover:bg-profit/10 disabled:opacity-50"
                          >
                            {busy ? "Drafting…" : "Approve"}
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => decide(p.id, "reject")}
                            className="cursor-pointer rounded border border-loss/40 px-2 py-1 text-xs text-loss transition-colors hover:bg-loss/10 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      ) : null}

                      {status.state === "approved_no_draft" ? (
                        <p className="text-xs text-faint">Approved — {status.reason}</p>
                      ) : null}

                      {status.state === "staged" ? (
                        <div className="mt-1 flex flex-col gap-1.5 rounded border border-accent/30 bg-accent/5 p-2">
                          <p className="num text-xs text-ink">
                            <code>{status.draft.key}</code>: {jsonPreview(status.draft.previousValue)} → <span className="text-accent">{jsonPreview(status.draft.proposedValue)}</span>
                          </p>
                          <p className="text-xs text-faint">{status.draft.rationale}</p>
                          <div className="flex gap-2 pt-1">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => resolveStaged(p.id, "confirm")}
                              className="cursor-pointer rounded border border-profit/40 px-2 py-1 text-xs text-profit transition-colors hover:bg-profit/10 disabled:opacity-50"
                            >
                              {busy ? "Applying…" : "Confirm — write to ai-brain.json"}
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => resolveStaged(p.id, "discard")}
                              className="cursor-pointer rounded border border-line2 px-2 py-1 text-xs text-muted transition-colors hover:bg-panel2 disabled:opacity-50"
                            >
                              Discard draft
                            </button>
                          </div>
                        </div>
                      ) : null}

                      {status.state === "confirmed" ? (
                        <p className="num text-xs text-faint">
                          <code>{status.draft.key}</code>: {jsonPreview(status.draft.previousValue)} → {jsonPreview(status.draft.proposedValue)}
                        </p>
                      ) : null}

                      {err ? <p className={cn("text-xs text-loss")}>{err}</p> : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: ProposalStatus }) {
  switch (status.state) {
    case "pending":
      return <Badge tone="muted">pending</Badge>;
    case "rejected":
      return <Badge tone="loss">rejected</Badge>;
    case "approved_no_draft":
      return <Badge tone="warn">approved — no draft</Badge>;
    case "staged":
      return <Badge tone="accent">draft ready</Badge>;
    case "confirmed":
      return <Badge tone="success">applied</Badge>;
    case "discarded":
      return <Badge tone="muted">discarded</Badge>;
  }
}
