import {
  Activity,
  BatteryCharging,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  Database,
  Gauge,
  GitCompareArrows,
  LineChart,
  ListChecks,
  PackageSearch,
  ShieldCheck,
  TriangleAlert,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { getBrain, getPicks, getMoney, getInventory, getEvents } from "@/lib/data";
import { ActionLink, Badge, EmptyState, PageHeader, Panel } from "@/components/ui";
import { buildIntelligenceData } from "@/lib/intelligence-server";
import {
  BacktestGrowthChart,
  CompositionBar,
  IndependentSampleTrendChart,
  RankerAccuracyChart,
  RunTokensChart,
} from "@/components/scout-charts";
import type { DiversitySummary } from "@/lib/intelligence-server";
import { num } from "@/lib/format";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

const LOOP = [
  ["Ingest", "Keepa snapshots, account data, documents, and analyst feedback"],
  ["Gate", "Eligibility, IP, margin, Amazon Buy Box, restrictions, and data quality"],
  ["Score", "Transparent rule score blended with a calibrated model when enough labels exist"],
  ["Review", "Ambiguous or high-risk candidates route to a human queue"],
  ["Observe", "Realized margin, sell-through, returns, Buy Box share, and price movement"],
  ["Promote", "A challenger replaces the champion only after measurable offline improvement"],
];

function decimal(value: number, digits = 1): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function dimensionLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  state = "measured",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  state?: "measured" | "unavailable";
}) {
  return (
    <div className="surface min-w-0 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-panel2 text-accent">
          <Icon size={15} aria-hidden />
        </span>
        <Badge tone={state === "measured" ? "success" : "warn"}>
          {state === "measured" ? "measured" : "unavailable"}
        </Badge>
      </div>
      <div className="mt-4 text-[10px] font-semibold uppercase tracking-[0.15em] text-faint">{label}</div>
      <div className="num mt-1 break-words text-2xl font-semibold text-ink">{value}</div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted">{detail}</p>
    </div>
  );
}

function DiversityList({ summary, noun }: { summary: DiversitySummary; noun: string }) {
  const total = summary.knownAsins + summary.unknownAsins;
  const shown = summary.buckets.slice(0, 6);
  const shownCount = shown.reduce((sum, bucket) => sum + bucket.count, 0);
  const otherKnown = Math.max(0, summary.knownAsins - shownCount);
  return (
    <div className="flex flex-col gap-3">
      {shown.length ? (
        <ol className="flex flex-col gap-2" aria-label={`Top ${noun} by unique ASIN count`}>
          {shown.map((bucket) => (
            <li key={bucket.label}>
              <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                <span className="truncate text-muted">{dimensionLabel(bucket.label)}</span>
                <span className="num shrink-0 text-ink">
                  {num(bucket.count)} <span className="text-faint">({Math.round(bucket.share * 100)}%)</span>
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-sm bg-panel2" aria-hidden>
                <div
                  className="h-full bg-accent"
                  style={{ width: `${Math.max(1, bucket.share * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState title={`No known ${noun} yet`} hint="Unknown values are not counted as diversity." />
      )}
      <p className="text-[11px] leading-relaxed text-faint">
        {num(summary.distinctKnown)} known {noun} across {num(summary.knownAsins)} of {num(total)} unique ASINs
        {otherKnown ? ` · ${num(otherKnown)} ASINs in ${num(summary.distinctKnown - shown.length)} other ${noun}` : ""}
        {summary.unknownAsins ? ` · ${num(summary.unknownAsins)} unknown` : ""}.
      </p>
    </div>
  );
}

export default async function IntelligencePage() {
  const brain = getBrain();
  const picks = getPicks();
  const money = getMoney();
  const inventory = getInventory();
  const intel = await buildIntelligenceData();
  // A large limit, not the feed's default 40 — this needs every outcome ever captured to judge
  // readiness honestly, not just the most recent page of the ledger.
  const outcomeEvents = getEvents(5000).filter((e) => e.kind === "outcome");
  const profits = outcomeEvents
    .map((e) => e.payload.actualProfit)
    .filter((v): v is number => typeof v === "number");
  const goodOutcomes = profits.filter((p) => p > 0).length;
  const badOutcomes = profits.filter((p) => p <= 0).length;
  const rag = brain.knowledge.ragCorpus;
  // Code Review 2026-07-02, Finding CS3: these three rows used to be hardcoded `state: false`
  // literally — permanently "blocked" no matter what real data existed, the opposite failure
  // mode of a fabricated "live" claim but still dishonest. Now derived from the real capture
  // ledger and account-connection signals, matching how the rest of the dashboard reports state.
  const readiness = [
    { label: "Knowledge retrieval", state: Boolean(rag?.chunks), detail: `${rag?.documents ?? 0} docs · ${rag?.chunks ?? 0} chunks`, icon: Database },
    { label: "Transparent OA gates", state: true, detail: "Criteria + spike/offers/Amazon-share guards", icon: ShieldCheck },
    { label: "Live Keepa ingestion", state: picks.connected, detail: picks.connected ? "scout is receiving data" : "paid Keepa key not configured", icon: Activity },
    { label: "Realized outcome labels", state: outcomeEvents.length > 0,
      detail: outcomeEvents.length > 0 ? `${outcomeEvents.length} outcome(s) logged` : "business DB ready; no real outcomes logged yet",
      icon: BrainCircuit },
    { label: "Account eligibility", state: money.connected || inventory.connected,
      detail: money.connected || inventory.connected ? "account data connected" : "Listings Restrictions SP-API not connected",
      icon: CheckCircle2 },
    { label: "Model promotion evidence", state: goodOutcomes > 0 && badOutcomes > 0,
      detail: goodOutcomes > 0 && badOutcomes > 0
        ? `${goodOutcomes} good, ${badOutcomes} bad realized outcome(s)`
        : "needs both good and bad realized labels",
      icon: GitCompareArrows },
  ];

  const sevenDayTrendDetail = intel.connected
    ? intel.sevenDayTrend === null
      ? "No prior complete seven-day baseline yet"
      : `${intel.sevenDayTrend >= 0 ? "+" : ""}${Math.round(intel.sevenDayTrend * 100)}% vs the prior 7 complete UTC days`
    : "";
  const backlogCategoryDetail = intel.connected && intel.pendingBacklog.available
    ? [
        ...intel.pendingBacklog.byCategory.slice(0, 3).map(
          (bucket) => `${dimensionLabel(bucket.label)} ${num(bucket.count)}`,
        ),
        intel.pendingBacklog.byCategory.length > 3
          ? `+${num(intel.pendingBacklog.byCategory.length - 3)} more categories`
          : null,
        intel.pendingBacklog.unknownCategoryAsins
          ? `Unknown ${num(intel.pendingBacklog.unknownCategoryAsins)}`
          : null,
      ].filter(Boolean).join(" · ") || "Persisted sampler queue is empty"
    : "Backtest state blob could not be read; this is not treated as zero";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Learning and governance"
        title="Scout intelligence"
        description="The scout becomes more useful through better evidence, honest labels, calibration, and gated model promotion—not by silently rewriting its own rules."
        meta={<Badge tone="warn">decision support · not autonomous</Badge>}
      />

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/find" tone="primary">Run the deal analyzer</ActionLink>
        <ActionLink href="/ask">Question the knowledge brain</ActionLink>
      </div>

      {intel.connected ? (
        <Panel
          title="Independent sample velocity"
          icon={<PackageSearch size={16} />}
          right="unique ASINs · UTC"
        >
          <p className="mb-4 max-w-4xl text-xs leading-relaxed text-muted">
            One independent sample here means one distinct ASIN at its first observed collection time.
            Repeated historical windows for that ASIN remain useful labels, but do not count as new products.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <MetricCard
              icon={Database}
              label="Unique ASINs"
              value={num(intel.totalUniqueAsins)}
              detail={`${num(intel.totalBacktestRows)} labeled rows · ${intel.averageRowsPerAsin === null ? "—" : decimal(intel.averageRowsPerAsin, 1)} rows per ASIN`}
            />
            <MetricCard
              icon={CalendarDays}
              label="New today"
              value={num(intel.newAsinsToday)}
              detail={`First seen since 00:00 UTC · ${num(intel.newAsinsLast24h)} in the rolling 24-hour window`}
            />
            <MetricCard
              icon={Activity}
              label="7-day average"
              value={`${decimal(intel.newAsins7DayAverage, 1)}/day`}
              detail={sevenDayTrendDetail}
            />
            <MetricCard
              icon={Zap}
              label="New ASINs / tier-3 token"
              value={intel.tier3Efficiency24h.asinsPerToken === null
                ? "Unavailable"
                : decimal(intel.tier3Efficiency24h.asinsPerToken, 2)}
              detail={intel.tier3Efficiency24h.asinsPerToken === null
                ? (intel.tier3Efficiency24h.reason ?? "No measurable rolling-window efficiency")
                : `${num(intel.tier3Efficiency24h.newAsins)} new ASINs / ${num(intel.tier3Efficiency24h.tier3Tokens)} history tokens · rolling 24h`}
              state={intel.tier3Efficiency24h.asinsPerToken === null ? "unavailable" : "measured"}
            />
            <MetricCard
              icon={BatteryCharging}
              label="Collector token capture"
              value={intel.tokenCapture24h.utilization === null
                ? "Unavailable"
                : `${Math.round(intel.tokenCapture24h.utilization * 100)}%`}
              detail={intel.tokenCapture24h.utilization === null
                ? (intel.tokenCapture24h.reason ?? "No measurable rolling-window utilization")
                : `${num(intel.tokenCapture24h.spentTokens)} spent / ${num(intel.tokenCapture24h.generatedTokens)} generated at ${decimal(intel.tokenCapture24h.refillRatePerMinute ?? 0, 2)} token/min · ${num(intel.tokenCapture24h.completedRuns)} completed runs`}
              state={intel.tokenCapture24h.utilization === null ? "unavailable" : "measured"}
            />
            <MetricCard
              icon={ListChecks}
              label="Pending sampler backlog"
              value={intel.pendingBacklog.available ? num(intel.pendingBacklog.pendingAsins) : "Unavailable"}
              detail={backlogCategoryDetail}
              state={intel.pendingBacklog.available ? "measured" : "unavailable"}
            />
          </div>
          <div className="mt-5 border-t border-line pt-4">
            <IndependentSampleTrendChart data={intel.dailyAsinTrend} />
            <p className="mt-1.5 text-[11px] text-faint">
              Bars are first-seen unique ASINs by UTC day. Today is partial; the headline 7-day average uses
              seven complete days and excludes today.
            </p>
          </div>
        </Panel>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {readiness.map(({ label, state, detail, icon: Icon }) => (
          <div key={label} className="surface rounded-xl p-4">
            <div className="flex items-start justify-between gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-panel2 text-accent"><Icon size={17} /></span><Badge tone={state ? "success" : "warn"}>{state ? "ready" : "blocked"}</Badge></div>
            <h2 className="mt-4 text-sm font-semibold text-ink">{label}</h2>
            <p className="mt-1 text-xs leading-relaxed text-muted">{detail}</p>
          </div>
        ))}
      </section>

      <Panel title="Evidence flywheel" icon={<Gauge size={16} />} right="measured improvement only">
        <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {LOOP.map(([title, detail], index) => (
            <li key={title} className="rounded-xl border border-line bg-bg/40 p-4">
              <div className="num text-[10px] uppercase tracking-[0.16em] text-accent">0{index + 1}</div>
              <h3 className="mt-2 text-sm font-semibold text-ink">{title}</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{detail}</p>
            </li>
          ))}
        </ol>
      </Panel>

      {!intel.connected ? (
        <Panel title="Training & collection" icon={<LineChart size={16} />} right="live">
          <EmptyState
            title="Supabase not configured"
            hint="Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in control-center/.env.local to see collection/training charts."
          />
        </Panel>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel
              title="Labeled backtest rows"
              icon={<Database size={16} />}
              right={`${num(intel.totalBacktestRows)} total`}
            >
              <BacktestGrowthChart data={intel.backtestGrowth} />
            </Panel>
            <Panel
              title="Ranker accuracy over time"
              icon={<LineChart size={16} />}
              right="AUC, held-out"
            >
              <RankerAccuracyChart data={intel.rankerHistory} />
            </Panel>
          </div>

          <Panel title="Collector token spend by tier" icon={<Activity size={16} />} right="hourly runs">
            <RunTokensChart data={intel.runHistory} tierBreakdownAvailableSince={intel.tierBreakdownAvailableSince} />
          </Panel>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <Panel
              title="Category diversity"
              icon={<Database size={16} />}
              right={`${num(intel.categoryDiversity.distinctKnown)} known`}
            >
              <DiversityList summary={intel.categoryDiversity} noun="categories" />
            </Panel>
            <Panel
              title="Sampling-source diversity"
              icon={<PackageSearch size={16} />}
              right={`${num(intel.sourceDiversity.distinctKnown)} known`}
            >
              <DiversityList summary={intel.sourceDiversity} noun="sources" />
              {intel.sourceDiversity.unknownAsins ? (
                <p className="mt-2 text-[11px] text-faint">
                  Unknown means no durable source tag exists for that ASIN, commonly because its rows predate
                  sample_source tracking. It is not reassigned by guesswork.
                </p>
              ) : null}
            </Panel>
            <Panel title="Sampling composition · labeled rows" icon={<Database size={16} />} right="dealfeed / explore / onpolicy">
              <CompositionBar
                emptyHint="Fills in once sample_source is populated (migration 011, 2026-07-09)."
                segments={[
                  { label: "dealfeed", value: intel.sampleComposition.dealfeed, color: "var(--accent)" },
                  { label: "explore", value: intel.sampleComposition.explore, color: "var(--info)" },
                  { label: "onpolicy", value: intel.sampleComposition.onpolicy, color: "var(--profit)" },
                  { label: "unknown (pre-migration)", value: intel.sampleComposition.unknown, color: "var(--text-faint)" },
                ]}
              />
              {!intel.sampleSourceAvailableSince ? (
                <p className="mt-2 text-[11px] text-faint">
                  Every row so far predates sample_source tracking — this breaks out starting with the next
                  dealfeed/explore/onpolicy sample.
                </p>
              ) : null}
            </Panel>
            <Panel title="Backtest label outcome" icon={<GitCompareArrows size={16} />} right="would-have-profited">
              <CompositionBar
                segments={[
                  { label: "profitable", value: intel.labelComposition.profitable, color: "var(--profit)" },
                  { label: "not profitable", value: intel.labelComposition.notProfitable, color: "var(--loss)" },
                  { label: "unknown", value: intel.labelComposition.unknown, color: "var(--text-faint)" },
                ]}
              />
            </Panel>
          </div>
        </>
      )}

      <Panel title="Accuracy guardrails" icon={<TriangleAlert size={16} />} right="non-negotiable">
        <div className="grid gap-3 md:grid-cols-2">
          {[
            ["No total-accuracy claim", "Marketplace data, fees, policies, and account eligibility change. Confidence must be calibrated and manual checks surfaced."],
            ["Strong labels beat proxies", "Actual margin, units, returns, and sell-through outrank public Keepa-derived weak labels."],
            ["Prevent leakage", "Only pre-decision features may train a sourcing model; post-purchase performance belongs in the label."],
            ["Keep hard gates outside ML", "Compliance, account eligibility, margin floors, and disallowed risk cannot be overridden by a high model score."],
          ].map(([title, detail]) => (
            <div key={title} className="rounded-lg border border-line bg-panel2/35 p-4"><h3 className="text-sm font-semibold text-ink">{title}</h3><p className="mt-1.5 text-xs leading-relaxed text-muted">{detail}</p></div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
