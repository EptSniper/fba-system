"use client";

import * as React from "react";
import { Keyboard, RefreshCw, ShieldAlert } from "lucide-react";
import { Badge, EmptyState } from "@/components/ui";
import { money, pct, bsr as bsrFmt, num, ago } from "@/lib/format";
import { cn } from "@/lib/cn";
import type { QueueItem } from "@/lib/queue-server";
import { REASON_CODES } from "@/lib/reason-codes";
import { explainSummary } from "@/lib/explain";

// How often to pull a fresh queue from /api/ops/queue in the background — catches leads/matches
// that appeared after the page's initial server render. Paused while a decision is mid-flight
// (busy) or a reason picker is open (pendingVerdict) so the list never shifts under the operator.
const AUTO_REFRESH_MS = 60_000;

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
  const [refreshing, setRefreshing] = React.useState(false);
  const [msg, setMsg] = React.useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const current = items[selected];

  // Pulls a fresh queue snapshot and reconciles it with local state — keeps the same item
  // selected (by kind+id) if it's still queued, otherwise clamps to the top of the list. Used
  // for the periodic background poll, the manual refresh button, and a fire-and-forget catch-up
  // after every decision (the optimistic local filter already removed the decided item; this
  // just picks up anything new that appeared server-side in the meantime).
  const refresh = React.useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/ops/queue", { cache: "no-store" });
      if (!res.ok) return;
      const data: { connected: boolean; items: QueueItem[] } = await res.json();
      if (!data.connected) return;
      setItems((prevItems) => {
        const prevCurrent = prevItems[selected];
        if (prevCurrent) {
          const stillHere = data.items.findIndex((it) => it.kind === prevCurrent.kind && it.id === prevCurrent.id);
          if (stillHere >= 0) setSelected(stillHere);
          else setSelected((s) => Math.max(0, Math.min(s, data.items.length - 1)));
        }
        return data.items;
      });
    } catch {
      // Silent — this is a background convenience refresh, not a user-initiated action; the
      // existing list stays put and the next periodic tick (or manual click) will retry.
    } finally {
      setRefreshing(false);
    }
  }, [selected]);

  React.useEffect(() => {
    if (busy || pendingVerdict) return;
    const id = window.setInterval(refresh, AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [busy, pendingVerdict, refresh]);

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
        void refresh();
      } catch {
        setMsg({ tone: "err", text: "Network error — is the dev server running?" });
      } finally {
        setBusy(false);
        setPendingVerdict(null);
      }
    },
    [current, items.length, busy, refresh],
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
    <div className="flex flex-col gap-3 pb-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-xs text-faint">
          <Keyboard size={12} aria-hidden />
          j/k navigate · A approve · R reject{current?.kind === "lead" ? " · W watch" : ""} · number key picks the reason
        </p>
        {/* Review fix (2026-07-09): the ONLY way to decide an item used to be the keyboard
            shortcuts above (A/R/W) — there was no clickable affordance at all, so a mouse user
            clicking cards was only ever selecting them, never actually recording a decision.
            These buttons drive the exact same setPendingVerdict() path the keyboard does. */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={refreshing}
            onClick={() => void refresh()}
            title="Pull a fresh queue from the server"
            className="cursor-pointer rounded border border-line p-1.5 text-faint transition-colors hover:border-accent hover:text-ink disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : undefined} aria-hidden />
          </button>
          <button
            type="button"
            disabled={busy || !current}
            onClick={() => setPendingVerdict("approve")}
            className="cursor-pointer rounded border border-profit/40 px-2.5 py-1 text-xs font-medium text-profit transition-colors hover:bg-profit/10 disabled:opacity-50"
          >
            Approve
          </button>
          <button
            type="button"
            disabled={busy || !current}
            onClick={() => setPendingVerdict("reject")}
            className="cursor-pointer rounded border border-loss/40 px-2.5 py-1 text-xs font-medium text-loss transition-colors hover:bg-loss/10 disabled:opacity-50"
          >
            Reject
          </button>
          {current?.kind === "lead" ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => setPendingVerdict("watch")}
              className="cursor-pointer rounded border border-line px-2.5 py-1 text-xs text-ink transition-colors hover:border-accent disabled:opacity-50"
            >
              Watch
            </button>
          ) : null}
        </div>
      </div>

      {/* Inline, not fixed-to-viewport: the picker now renders directly under the toolbar the
          operator just clicked, so it's impossible to miss (the old bottom-pinned bar could
          land off-screen on a tall page, which read as "the button did nothing"). */}
      {pendingVerdict ? (
        <div
          className={cn(
            "rounded border p-3",
            pendingVerdict === "approve" ? "border-profit/40 bg-profit/5" : pendingVerdict === "reject" ? "border-loss/40 bg-loss/5" : "border-line bg-panel2/50",
          )}
        >
          <div className="mb-2 text-xs font-medium text-ink">
            {pendingVerdict === "approve" ? "Approve" : pendingVerdict === "reject" ? "Reject" : "Watch"}
            {current ? <> — {current.kind === "lead" ? current.title ?? current.asin ?? `lead #${current.id}` : current.asin ?? `deal #${current.dealId}`}</> : null}
            : pick a reason (Escape to cancel)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {REASON_CODES.map((r, i) => (
              <button
                key={r.code}
                type="button"
                disabled={busy}
                onClick={() => submit(pendingVerdict, r.code)}
                className="cursor-pointer rounded border border-line bg-panel px-2 py-1 text-xs text-ink transition-colors hover:border-accent disabled:opacity-50"
              >
                {i + 1}. {r.label}
              </button>
            ))}
            <button
              type="button"
              disabled={busy}
              onClick={() => setPendingVerdict(null)}
              className="cursor-pointer rounded border border-transparent px-2 py-1 text-xs text-faint transition-colors hover:text-ink disabled:opacity-50"
            >
              cancel
            </button>
          </div>
          {busy ? <p className="mt-2 text-[11px] text-faint">Recording…</p> : null}
        </div>
      ) : null}

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
    </div>
  );
}

// A single labeled number — "Profit $4.20/u" instead of a bare, ambiguous "$4.20" (Sourcing
// plan finding: the old card showed profit unlabeled, which read as if it were the sell price).
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined) return null;
  return (
    <span className="text-xs text-muted">
      <span className="text-faint">{label}</span> <span className="num text-ink">{value}</span>
    </span>
  );
}

function QueueCard({ item, active, onClick }: { item: QueueItem; active: boolean; onClick: () => void }) {
  const summary = item.kind === "lead" ? explainSummary(item.explanation) : null;
  const asin = item.asin;

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "surface flex w-full cursor-pointer flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors",
        active ? "border-accent" : "border-line hover:border-line2",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Badge tone={item.kind === "lead" ? "accent" : "info"}>{item.kind === "lead" ? "scout lead" : "deal match"}</Badge>
          {item.kind === "lead" && item.buyCost === null ? (
            <Badge tone="warn">estimated — no source yet</Badge>
          ) : null}
        </div>
        <span className="num text-[11px] text-faint">priority {item.priority.toFixed(2)} · seen {ago(item.createdAt)}</span>
      </div>

      {item.kind === "lead" ? (
        <>
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="block truncate text-sm text-ink">{item.title ?? item.asin ?? `lead #${item.id}`}</span>
              <span className="num text-xs text-muted">
                {item.asin ?? "no ASIN"} · {item.brand ?? "no brand"} {item.category ? `· ${item.category}` : ""}
              </span>
            </div>
            {asin ? (
              <a
                href={`https://www.amazon.com/dp/${asin}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-[11px] text-faint underline decoration-dotted hover:text-accent"
              >
                view on Amazon
              </a>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Stat label="Sell" value={item.sellPrice !== null ? money(item.sellPrice) : null} />
            <Stat label="Buy" value={item.buyCost !== null ? money(item.buyCost) : "— (estimated)"} />
            <Stat label="Profit" value={item.profit !== null ? `${money(item.profit)}/u` : null} />
            <Stat label="ROI" value={item.roi !== null ? pct(item.roi) : null} />
            <Stat label="BSR" value={item.bsr !== null ? bsrFmt(item.bsr) : null} />
            <Stat label="Sales/mo" value={item.monthlySales !== null ? num(item.monthlySales) : null} />
            <Stat label="Offers" value={item.offerCount !== null ? num(item.offerCount) : null} />
            {item.amazonPresent !== null ? (
              <span className="text-xs text-muted">
                <span className="text-faint">Amazon on listing</span>{" "}
                <span className={cn("num", item.amazonPresent ? "text-loss" : "text-profit")}>{item.amazonPresent ? "yes" : "no"}</span>
              </span>
            ) : null}
          </div>
          {summary ? <p className="text-xs text-faint">{summary}</p> : null}
        </>
      ) : (
        <>
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="block truncate text-sm text-ink">{item.asin ?? `deal #${item.dealId}`}</span>
              <span className="num text-xs text-muted">
                deal #{item.dealId} · method: {item.method ?? "unknown"} {item.packMatch === false ? "· pack mismatch risk" : ""}
              </span>
            </div>
            {asin ? (
              <a
                href={`https://www.amazon.com/dp/${asin}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="shrink-0 text-[11px] text-faint underline decoration-dotted hover:text-accent"
              >
                view on Amazon
              </a>
            ) : null}
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
    </div>
  );
}
