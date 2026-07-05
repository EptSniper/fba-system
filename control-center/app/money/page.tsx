import { ShieldAlert } from "lucide-react";
import { getBrain, getInventory, getMoney } from "@/lib/data";
import { money, pct } from "@/lib/format";
import { agedTier, daysAtFba, isCutLossCandidate } from "@/lib/aged-inventory";
import { committedCapital, getOpenBuyCommitments, supabaseConfigured } from "@/lib/supabase-server";
import { KpiCard } from "@/components/blocks";
import { Panel, EmptyState, Badge, ConnBadge, DataNote, ActionLink } from "@/components/ui";
import { ProfitChart } from "@/components/profit-chart";

const agedBadgeTone: Record<string, "success" | "warn" | "loss"> = { ok: "success", amber: "warn", red: "loss", surcharge: "loss" };

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

// sales rows have no fixed schema yet (SP-API wiring is still planned — see amazon/page.tsx's
// roadmap), so this renders whatever keys are actually present rather than assuming a shape.
// Money-ish keys get currency formatting; everything else prints as-is. Fixes Code Review
// 2026-07-02 Finding CB1: this panel used to render `null` the moment real sales existed
// (`m.sales.length ? null : <EmptyState />`) — dishonest the instant the first real sale landed.
const MONEY_KEY_HINTS = ["amount", "price", "profit", "fee", "revenue", "payout", "cost", "total"];

function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number" && MONEY_KEY_HINTS.some((h) => key.toLowerCase().includes(h))) {
    return money(value);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function prettyLabel(key: string): string {
  return key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (c) => c.toUpperCase());
}

export default async function MoneyPage() {
  const m = getMoney();
  const inventory = getInventory();
  const brain = getBrain();
  const toolsTotal = m.recurringCosts.reduce((s, c) => s + (c.active ? c.monthly : 0), 0);
  const salesColumns = m.sales.length ? Object.keys(m.sales[0]) : [];

  // Capital & safety cockpit (CC2 item 2) — bankroll.* is documented as informational/
  // doctrine in ai-brain.json ("nothing in scoring.py consumes them"), so this panel is the
  // FIRST place these numbers become a live check rather than just text on the Brain page.
  const bankroll = brain.operations?.bankroll ?? {};
  const capitalConfigured = supabaseConfigured();
  const openBuyRows = capitalConfigured ? await getOpenBuyCommitments() : null;
  const openBuyFetchFailed = capitalConfigured && openBuyRows === null;
  const openBuyCommitted = openBuyRows ? committedCapital(openBuyRows) : 0;
  const totalCommitted = m.summary.cashInInventory + openBuyCommitted;

  const now = new Date();
  const cutLossDays = bankroll.cutLossDays ?? 60;
  const agedSurchargeDay = bankroll.agedSurchargeDay ?? 181;
  const cutLossItems = inventory.items.filter((it) => isCutLossCandidate(it, cutLossDays, now));
  const agedItems = inventory.items
    .filter((it) => it.receivedAt)
    .map((it) => ({ ...it, days: daysAtFba(it.receivedAt!, now) }))
    .filter((it) => it.days >= 120)
    .sort((a, b) => b.days - a.days);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Money</h1>
        <ConnBadge connected={m.connected} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="https://sellercentral.amazon.com/payments/dashboard/index.html" external tone="primary">Open Amazon Payments</ActionLink>
        <ActionLink href="/inventory">Review inventory</ActionLink>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Invested" value={money(m.summary.invested)} />
        <KpiCard label="Revenue" value={money(m.summary.revenue)} tone="profit" />
        <KpiCard label="Amazon fees" value={money(m.summary.fees)} tone="loss" />
        <KpiCard label="Net profit" value={money(m.summary.netProfit)} tone="profit" />
      </section>

      <Panel
        title="Capital & safety"
        icon={<ShieldAlert size={13} />}
        right={bankroll.cashReservePct !== undefined ? `reserve target: ${pct(bankroll.cashReservePct)}` : undefined}
      >
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <KpiCard label="Cash in inventory" value={money(m.summary.cashInInventory)} />
            <KpiCard
              label="Open buy commitments"
              value={capitalConfigured ? (openBuyFetchFailed ? "—" : money(openBuyCommitted)) : "—"}
            />
            <KpiCard label="Total committed" value={money(totalCommitted)} tone="accent" />
          </div>
          {bankroll.buckets?.length ? (
            <p className="text-xs text-faint">
              Bankroll buckets (ai-brain.json, amounts not yet tracked per-bucket): {bankroll.buckets.join(", ")}.
              Reserve policy: keep at least {pct(bankroll.cashReservePct ?? 0.2)} of sourcing capital uncommitted.
            </p>
          ) : null}

          <div>
            <div className="mb-1.5 text-[10px] uppercase tracking-[0.08em] text-faint">Cut-loss list ({cutLossDays}+ days no sale)</div>
            {!inventory.items.length ? (
              <EmptyState title="No inventory yet" hint="Nothing to check for cut-loss until real inventory items exist." />
            ) : !cutLossItems.length ? (
              <EmptyState title="Nothing flagged" hint="No item has gone this long without a sale." />
            ) : (
              <ul className="flex flex-col divide-y divide-line text-sm">
                {cutLossItems.map((it, i) => (
                  <li key={i} className="flex items-center justify-between py-1.5">
                    <span className="truncate text-ink">{it.product}</span>
                    <Badge tone="loss">cut-loss candidate</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <div className="mb-1.5 text-[10px] uppercase tracking-[0.08em] text-faint">Aged-inventory countdown (amber 120d / red 150d / surcharge live {agedSurchargeDay}d)</div>
            {!inventory.items.length ? (
              <EmptyState title="No inventory yet" hint="Days-at-FBA tracking starts once real inventory items exist." />
            ) : !agedItems.length ? (
              <EmptyState title="Nothing aged" hint="No item has been at FBA 120+ days." />
            ) : (
              <ul className="flex flex-col divide-y divide-line text-sm">
                {agedItems.map((it, i) => (
                  <li key={i} className="flex items-center justify-between py-1.5">
                    <span className="truncate text-ink">{it.product}</span>
                    <span className="flex items-center gap-2">
                      <span className="num text-muted">{it.days}d</span>
                      <Badge tone={agedBadgeTone[agedTier(it.days, agedSurchargeDay)]}>{agedTier(it.days, agedSurchargeDay)}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Panel>

      <Panel title="Monthly tool costs" right={`active: ${money(toolsTotal)}/mo`}>
        <ul className="flex flex-col divide-y divide-line">
          {m.recurringCosts.map((c) => (
            <li key={c.tool} className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-muted">{c.tool}</span>
              <span className="flex items-center gap-3">
                <span className="num text-ink">{money(c.monthly)}/mo</span>
                <Badge tone={c.active ? "success" : "muted"}>{c.active ? "active" : "not yet"}</Badge>
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Sales & payouts" right={<DataNote source={m.source} updated={m.updated} />}>
        {m.sales.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  {salesColumns.map((col) => (
                    <th key={col} className="py-2 pr-4 font-medium">{prettyLabel(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {m.sales.map((row, i) => (
                  <tr key={i}>
                    {salesColumns.map((col) => (
                      <td key={col} className="num py-2 pr-4 text-ink">{formatCell(col, row[col])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No sales yet"
            hint="Every sale and payout will show here — auto-filled from Amazon SP-API once the account is live."
          />
        )}
      </Panel>

      <Panel title="Profit · last 30 days">
        <ProfitChart data={m.profitByDay} />
      </Panel>
    </div>
  );
}
