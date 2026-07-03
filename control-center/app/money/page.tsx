import { getMoney } from "@/lib/data";
import { money } from "@/lib/format";
import { KpiCard } from "@/components/blocks";
import { Panel, EmptyState, Badge, ConnBadge, DataNote, ActionLink } from "@/components/ui";
import { ProfitChart } from "@/components/profit-chart";

export default function MoneyPage() {
  const m = getMoney();
  const toolsTotal = m.recurringCosts.reduce((s, c) => s + (c.active ? c.monthly : 0), 0);

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
        {m.sales.length ? null : (
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
