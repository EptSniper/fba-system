import { Activity } from "lucide-react";
import { Panel, Badge, EmptyState } from "@/components/ui";
import { num, ago } from "@/lib/format";
import type { SupabaseRun } from "@/lib/supabase-server";
import { WorkflowTriggers } from "@/components/workflow-trigger";

// CC1's Runs health panel — the observability collect_hourly.py already writes to Supabase's
// `runs` table (System Blueprint Prompt G1/G2) but nothing in the UI showed it before this.
// "connected: false" means Supabase isn't configured at all (honest "not connected", not a
// fabricated empty run history); "connected: true, runs: []" means it IS configured but the
// hourly collector has genuinely never run yet — both are real, distinct states. `runs` is
// expected to already be filtered to the real collector (lib/supabase-server.ts's
// getCollectorRuns) — Review fix (2026-07-09): this panel used to take ANY runs row, including
// frequent local housekeeping ticks (run_daily.py) that fire far more often than the hourly
// collector and could show a confusing "SKIPPED, 0/0/0/-" right after a real, successful run.
export function RunsHealth({
  connected,
  fetchFailed,
  runs,
  searchesDue,
}: {
  connected: boolean;
  fetchFailed?: boolean;
  runs: SupabaseRun[];
  // Brands due a re-mining run (CC1 item 2's "searches due"); null = couldn't be read —
  // rendered as "—", never as a fake 0.
  searchesDue?: number | null;
}) {
  const latest = runs[0];
  const toneFor = (status: string) => (status === "success" ? "success" : status === "failed" ? "loss" : "warn");

  return (
    <Panel title="Runs health" icon={<Activity size={13} />} right={connected ? "Supabase" : "not connected"}>
      {!connected ? (
        <EmptyState
          title="Supabase not configured"
          hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in control-center/.env.local to see real run history here."
        />
      ) : fetchFailed ? (
        <EmptyState title="Could not reach Supabase" hint="The credentials are set, but the request failed — check the server log for the real error." />
      ) : !latest ? (
        <EmptyState title="No collector runs recorded yet" hint="keepa-collect.yml writes a runs row every hourly cycle — this fills in once it has run at least once." />
      ) : (
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[12px] text-muted">Last run</span>
            <span className="flex items-center gap-2">
              <span className="num text-[12px] text-ink">{ago(latest.started_at)}</span>
              <Badge tone={toneFor(latest.status)}>{latest.status}</Badge>
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-5">
            <div>
              <div className="text-faint">Scanned</div>
              <div className="num text-ink">{num(latest.asins_scanned)}</div>
            </div>
            <div>
              <div className="text-faint">Gated</div>
              <div className="num text-ink">{num(latest.candidates_gated)}</div>
            </div>
            <div>
              <div className="text-faint">Leads written</div>
              <div className="num text-ink">{num(latest.leads_upserted)}</div>
            </div>
            <div>
              <div className="text-faint">Tokens left</div>
              <div className="num text-ink">{latest.tokens_left_end === null ? "—" : num(latest.tokens_left_end)}</div>
            </div>
            <div>
              <div className="text-faint">Searches due</div>
              <div className="num text-ink">{searchesDue == null ? "—" : num(searchesDue)}</div>
            </div>
          </div>
          {latest.error_summary ? (
            <p className="rounded border border-loss/25 bg-loss/5 px-2 py-1.5 text-[11px] text-loss">{latest.error_summary}</p>
          ) : null}
        </div>
      )}
      {connected ? <WorkflowTriggers /> : null}
    </Panel>
  );
}
