import { ListChecks, Radar } from "lucide-react";
import { getLeads } from "@/lib/data";
import { getSupabaseLeads, supabaseConfigured } from "@/lib/supabase-server";
import { explainSummary } from "@/lib/explain";
import { pct, money, ago } from "@/lib/format";
import { Panel, Pill, Badge, EmptyState, DataNote, ActionLink } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default async function LeadsPage() {
  const leads = getLeads();
  const hasPipeline = Object.values(leads.pipeline).some((v) => v > 0);
  const scoutConnected = supabaseConfigured();
  // Three honest states, same as the Today page's runs panel: not configured / configured but
  // the fetch failed / configured and genuinely empty. Collapsing a failed fetch into "no
  // scout leads yet" would be a fabricated empty state (Code Review 2026-07-03, Finding #9).
  const scoutLeadsResult = scoutConnected ? await getSupabaseLeads(100) : null;
  const scoutLeads = scoutLeadsResult ?? [];
  const scoutFetchFailed = scoutConnected && scoutLeadsResult === null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Leads</h1>
        <DataNote source={leads.source} updated={leads.updated} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/find" tone="primary">Analyze a product</ActionLink>
        <ActionLink href="https://sellercentral.amazon.com/product-search" external>Check listing eligibility</ActionLink>
      </div>

      <Panel title="Pipeline" icon={<ListChecks size={16} />}>
        {hasPipeline ? (
          <div className="flex flex-wrap gap-2">
            {Object.entries(leads.pipeline).map(([k, v]) => (
              <Pill key={k} label={k} value={v} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<ListChecks size={20} />}
            title="Pipeline is empty"
            hint="Add a product idea or approve a scout pick — it moves idea → research → buy → ordered → sold."
          />
        )}
      </Panel>

      <Panel
        title="Scout leads"
        icon={<Radar size={16} />}
        right={<Badge tone={scoutConnected ? "success" : "warn"}>{scoutConnected ? "Supabase" : "not connected"}</Badge>}
      >
        {!scoutConnected ? (
          <EmptyState
            title="Supabase not configured"
            hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in control-center/.env.local to see the scout's own leads here."
          />
        ) : scoutFetchFailed ? (
          <EmptyState
            title="Could not reach Supabase"
            hint="Supabase is configured but the fetch failed — this is a connection problem, not an empty leads table. Check the network / Supabase status and reload."
          />
        ) : scoutLeads.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {scoutLeads.map((l) => {
              const summary = explainSummary(l.explanation);
              return (
              <li key={l.id} className="flex flex-col gap-1 py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="block truncate text-ink">{l.title ?? l.asin ?? `lead #${l.id}`}</span>
                    <span className="num text-xs text-muted">
                      {l.asin} · {l.brand ?? "no brand"} · {ago(l.created_at)}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {l.roi !== null ? <span className="num text-xs text-muted">{pct(l.roi)} ROI</span> : null}
                    {l.profit !== null ? <span className="num text-xs text-muted">{money(l.profit)}/u</span> : null}
                    <Badge tone={l.verdict === "review" ? "warn" : "muted"}>{l.verdict ?? "?"}</Badge>
                  </div>
                </div>
                {summary ? <p className="text-xs text-faint">{summary}</p> : null}
              </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState title="No scout leads yet" hint="run_daily.py writes every scored candidate here once the scout has run at least once." />
        )}
      </Panel>

      <Panel title="Manual leads (local ledger)">
        {leads.leads.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {leads.leads.map((l, i) => (
              <li key={i} className="flex flex-col gap-1 py-2.5">
                <span className="block truncate">{l.product}</span>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  {l.asin ? <span className="num text-xs text-muted">{l.asin}</span> : null}
                  {l.roi !== undefined ? <span className="num text-xs text-muted">{pct(l.roi)} ROI</span> : null}
                  <span className="num text-xs text-muted">{l.status}</span>
                </div>
                {l.notes ? <p className="text-xs text-faint">{l.notes}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No leads tracked yet" />
        )}
      </Panel>
    </div>
  );
}
