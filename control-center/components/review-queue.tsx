"use client";

import * as React from "react";
import { Keyboard, ShieldAlert } from "lucide-react";
import { Badge, EmptyState } from "@/components/ui";
import { money, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import type { QueueItem } from "@/lib/queue-server";
import { REASON_CODES } from "@/lib/reason-codes";
import { explainSummary } from "@/lib/explain";

// The Review Queue (CC1) — the ONE place every scout lead marked "review" and every
// unresolved deal-match verification waits for a human. Keyboard-first: j/k select, A/R/W
// start a decision, then a number key picks the REQUIRED reason code. Every decision POSTs to
// /api/ops/decide, which is the only writer to Supabase's decisions/deal_matches tables from
// this app — there is no auto-approve anywhere in this component.

type Verdict = "approve" | "reject" | "watch";

export function ReviewQueue({ initialItems, connected }: { initialItems: QueueItem[]; connected: boolean }) {
  const [items, setItems] = React.useState(initialItems);
  const [selected, setSelected] = React.useState(0);
  const [pendingVerdict, setPendingVerdict] = React.useState<Verdict | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const current = items[selected];

  const submit = React.useCallback(
    async (verdict: Verdict, reasonCode: string) => {
      if (!current || busy) return;
      setBusy(true);
      setMsg(null);
      try {
        const res = await fetch("/api/ops/decide", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind: current.kind,
            id: current.id,
            verdict,
            reasonCode,
            // Approved buys feed scout's brand re-mining loop server-side — only leads carry a brand.
            brand: current.kind === "lead" ? current.brand ?? undefined : undefined,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          // Includes the Supabase-write-failed 502: nothing was recorded, item stays queued.
          setMsg({ tone: "err", text: data.error ?? "Could not record the decision." });
          return;
        }
        setItems((cur) => cur.filter((it) => !(it.kind === current.kind && it.id === current.id)));
        setSelected((s) => Math.max(0, Math.min(s, items.length - 2)));
        setMsg({ tone: "ok", text: `${verdict === "approve" ? "Approved" : verdict === "reject" ? "Rejected" : "Watching"} — reason: ${reasonCode}.` });
      } catch {
        setMsg({ tone: "err", text: "Network error — is the dev server running?" });
      } finally {
        setBusy(false);
        setPendingVerdict(null);
      }
    },
    [current, items.length, busy],
  );

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (busy) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (pendingVerdict) {
        if (e.key === "Escape") {
          setPendingVerdict(null);
          return;
        }
        const idx = Number(e.key) - 1;
        if (idx >= 0 && idx < REASON_CODES.length) submit(pendingVerdict, REASON_CODES[idx].code);
        return;
      }

      if (e.key === "j") setSelected((s) => Math.min(s + 1, Math.max(0, items.length - 1)));
      else if (e.key === "k") setSelected((s) => Math.max(s - 1, 0));
      else if (e.key.toLowerCase() === "a") setPendingVerdict("approve");
      else if (e.key.toLowerCase() === "r") setPendingVerdict("reject");
      else if (e.key.toLowerCase() === "w" && current?.kind === "lead") setPendingVerdict("watch");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length, pendingVerdict, submit, busy, current]);

  if (!connected) {
    return (
      <EmptyState
        title="Supabase not configured"
        hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in control-center/.env.local to use the Review Queue."
      />
    );
  }
  if (!items.length) {
    return (
      <EmptyState
        title="Queue is empty"
        hint="Nothing is waiting on a human decision right now — scout leads marked 'review' and unresolved deal matches appear here."
      />
    );
  }

  return (
    <div className="flex flex-col gap-3 pb-16">
      <p className="flex items-center gap-1.5 text-xs text-faint">
        <Keyboard size={12} aria-hidden />
        j/k navigate · A approve · R reject{current?.kind === "lead" ? " · W watch" : ""} · number key picks the reason
      </p>
      {msg ? (
        <div className={cn("rounded border px-3 py-2 text-xs", msg.tone === "ok" ? "border-profit/30 text-profit" : "border-loss/30 text-loss")}>
          {msg.text}
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        {items.map((it, i) => (
          <QueueCard
            key={`${it.kind}-${it.id}`}
            item={it}
            active={i === selected}
            // Ignore selection clicks while a decision is in flight — the list is about to
            // shift, and acting on a stale index would point the verdict at the wrong item.
            onClick={() => !busy && setSelected(i)}
          />
        ))}
      </div>

      {pendingVerdict ? (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-panel p-3 sm:static sm:z-auto sm:rounded-lg sm:border">
          <div className="mb-2 text-xs text-muted">
            {pendingVerdict === "approve" ? "Approve" : pendingVerdict === "reject" ? "Reject" : "Watch"} — pick a reason (Escape to cancel):
          </div>
          <div className="flex flex-wrap gap-1.5">
            {REASON_CODES.map((r, i) => (
              <button
                key={r.code}
                type="button"
                disabled={busy}
                onClick={() => submit(pendingVerdict, r.code)}
                className="cursor-pointer rounded border border-line px-2 py-1 text-xs text-ink transition-colors hover:border-accent disabled:opacity-50"
              >
                {i + 1}. {r.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function QueueCard({ item, active, onClick }: { item: QueueItem; active: boolean; onClick: () => void }) {
  const summary = item.kind === "lead" ? explainSummary(item.explanation) : null;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "surface flex w-full cursor-pointer flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors",
        active ? "border-accent" : "border-line hover:border-line2",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <Badge tone={item.kind === "lead" ? "accent" : "info"}>{item.kind === "lead" ? "scout lead" : "deal match"}</Badge>
        <span className="num text-[11px] text-faint">priority {item.priority.toFixed(2)}</span>
      </div>

      {item.kind === "lead" ? (
        <>
          <div className="min-w-0">
            <span className="block truncate text-sm text-ink">{item.title ?? item.asin ?? `lead #${item.id}`}</span>
            <span className="num text-xs text-muted">
              {item.asin} · {item.brand ?? "no brand"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            {item.profit !== null ? <span className="num text-muted">{money(item.profit)}/u</span> : null}
            {item.roi !== null ? <span className="num text-muted">{pct(item.roi)} ROI</span> : null}
            {item.bsr !== null ? <span className="num text-muted">BSR {item.bsr.toLocaleString()}</span> : null}
          </div>
          {summary ? <p className="text-xs text-faint">{summary}</p> : null}
        </>
      ) : (
        <>
          <div className="min-w-0">
            <span className="block truncate text-sm text-ink">{item.asin ?? `deal #${item.dealId}`}</span>
            <span className="num text-xs text-muted">
              deal #{item.dealId} · method: {item.method ?? "unknown"} {item.packMatch === false ? "· pack mismatch risk" : ""}
            </span>
          </div>
          {item.confidence !== null ? (
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <ShieldAlert size={12} aria-hidden />
              confidence {pct(item.confidence)}
            </div>
          ) : null}
          {item.llmReason ? <p className="text-xs text-faint">{item.llmReason}</p> : null}
        </>
      )}
    </button>
  );
}
