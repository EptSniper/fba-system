import Link from "next/link";
import { ArrowRight, Database, LineChart, Radar, ShieldCheck, Target } from "lucide-react";
import { getBrain, getDeals, getInventory, getLeads, getMoney, getPicks } from "@/lib/data";
import { getCollectorRuns, getSearchLogRows, searchesDueCount, supabaseConfigured } from "@/lib/supabase-server";
import { KpiCard, PickCard, IngestionFeed } from "@/components/blocks";
import { ProfitChart } from "@/components/profit-chart";
import { RunsHealth } from "@/components/runs-health";
import { Badge, EmptyState, PageHeader, Panel } from "@/components/ui";
import { money, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const fin = getMoney();
  const inventory = getInventory();
  const leads = getLeads();
  const picks = getPicks();
  const deals = getDeals();
  const brain = getBrain();
  const runsConfigured = supabaseConfigured();
  const [runsResult, searchLogResult] = runsConfigured
    ? await Promise.all([getCollectorRuns(14), getSearchLogRows()])
    : [null, null];
  // Distinguish "Supabase not configured" from "configured, but this fetch failed" from
  // "configured and genuinely has zero runs" — three different honest states, not one.
  const runs = runsResult ?? [];
  const runsFetchFailed = runsConfigured && runsResult === null;
  // null = unreadable (rendered "—"), a number = real count of brands due a re-mining run.
  const searchesDue = searchLogResult === null ? null : searchesDueCount(searchLogResult);
  const rag = brain.knowledge.ragCorpus;
  const c = brain.criteria as Record<string, number>;
  const g = (brain.guards ?? {}) as Record<string, number>;

  const systems = [
    { label: "Knowledge brain", on: Boolean(rag?.chunks), detail: rag ? `${rag.chunks.toLocaleString()} notes searchable` : "not built", href: "/ask" },
    { label: "Scout engine", on: picks.connected, detail: picks.connected ? "receiving Keepa data" : "needs paid Keepa key", href: "/intelligence" },
    // "connected" here means real (if manually captured) data exists — NOT that SP-API is
    // wired (SP-API integration is still planned, see amazon/page.tsx's roadmap table). Match
    // that page's own honest phrasing instead of overclaiming a specific unbuilt integration.
    { label: "Amazon account", on: fin.connected || inventory.connected, detail: fin.connected || inventory.connected ? "account data connected" : "SP-API not connected", href: "/amazon" },
    { label: "Deal feeds", on: deals.connected, detail: deals.connected ? "retailer feeds live" : "deal API not connected", href: "/deals" },
  ];

  const activeLeads = Object.values(leads.pipeline).reduce((a, b) => a + b, 0);

  // These are ai-brain.json's criteria thresholds. Only "Amazon Buy Box" is a real hard reject
  // (scout/scoring.py's oa_hard_reject() — unconditional regardless of score); BSR/Sales/ROI/
  // Profit/Offers/Price are SCORED thresholds that each contribute points to the 0-100 score —
  // a candidate can miss one and still clear the review bar. Calling all of these "gates" (as
  // an earlier version of this panel did) falsely implied every row was a pass/fail cutoff
  // (Code Review 2026-07-02, Finding S4).
  const criteria: [string, string][] = [
    ["BSR", `≤ ${Math.round(c.bsrMax / 1000)}k`],
    ["Sales/mo", `≥ ${c.minMonthlySales}`],
    ["ROI", `≥ ${Math.round(c.minRoi * 100)}%`],
    ["Profit/unit", `≥ $${c.minProfitPerUnit}`],
    ["Offers", `${c.minOffers}–${c.maxOffers}`],
    ["Price", `$${c.priceMin}–$${c.priceMax}`],
    ["Amazon Buy Box (hard reject)", c.rejectIfAmazonBuyBox ? "reject" : "allow"],
  ];
  const guards: [string, string][] = [
    ["Price spike", `> ${g.priceSpikeRatio ?? 1.5}× 90d`],
    ["Offers rising", `> ${g.offersRiseRatio ?? 1.4}× 90d`],
    ["Amazon BB share", `≥ ${Math.round((g.amazonBuyBoxShareMax ?? 0.2) * 100)}%`],
  ];

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        eyebrow="overview"
        title="Today"
        meta={
          <Badge tone={rag?.chunks ? "success" : "warn"}>
            {rag?.chunks ? "knowledge live" : "knowledge not built"}
          </Badge>
        }
      />

      <section aria-label="Key metrics" className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <KpiCard label="Net profit · MTD" tone="profit" value={money(fin.summary.netProfitMTD)} />
        <KpiCard label="Cash in inventory" value={money(fin.summary.cashInInventory)} />
        <KpiCard label="Blended ROI" tone="profit" value={fin.summary.blendedRoi == null ? "—" : pct(fin.summary.blendedRoi)} />
        <KpiCard label="Units at FBA" value={num(inventory.summary.atFba)} />
        <KpiCard label="Active leads" value={num(activeLeads)} />
        <KpiCard label="Knowledge notes" tone="accent" value={num(rag?.chunks ?? 0)} />
      </section>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2">
          <Panel title="Systems" icon={<Radar size={13} />} right="real connections only">
            <div className="flex flex-col divide-y divide-line">
              {systems.map((s) => (
                <Link
                  key={s.label}
                  href={s.href}
                  className="group flex cursor-pointer items-center gap-2.5 py-2 transition-colors hover:text-ink"
                >
                  <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", s.on ? "bg-profit" : "bg-warn")} aria-hidden />
                  <span className="w-32 shrink-0 text-[13px] text-ink">{s.label}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px] text-muted">{s.detail}</span>
                  <ArrowRight size={13} className="shrink-0 text-faint transition-colors group-hover:text-accent" aria-hidden />
                </Link>
              ))}
            </div>
          </Panel>

          <RunsHealth connected={runsConfigured} fetchFailed={runsFetchFailed} runs={runs} searchesDue={searchesDue} />

          <Panel title="Scout picks" icon={<Target size={13} />} right={picks.connected ? "live" : "offline"}>
            {picks.picks.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {picks.picks.slice(0, 4).map((p) => <PickCard key={p.asin} pick={p} />)}
              </div>
            ) : (
              <EmptyState title="No live picks" hint="Connect Keepa to see scored picks." />
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-3">
          <Panel title="Buy criteria" icon={<ShieldCheck size={13} />} right="ai-brain">
            <dl className="flex flex-col divide-y divide-line text-[12px]">
              {criteria.map(([k, v]) => (
                <div key={k} className="flex items-center justify-between py-1.5">
                  <dt className="text-muted">{k}</dt>
                  <dd className="num font-medium text-ink">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-2.5 border-t border-line pt-2">
              <div className="mb-1 text-[10px] uppercase tracking-[0.08em] text-faint">Red-flag guards</div>
              <dl className="flex flex-col divide-y divide-line text-[12px]">
                {guards.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between py-1.5">
                    <dt className="text-muted">{k}</dt>
                    <dd className="num font-medium text-loss">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </Panel>

          <Panel title="Profit · 30d" icon={<LineChart size={13} />} right={fin.connected ? "Amazon" : "manual"}>
            <ProfitChart data={fin.profitByDay} />
          </Panel>

          <Panel title="Latest ingested" icon={<Database size={13} />} right={`${rag?.documents ?? 0} docs`}>
            <IngestionFeed items={brain.ingestionLog.slice(-6)} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
