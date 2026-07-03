"use client";

import * as React from "react";
import { CheckCircle2, Eye, EyeOff, Loader2, Save, Trash2, XCircle, Zap } from "lucide-react";
import { KEY_REGISTRY, type KeyEntry } from "@/lib/keys";
import { cn } from "@/lib/cn";

type Status = { id: string; fieldsSet: Record<string, boolean> };
type Msg = { tone: "ok" | "err"; text: string };

const GROUPS = ["Sourcing", "Discord routing", "Knowledge", "Amazon", "Ops"] as const;

export function KeyManager() {
  const [statuses, setStatuses] = React.useState<Record<string, Status>>({});
  const [loaded, setLoaded] = React.useState(false);
  const [ready, setReady] = React.useState(true);
  // entryId -> fieldId -> what the operator has typed THIS session (never persisted anywhere
  // except via an explicit Save click — not localStorage, not auto-saved on change).
  const [values, setValues] = React.useState<Record<string, Record<string, string>>>({});
  const [reveal, setReveal] = React.useState<Record<string, boolean>>({});
  const [busy, setBusy] = React.useState<Record<string, "save" | "clear" | "test" | "">>({});
  const [msg, setMsg] = React.useState<Record<string, Msg | undefined>>({});

  const refresh = React.useCallback(async () => {
    try {
      const res = await fetch("/api/settings/keys");
      const data = await res.json();
      setReady(Boolean(data.ready));
      const map: Record<string, Status> = {};
      for (const s of (data.keys ?? []) as Status[]) map[s.id] = s;
      setStatuses(map);
    } catch {
      // Honest degrade: leave statuses empty rather than fake a "not set" or "set" guess.
    } finally {
      setLoaded(true);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const setField = (entryId: string, fieldId: string, v: string) =>
    setValues((cur) => ({ ...cur, [entryId]: { ...cur[entryId], [fieldId]: v } }));

  async function run(entry: KeyEntry, action: "save" | "clear" | "test") {
    if (action === "clear" && !window.confirm(`Clear the saved ${entry.label} key(s)? This can't be undone from here.`)) {
      return;
    }
    setBusy((b) => ({ ...b, [entry.id]: action }));
    setMsg((m) => ({ ...m, [entry.id]: undefined }));

    // For "save": only send fields the operator actually typed something into — an
    // untouched/blank field must NEVER overwrite an already-saved real secret with "".
    // For "test": send whatever's typed (empty is fine — the route falls back to the saved
    // value on the server side, which it never returns to us).
    const raw = values[entry.id] ?? {};
    const payloadValues =
      action === "save"
        ? Object.fromEntries(Object.entries(raw).filter(([, v]) => v.trim() !== ""))
        : raw;

    try {
      const res = await fetch("/api/settings/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, id: entry.id, values: payloadValues }),
      });
      const data = await res.json();
      if (action === "test") {
        setMsg((m) => ({ ...m, [entry.id]: { tone: data.ok ? "ok" : "err", text: data.detail ?? "No result." } }));
      } else if (!res.ok || data.error) {
        setMsg((m) => ({ ...m, [entry.id]: { tone: "err", text: data.error ?? "Something went wrong." } }));
      } else {
        setMsg((m) => ({ ...m, [entry.id]: { tone: "ok", text: action === "save" ? "Saved." : "Cleared." } }));
        setValues((v) => ({ ...v, [entry.id]: {} }));
        await refresh();
      }
    } catch {
      setMsg((m) => ({ ...m, [entry.id]: { tone: "err", text: "Network error — is the dev server running locally?" } }));
    } finally {
      setBusy((b) => ({ ...b, [entry.id]: "" }));
    }
  }

  if (!loaded) return <div className="text-[12px] text-muted">Loading key status…</div>;
  if (!ready) {
    return (
      <div className="text-[12px] text-warn">
        Key management is local-operator-only — this environment doesn&apos;t have the sibling scout/knowledge-rag folders.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {GROUPS.map((group) => {
        const entries = KEY_REGISTRY.filter((e) => e.group === group);
        if (!entries.length) return null;
        return (
          <div key={group}>
            <div className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-faint">{group}</div>
            <div className="flex flex-col gap-2">
              {entries.map((entry) => {
                const status = statuses[entry.id];
                const allSet = entry.fields.every((f) => status?.fieldsSet?.[f.id]);
                const anySet = entry.fields.some((f) => status?.fieldsSet?.[f.id]);
                const entryBusy = busy[entry.id] ?? "";
                const entryMsg = msg[entry.id];
                return (
                  <div key={entry.id} className="surface p-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-semibold text-ink">{entry.label}</span>
                      <span
                        className={cn(
                          "border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em]",
                          allSet ? "border-profit/40 text-profit" : anySet ? "border-warn/40 text-warn" : "border-line2 text-muted",
                        )}
                      >
                        {allSet ? "set" : anySet ? "partially set" : "not set"}
                      </span>
                    </div>
                    <p className="mb-2.5 text-[11px] leading-relaxed text-muted">{entry.hint}</p>

                    <div className="flex flex-col gap-2">
                      {entry.fields.map((field) => {
                        const revealKey = `${entry.id}:${field.id}`;
                        const revealed = reveal[revealKey];
                        const typed = values[entry.id]?.[field.id] ?? "";
                        const fieldSet = status?.fieldsSet?.[field.id];
                        return (
                          <label key={field.id} className="block">
                            <span className="mb-1 block text-[11px] text-muted">{field.label}</span>
                            <span className="relative block">
                              <input
                                className={cn("field", field.secret && "pr-9")}
                                type={!field.secret || revealed ? "text" : "password"}
                                value={typed}
                                onChange={(e) => setField(entry.id, field.id, e.target.value)}
                                placeholder={fieldSet ? "already set — leave blank to keep" : field.placeholder}
                                autoComplete="off"
                              />
                              {field.secret ? (
                                <button
                                  type="button"
                                  onClick={() => setReveal((r) => ({ ...r, [revealKey]: !r[revealKey] }))}
                                  className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer text-faint hover:text-ink"
                                  aria-label={revealed ? "Hide value" : "Show value"}
                                >
                                  {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
                                </button>
                              ) : null}
                            </span>
                          </label>
                        );
                      })}
                    </div>

                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={entryBusy !== ""}
                        onClick={() => run(entry, "save")}
                        className="inline-flex cursor-pointer items-center gap-1.5 bg-accent px-3 py-1.5 text-[11px] font-bold text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {entryBusy === "save" ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                        Save
                      </button>
                      {entry.testProvider ? (
                        <button
                          type="button"
                          disabled={entryBusy !== ""}
                          onClick={() => run(entry, "test")}
                          className="inline-flex cursor-pointer items-center gap-1.5 border border-line2 px-3 py-1.5 text-[11px] font-bold text-muted transition-colors hover:border-accent/50 hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {entryBusy === "test" ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
                          Test connection
                        </button>
                      ) : null}
                      {anySet ? (
                        <button
                          type="button"
                          disabled={entryBusy !== ""}
                          onClick={() => run(entry, "clear")}
                          className="inline-flex cursor-pointer items-center gap-1.5 border border-line2 px-3 py-1.5 text-[11px] font-bold text-muted transition-colors hover:border-loss/50 hover:text-loss disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <Trash2 size={12} />
                          Clear
                        </button>
                      ) : null}
                      {entryMsg ? (
                        <span className={cn("flex items-center gap-1.5 text-[11px]", entryMsg.tone === "ok" ? "text-profit" : "text-loss")}>
                          {entryMsg.tone === "ok" ? <CheckCircle2 size={12} className="shrink-0" /> : <XCircle size={12} className="shrink-0" />}
                          {entryMsg.text}
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
