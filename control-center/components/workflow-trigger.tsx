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
//
// Review fix (2026-07-09, live incident): the first version gave up after 3 minutes and called
// it "error" if GitHub's run-list API hadn't yet surfaced the new run — but GitHub's Actions
// queue has been demonstrably slow this session (scheduled crons landing 1.5-3.5h late; here, a
// manually dispatched run sat in `queued` for 4+ minutes before even showing up as distinct from
// the prior run). The dispatch itself HAD succeeded (confirmed live: the run existed on GitHub
// the whole time, just slow to appear/start) — labeling that "error" is actively misleading.
// Now polls for much longer, and a timeout without a detected new run is an honest "still
// pending" state, never phrased as a failure.

type Workflow = "keepa-collect" | "train-ranker";

type RunStatus = { id: number; status: string; conclusion: string | null; createdAt: string; htmlUrl: string };

const LABELS: Record<Workflow, string> = {
  "keepa-collect": "Run collector now",
  "train-ranker": "Train ranker now",
};

const POLL_INTERVAL_MS = 5000;
const MAX_POLLS = 120; // ~10 minutes — generous given GitHub's demonstrated queue delays this session

async function fetchStatus(workflow: Workflow): Promise<RunStatus | null> {
  const res = await fetch(`/api/ops/dispatch/status?workflow=${workflow}`, { cache: "no-store" });
  if (!res.ok) return null;
  const data = await res.json();
  return data.run ?? null;
}

function TriggerButton({ workflow }: { workflow: Workflow }) {
  const [phase, setPhase] = React.useState<"idle" | "dispatching" | "waiting" | "running" | "done" | "stalled" | "error">("idle");
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
    setMessage("Triggered — waiting for GitHub to show the new run…");

    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      const latest = await fetchStatus(workflow);
      const isOurs = latest && latest.id !== beforeId;

      // Show a link as soon as ANY run is known, even before we're sure it's ours — GitHub's
      // list can lag, so surfacing "here's the latest known run" beats leaving the operator
      // with nothing to check for minutes.
      if (latest) setRunUrl(latest.htmlUrl);

      if (isOurs && latest) {
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
        setMessage("Triggered, but GitHub hasn't shown the new run yet (its queue can lag several minutes) — still checking…");
      }
      if (attempts < MAX_POLLS) {
        pollRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      } else {
        // An honest "don't know yet," NOT a failure — the dispatch call itself already
        // succeeded (see /api/ops/dispatch's 200 above). GitHub may just still be catching up.
        setPhase("stalled");
        setMessage("Still hasn't shown as a new run after ~10 minutes. The trigger did succeed — check the Actions tab to see what's actually happening.");
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
          {phase === "done" ? <Badge tone="success">done</Badge>
            : phase === "error" ? <Badge tone="loss">error</Badge>
            : phase === "stalled" ? <Badge tone="warn">pending</Badge>
            : null}
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
