import { Package } from "lucide-react";
import { getInventory } from "@/lib/data";
import { num } from "@/lib/format";
import { KpiCard } from "@/components/blocks";
import { Panel, EmptyState, ConnBadge, DataNote, ActionLink } from "@/components/ui";

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
        {inv.items.length ? null : (
          <EmptyState
            icon={<Package size={20} />}
            title="No inventory yet"
            hint="Units appear here when you order and ship to FBA — live stock + restock alerts come from SP-API later."
          />
        )}
      </Panel>

      <Panel title="Restock watch">
        {inv.restock.length ? null : (
          <EmptyState title="Nothing to restock" hint="Fast movers nearing the low-inventory line will be flagged here." />
        )}
      </Panel>
    </div>
  );
}
