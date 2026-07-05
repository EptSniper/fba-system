import { Tag, Store, Compass } from "lucide-react";
import { getDeals } from "@/lib/data";
import { getDealHints, supabaseConfigured } from "@/lib/supabase-server";
import { money, pct, ago } from "@/lib/format";
import { Panel, Badge, EmptyState, ConnBadge, DataNote, ActionLink } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default async function DealsPage() {
  const d = getDeals();
  // Fresh deal-watch hints (TOP100_DEAL_WATCH_PLAN.md T3). Three honest states, same as the
  // Leads page: not configured / configured-but-fetch-failed / genuinely empty.
  const hintsConnected = supabaseConfigured();
  const hintsResult = hintsConnected ? await getDealHints(50) : null;
  const hints = hintsResult ?? [];
  const hintsFetchFailed = hintsConnected && hintsResult === null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Deals · always-on sourcing</h1>
        <ConnBadge connected={d.connected} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/find" tone="primary">Analyze a manual deal</ActionLink>
        <ActionLink href="/tools">Open sourcing tools</ActionLink>
      </div>

      <Panel
        title="Deal-led discovery hints"
        icon={<Compass size={16} />}
        right={<Badge tone={hintsConnected ? "success" : "warn"}>{hintsConnected ? "Supabase" : "not connected"}</Badge>}
      >
        <p className="mb-3 text-xs text-faint">
          The nightly Top-100 deal watch derives these; the 7:30 AM scout points Keepa here FIRST.
          Fresh (unexpired) hints only. Avoid-listed brands never appear — signal, never a buy.
        </p>
        {!hintsConnected ? (
          <EmptyState title="Supabase not configured" hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in control-center/.env.local." />
        ) : hintsFetchFailed ? (
          <EmptyState title="Could not reach Supabase" hint="Configured, but the fetch failed — a connection problem, not an empty table." />
        ) : hints.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {hints.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 truncate">
                  <span className="text-ink">{h.brand ?? "?"}</span>
                  {h.store ? <span className="text-muted"> · {h.store}</span> : null}
                  {h.category ? <span className="text-faint"> · {h.category}</span> : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="num text-xs text-faint">seen {ago(h.last_seen)}</span>
                  {h.strength !== null ? <Badge tone="accent">strength {h.strength}</Badge> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Compass size={20} />}
            title="No fresh hints"
            hint="The deal watch hasn't derived any unexpired brand hints yet — the scout runs fully self-directed discovery until it does. Run scout/deals/run_watch.py (or wait for the nightly job)."
          />
        )}
      </Panel>

      <Panel title="The rule" icon={<Tag size={16} />}>
        <p className="text-sm text-muted">{d.principle}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {d.watchedRetailers.map((r) => (
            <span key={r} className="inline-flex items-center gap-1 rounded-md bg-panel2 px-2 py-0.5 text-xs text-muted">
              <Store size={12} aria-hidden /> {r}
            </span>
          ))}
        </div>
      </Panel>

      <Panel
        title="Today's profitable deals"
        right={<DataNote source={d.source} updated={d.updated} />}
      >
        {d.today.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {d.today.map((t, i) => (
              <li key={i} className="flex items-center justify-between py-2.5">
                <span>
                  <span className="text-muted">{t.retailer}</span> · {t.item}
                </span>
                <span className="num flex items-center gap-3">
                  {money(t.dealPrice)} → {money(t.amazonPrice)}
                  {typeof t.roi === "number" ? <Badge tone="success">roi {pct(t.roi)}</Badge> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Tag size={20} />}
            title="No deals tracked yet"
            hint={d.reason ?? (
              // Code Review 2026-07-02, Finding CS4/CS5: this used to point at FMTC/LinkMyDeals,
              // neither of which scout/deals/ actually implements. The real, already-built
              // sources are Slickdeals RSS (no key needed, live now) and Best Buy's Products
              // API (needs BESTBUY_API_KEY — see HUMAN_TODO.md). Matcher (D2)/pipeline wiring
              // (D3) that would surface real matched deals here are still not built.
              "Slickdeals RSS is wired and needs no key; Best Buy needs BESTBUY_API_KEY (see HUMAN_TODO.md). "
              + "Both collect deals today, but the matcher that turns them into Amazon-matched picks isn't built yet — see scout/README.md's Deal Finder section."
            )}
          />
        )}
      </Panel>
    </div>
  );
}
