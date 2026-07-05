import Link from "next/link";
import { CalendarClock, ClipboardCheck, Compass, ListTodo, LineChart } from "lucide-react";
import { getBrain } from "@/lib/data";
import {
  getDealHints,
  getRecentRuns,
  getSearchLogRows,
  searchesDueCount,
  supabaseConfigured,
} from "@/lib/supabase-server";
import { buildQueue } from "@/lib/queue-server";
import { explainSummary } from "@/lib/explain";
import { computeSeasonalChips } from "@/lib/seasonal";
import { parseProposals, pendingCount } from "@/lib/proposals";
import { readAllDecisionEvents, statusMap } from "@/lib/proposal-drafts";
import { parseHumanTodoItems, unchecked } from "@/lib/human-todo";
import { latestReportBlock } from "@/lib/reports";
import { hubTrackingPath, projectRootPath, readTextFile } from "@/lib/events-server";
import { RunsHealth } from "@/components/runs-health";
import { Badge, EmptyState, PageHeader, Panel } from "@/components/ui";
import { money, pct } from "@/lib/format";

// Reads live sibling learning-hub/ + HUMAN_TODO.md files and Supabase on every request (Code
// Review 2026-07-02, Finding CS8's convention).
export const dynamic = "force-dynamic";

const chipTone: Record<string, "info" | "warn" | "loss"> = { info: "info", warn: "warn", danger: "loss" };

export default async function BriefPage() {
  const brain = getBrain();
  const runsConfigured = supabaseConfigured();

  const [runsResult, searchLogResult, queue, hintsResult] = runsConfigured
    ? await Promise.all([getRecentRuns(14), getSearchLogRows(), buildQueue(), getDealHints(50)])
    : [null, null, { connected: false, items: [] as Awaited<ReturnType<typeof buildQueue>>["items"] }, null];

  const runs = runsResult ?? [];
  const runsFetchFailed = runsConfigured && runsResult === null;
  const searchesDue = searchLogResult === null ? null : searchesDueCount(searchLogResult);
  // Fresh deal-watch hints steering the scout's discovery (TOP100_DEAL_WATCH_PLAN.md T3).
  const freshHints = hintsResult ?? [];

  const topCandidates = queue.items
    .filter((it) => it.kind === "lead")
    .slice(0, 5) as Extract<(typeof queue.items)[number], { kind: "lead" }>[];

  const seasonalChips = computeSeasonalChips(brain.operations?.seasonal2026 ?? {}, new Date());

  const proposalsMd = readTextFile(hubTrackingPath("brain-proposals.md"));
  const proposalsPending =
    proposalsMd === null ? null : pendingCount(parseProposals(proposalsMd), statusMap(readAllDecisionEvents()));

  const humanTodoMd = readTextFile(projectRootPath("HUMAN_TODO.md"));
  const humanTodoItems = humanTodoMd === null ? null : unchecked(parseHumanTodoItems(humanTodoMd));

  const opsReportMd = readTextFile(hubTrackingPath("ops-report.md"));
  const weeklyReviewMd = readTextFile(hubTrackingPath("weekly-reviews.md"));
  const opsBlock = opsReportMd ? latestReportBlock(opsReportMd) : null;
  const weeklyBlock = weeklyReviewMd ? latestReportBlock(weeklyReviewMd) : null;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Command"
        title="Morning Brief"
        description="Everything to start the day with: last run, today's top candidates, seasonal timing, and what's still waiting on you."
      />

      {seasonalChips.length ? (
        <div className="flex flex-wrap gap-2">
          {seasonalChips.map((c) => (
            <Badge key={c.key} tone={chipTone[c.tone]}>{c.label}</Badge>
          ))}
        </div>
      ) : null}

      <RunsHealth connected={runsConfigured} fetchFailed={runsFetchFailed} runs={runs} searchesDue={searchesDue} />

      {freshHints.length ? (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
          <Compass size={12} aria-hidden className="text-accent" />
          <span className="text-ink">Deal-led discovery:</span> the scout is steering toward{" "}
          {freshHints.slice(0, 6).map((h) => h.brand).filter(Boolean).join(", ")}
          {freshHints.length > 6 ? ` +${freshHints.length - 6} more` : ""} (fresh deal-watch hints).
          <Link href="/deals" className="text-accent hover:underline">Deals →</Link>
        </p>
      ) : null}

      <Panel title="Today's top candidates" icon={<ClipboardCheck size={13} />} right={`triage-ordered, ${queue.items.length} in queue`}>
        {!runsConfigured ? (
          <EmptyState title="Supabase not configured" hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to see triaged candidates here." />
        ) : !queue.connected ? (
          <EmptyState title="Could not reach Supabase" hint="The Review Queue's data couldn't be loaded — check the server log." />
        ) : !topCandidates.length ? (
          <EmptyState title="Nothing waiting on review" hint="Every scout lead marked 'review' is either decided or the scout hasn't found one yet." />
        ) : (
          <div className="flex flex-col gap-2">
            {topCandidates.map((l) => {
              const summary = explainSummary(l.explanation);
              const analystNote = l.explanation?.analyst_note;
              return (
                <div key={l.id} className="surface flex flex-col gap-1 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="block min-w-0 truncate text-sm text-ink">{l.title ?? l.asin ?? `lead #${l.id}`}</span>
                    {analystNote?.disagrees_with_rules ? <Badge tone="warn">analyst disagrees</Badge> : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span className="num text-muted">{l.asin}</span>
                    {l.profit !== null ? <span className="num text-muted">{money(l.profit)}/u</span> : null}
                    {l.roi !== null ? <span className="num text-muted">{pct(l.roi)} ROI</span> : null}
                  </div>
                  {summary ? <p className="text-xs text-faint">{summary}</p> : null}
                  {analystNote?.narrative ? <p className="text-xs text-faint">Analyst: {analystNote.narrative}</p> : null}
                </div>
              );
            })}
            <Link href="/queue" className="text-xs text-accent hover:underline">Open full Review Queue →</Link>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Panel title="Brain proposals" icon={<ListTodo size={13} />}>
          {proposalsMd === null ? (
            <EmptyState title="Could not read brain-proposals.md" hint="Not available in this deployment, or the file is missing." />
          ) : proposalsPending === 0 ? (
            <EmptyState title="Nothing pending" hint="No brain-proposals.md entries are waiting on a decision." />
          ) : (
            <div className="flex items-center justify-between">
              <span className="text-sm text-ink">{proposalsPending} proposal{proposalsPending === 1 ? "" : "s"} pending review</span>
              <Link href="/proposals" className="text-xs text-accent hover:underline">Review →</Link>
            </div>
          )}
        </Panel>

        <Panel title="HUMAN_TODO.md" icon={<CalendarClock size={13} />}>
          {humanTodoItems === null ? (
            <EmptyState title="Could not read HUMAN_TODO.md" hint="Not available in this deployment, or the file is missing." />
          ) : !humanTodoItems.length ? (
            <EmptyState title="Nothing outstanding" hint="Every HUMAN_TODO.md item is marked done." />
          ) : (
            <ul className="flex flex-col divide-y divide-line text-sm">
              {humanTodoItems.slice(0, 5).map((i) => (
                <li key={i.number} className="py-1.5 text-ink">
                  <span className="num text-faint">{i.number}.</span> {i.title}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Weekly KPIs" icon={<LineChart size={13} />} right={opsBlock ? opsBlock.header : undefined}>
        {!opsBlock && !weeklyBlock ? (
          <EmptyState title="No ops report yet" hint="scout/ops_report.py writes ops-report.md weekly once realized outcomes exist to compute KPIs from." />
        ) : (
          <div className="flex flex-col gap-3 text-sm">
            {opsBlock ? <pre className="whitespace-pre-wrap font-sans text-xs text-muted">{opsBlock.body}</pre> : null}
            {weeklyBlock ? (
              <div className="border-t border-line pt-2">
                <div className="mb-1 text-[10px] uppercase tracking-[0.08em] text-faint">Latest weekly review — {weeklyBlock.header}</div>
                <pre className="whitespace-pre-wrap font-sans text-xs text-muted">{weeklyBlock.body}</pre>
              </div>
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  );
}
