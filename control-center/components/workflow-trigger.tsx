"use client";

import * as React from "react";
import { Loader2, Play } from "lucide-react";
import { Badge } from "@/components/ui";
import { cn } from "@/lib/cn";

// The Runs Health panel's "run now" buttons (2026-07-09): GitHub's own `schedule:` cron is NOT
// reliably hourly under load (live-observed gaps of 1.5-3.5h+ on both keepa-collect.yml and
// train-ranker.yml this same session) — this triggers a REAL workflow_dispatch run through
// /api/ops/dispatch (the exact same code path the hourly cron uses) and then polls
// /api/ops/dispatch/status so the button's own state tells you what actually happened, not just
// that a click was registered.

type Workflow = "keepa-collect" | "train-ranker";

type RunStatus = { id: number; status: string; conclusion: string | null; createdAt: string; htmlUrl: string };

const LABELS: Record<Workflow, string> = {
  "keepa-collect": "Run collector now",
  "train-ranker": "Train ranker now",
};

const POLL_INTERVAL_MS = 4000;
const MAX_POLLS = 45; // ~3 minutes — both workflows finish in well under a minute normally

async function fetchStatus(workflow: Workflow): Promise<RunStatus | null> {
  const res = await fetch(`/api/ops/dispatch/status?workflow=${workflow}`, { cache: "no-store" });
  if (!res.ok) return null;
  const data = await res.json();
  return data.run ?? null;
}

function TriggerButton({ workflow }: { workflow: Workflow }) {
  const [phase, setPhase] = React.useState<"idle" | "dispatching" | "waiting" | "running" | "done" | "error">("idle");
  const [message, setMessage] = React.useState<string | null>(null);
  const [runUrl, setRunUrl] = React.useState<string | null>(null);
  const pollRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => () => {
    if (pollRef.current) clearTimeout(pollRef.current);
  }, []);

  const run = React.useCallback(async () => {
    setPhase("dispatching");
    setMessage(null);
    setRunUrl(null);

    // Baseline: the run that was already latest BEFORE this click, so polling can tell "the run
    // I just triggered" apart from "the same old run that hasn't changed yet."
    const before = await fetchStatus(workflow);
    const beforeId = before?.id ?? null;

    const res = await fetch("/api/ops/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setPhase("error");
      setMessage(data.error ?? "Could not trigger the workflow.");
      return;
    }
    setPhase("waiting");

    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      const latest = await fetchStatus(workflow);
      if (latest && latest.id !== beforeId) {
        setRunUrl(latest.htmlUrl);
        if (latest.status === "completed") {
          setPhase(latest.conclusion === "success" ? "done" : "error");
          setMessage(
            latest.conclusion === "success"
              ? "Completed successfully."
              : `Finished with conclusion: ${latest.conclusion ?? "unknown"}.`,
          );
          return;
        }
        setPhase("running");
        setMessage(latest.status === "queued" ? "Queued on GitHub…" : "Running…");
      } else {
        setMessage("Waiting for GitHub to pick up the run…");
      }
      if (attempts < MAX_POLLS) {
        pollRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      } else {
        setPhase("error");
        setMessage("Still not showing as started after ~3 minutes — check the Actions tab directly.");
      }
    };
    pollRef.current = setTimeout(poll, POLL_INTERVAL_MS);
  }, [workflow]);

  const busy = phase === "dispatching" || phase === "waiting" || phase === "running";

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className={cn(
          "flex cursor-pointer items-center justify-center gap-1.5 rounded border px-2.5 py-1.5 text-[12px] font-medium transition-colors disabled:cursor-not-allowed",
          busy
            ? "border-line2 text-muted"
            : "border-accent/50 text-accent hover:bg-accent/10",
        )}
      >
        {busy ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Play size={13} aria-hidden />}
        {LABELS[workflow]}
      </button>
      {message ? (
        <p className="flex items-center gap-1.5 text-[11px] text-faint">
          {phase === "done" ? <Badge tone="success">done</Badge> : phase === "error" ? <Badge tone="loss">error</Badge> : null}
          <span>{message}</span>
          {runUrl ? (
            <a href={runUrl} target="_blank" rel="noreferrer" className="text-accent underline">
              view run
            </a>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

export function WorkflowTriggers() {
  return (
    <div className="flex flex-wrap gap-3 border-t border-line pt-2.5">
      <TriggerButton workflow="keepa-collect" />
      <TriggerButton workflow="train-ranker" />
    </div>
  );
}
