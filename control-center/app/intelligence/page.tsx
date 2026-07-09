import { Activity, BrainCircuit, CheckCircle2, Database, Gauge, GitCompareArrows, LineChart, ShieldCheck, TriangleAlert } from "lucide-react";
import { getBrain, getPicks, getMoney, getInventory, getEvents } from "@/lib/data";
import { ActionLink, Badge, EmptyState, PageHeader, Panel } from "@/components/ui";
import { buildIntelligenceData } from "@/lib/intelligence-server";
import { BacktestGrowthChart, CompositionBar, RankerAccuracyChart, RunTokensChart } from "@/components/scout-charts";
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
              title="Backtest rows collected"
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

          <div className="grid gap-3 md:grid-cols-2">
            <Panel title="Sampling composition" icon={<Database size={16} />} right="dealfeed / explore / onpolicy">
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
