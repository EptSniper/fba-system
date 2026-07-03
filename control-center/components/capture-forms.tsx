"use client";

import * as React from "react";
import { Plus, ScrollText, Check, AlertTriangle, Loader2 } from "lucide-react";
import type { CaptureEvent, CaptureKind } from "@/lib/types";
import { cn } from "@/lib/cn";

const TABS: { kind: CaptureKind; label: string; blurb: string }[] = [
  { kind: "lead", label: "Lead", blurb: "A product you're researching or moving through the pipeline." },
  { kind: "decision", label: "Decision", blurb: "A buy / test / wait / pass call you made — and why." },
  { kind: "inventory", label: "Inventory", blurb: "Units you actually own, at FBA, or in transit." },
  { kind: "outcome", label: "Outcome", blurb: "What really happened — the label the scout learns from." },
];

// Shared field styles — visible focus, smooth transitions, full-contrast text (design-system rules).
const fieldCls =
  "min-h-10 w-full rounded-lg border border-line2 bg-bg/40 px-3 py-2 text-sm text-ink placeholder:text-faint " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {hint ? <span className="text-[11px] text-faint">{hint}</span> : null}
    </label>
  );
}

type FormState = Record<string, string>;

const EMPTY: FormState = {};

export function CaptureForms({ initialEvents }: { initialEvents: CaptureEvent[] }) {
  const [kind, setKind] = React.useState<CaptureKind>("lead");
  const [form, setForm] = React.useState<FormState>(EMPTY);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [events, setEvents] = React.useState<CaptureEvent[]>(initialEvents);

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  function switchTab(k: CaptureKind) {
    setKind(k);
    setForm(EMPTY);
    setMsg(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, ...form }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg({ tone: "err", text: data.error ?? "Something went wrong." });
      } else if (data.warning) {
        // The ledger write succeeded but the aggregate (leads.json/inventory.json) silently
        // couldn't be updated — never show the plain "Saved" success message for that.
        setMsg({ tone: "err", text: data.warning });
        setForm(EMPTY);
        if (data.event) setEvents((prev) => [data.event as CaptureEvent, ...prev].slice(0, 40));
      } else {
        setMsg({ tone: "ok", text: `Saved to the ledger${kind === "outcome" ? " — that's a training label." : "."}` });
        setForm(EMPTY);
        if (data.event) setEvents((prev) => [data.event as CaptureEvent, ...prev].slice(0, 40));
      }
    } catch {
      setMsg({ tone: "err", text: "Network error — is the dev server running locally?" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Tabs */}
      <div className="surface flex flex-wrap gap-1 rounded-xl p-1.5" role="tablist" aria-label="Capture type">
        {TABS.map((t) => {
          const active = t.kind === kind;
          return (
            <button
              key={t.kind}
              role="tab"
              aria-selected={active}
              onClick={() => switchTab(t.kind)}
              className={cn(
                "min-h-9 cursor-pointer rounded-lg px-3.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                active ? "bg-accent text-white" : "text-muted hover:bg-white/[0.05] hover:text-ink",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <form onSubmit={submit} className="surface flex flex-col gap-4 rounded-2xl p-4 sm:p-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Product is required for every kind */}
          <Field label="Product *">
            <input className={fieldCls} value={form.product ?? ""} onChange={set("product")} required maxLength={120} placeholder="e.g. Crayola 64-ct crayons" />
          </Field>
          <Field label="ASIN">
            <input className={fieldCls} value={form.asin ?? ""} onChange={set("asin")} maxLength={20} placeholder="B0XXXXXXXX" />
          </Field>

          {kind === "lead" && (
            <>
              <Field label="Status">
                <select className={fieldCls} value={form.status ?? "idea"} onChange={set("status")}>
                  {["idea", "researching", "buy", "ordered", "sold", "passed"].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </Field>
              <Field label="Est. ROI %">
                <input className={fieldCls} value={form.roi ?? ""} onChange={set("roi")} inputMode="decimal" placeholder="35" />
              </Field>
              <Field label="Source site">
                <input className={fieldCls} value={form.sourceSite ?? ""} onChange={set("sourceSite")} maxLength={80} placeholder="Target, Walmart…" />
              </Field>
            </>
          )}

          {kind === "decision" && (
            <>
              <Field label="Decision *">
                <select className={fieldCls} value={form.decision ?? "wait"} onChange={set("decision")}>
                  {["buy", "test", "wait", "pass"].map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </Field>
              <Field label="Quantity">
                <input className={fieldCls} value={form.qty ?? ""} onChange={set("qty")} inputMode="numeric" placeholder="10" />
              </Field>
            </>
          )}

          {kind === "inventory" && (
            <>
              <Field label="Units owned">
                <input className={fieldCls} value={form.owned ?? ""} onChange={set("owned")} inputMode="numeric" placeholder="0" />
              </Field>
              <Field label="At FBA">
                <input className={fieldCls} value={form.atFba ?? ""} onChange={set("atFba")} inputMode="numeric" placeholder="0" />
              </Field>
              <Field label="In transit">
                <input className={fieldCls} value={form.inTransit ?? ""} onChange={set("inTransit")} inputMode="numeric" placeholder="0" />
              </Field>
              <Field label="Status">
                <input className={fieldCls} value={form.status ?? ""} onChange={set("status")} maxLength={40} placeholder="in stock / low" />
              </Field>
            </>
          )}

          {kind === "outcome" && (
            <>
              <Field label="Bought qty">
                <input className={fieldCls} value={form.boughtQty ?? ""} onChange={set("boughtQty")} inputMode="numeric" placeholder="10" />
              </Field>
              <Field label="Sold qty">
                <input className={fieldCls} value={form.soldQty ?? ""} onChange={set("soldQty")} inputMode="numeric" placeholder="10" />
              </Field>
              <Field label="Actual profit $ (net)">
                <input className={fieldCls} value={form.actualProfit ?? ""} onChange={set("actualProfit")} inputMode="decimal" placeholder="42.50" />
              </Field>
              <Field label="Returns">
                <input className={fieldCls} value={form.returns ?? ""} onChange={set("returns")} inputMode="numeric" placeholder="0" />
              </Field>
            </>
          )}
        </div>

        {(kind === "lead" || kind === "outcome") && (
          <Field label="Notes">
            <textarea className={cn(fieldCls, "min-h-20 py-2")} value={form.notes ?? ""} onChange={set("notes")} maxLength={500} placeholder="Anything worth remembering later…" />
          </Field>
        )}
        {kind === "decision" && (
          <Field label="Rationale">
            <textarea className={cn(fieldCls, "min-h-20 py-2")} value={form.rationale ?? ""} onChange={set("rationale")} maxLength={500} placeholder="Keepa stable, ROI 38%, ungated…" />
          </Field>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex min-h-10 cursor-pointer items-center justify-center gap-2 bg-accent px-4 text-sm font-semibold text-white transition-all duration-200 hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Plus size={15} aria-hidden />}
            {busy ? "Saving…" : "Record"}
          </button>
          {msg ? (
            <span
              role="status"
              className={cn(
                "inline-flex items-center gap-1.5 text-xs font-medium",
                msg.tone === "ok" ? "text-profit" : "text-loss",
              )}
            >
              {msg.tone === "ok" ? <Check size={14} aria-hidden /> : <AlertTriangle size={14} aria-hidden />}
              {msg.text}
            </span>
          ) : null}
        </div>
      </form>

      {/* Recent ledger activity */}
      <section className="surface overflow-hidden rounded-xl">
        <header className="flex items-center gap-2 border-b border-line px-4 py-3.5 text-sm font-medium text-ink sm:px-5">
          <span className="text-accent"><ScrollText size={16} /></span>
          Recent activity
          <span className="num ml-auto text-xs text-faint">append-only ledger</span>
        </header>
        <div className="p-4 sm:p-5">
          {events.length ? (
            <ul className="flex flex-col divide-y divide-line text-sm">
              {events.map((e) => (
                <li key={e.id} className="flex items-start justify-between gap-3 py-2.5">
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate text-ink">
                      <span className="num mr-2 rounded bg-white/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">{e.kind}</span>
                      {String(e.payload.product ?? "")}
                      {e.payload.decision ? ` — ${String(e.payload.decision)}` : ""}
                      {e.payload.status && e.kind === "lead" ? ` — ${String(e.payload.status)}` : ""}
                    </span>
                  </span>
                  <span className="num shrink-0 text-xs text-faint">{e.ts.slice(0, 10)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="flex min-h-32 flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-line2 bg-bg/35 px-5 py-8 text-center">
              <p className="text-sm font-medium text-ink">Ledger is empty</p>
              <p className="text-xs text-muted">Record your first entry above.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
