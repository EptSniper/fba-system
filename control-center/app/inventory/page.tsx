import { Package } from "lucide-react";
import { getInventory } from "@/lib/data";
import { num } from "@/lib/format";
import { KpiCard } from "@/components/blocks";
import { Badge, Panel, EmptyState, ConnBadge, DataNote, ActionLink } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default function InventoryPage() {
  const inv = getInventory();
  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Inventory</h1>
        <ConnBadge connected={inv.connected} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="https://sellercentral.amazon.com/inventory" external tone="primary">Open Amazon inventory</ActionLink>
        <ActionLink href="/find">Analyze a replenishment</ActionLink>
      </div>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Units owned" value={num(inv.summary.unitsOwned)} />
        <KpiCard label="At fba" value={num(inv.summary.atFba)} />
        <KpiCard label="In transit" value={num(inv.summary.inTransit)} />
        <KpiCard label="Low stock" value={num(inv.summary.lowStock)} tone={inv.summary.lowStock ? "loss" : "ink"} />
      </section>

      <Panel
        title="Stock"
        icon={<Package size={16} />}
        right={<DataNote source={inv.source} updated={inv.updated} />}
      >
        {inv.items.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {inv.items.map((item, i) => (
              <li key={item.asin ?? i} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-ink">{item.product}</div>
                  {item.asin ? <div className="num text-xs text-muted">{item.asin}</div> : null}
                </div>
                <div className="flex items-center gap-3 whitespace-nowrap">
                  <span className="num text-muted">{num(item.owned)} owned</span>
                  <span className="num text-muted">{num(item.atFba)} at FBA</span>
                  {item.inTransit ? <span className="num text-muted">{num(item.inTransit)} in transit</span> : null}
                  <Badge tone={item.status === "low" ? "loss" : item.status === "ok" ? "success" : "muted"}>
                    {item.status}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Package size={20} />}
            title="No inventory yet"
            hint="Units appear here when you order and ship to FBA — live stock + restock alerts come from SP-API later."
          />
        )}
      </Panel>

      <Panel title="Restock watch">
        {inv.restock.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {inv.restock.map((r, i) => (
              <li key={i} className="flex items-center justify-between py-2.5">
                <span className="text-ink">{r.product}</span>
                <Badge tone={r.daysLeft <= 14 ? "loss" : r.daysLeft <= 30 ? "warn" : "muted"}>
                  {num(r.daysLeft)}d left
                </Badge>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="Nothing to restock" hint="Fast movers nearing the low-inventory line will be flagged here." />
        )}
      </Panel>
    </div>
  );
}
