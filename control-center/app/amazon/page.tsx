import { ArrowUpRight, Boxes, CircleDollarSign, HeartPulse, ListPlus, Send, Store, Workflow } from "lucide-react";
import { getInventory, getMoney } from "@/lib/data";
import { Badge, PageHeader, Panel } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

const WORKSPACES = [
  { title: "Account Health", description: "Policy compliance, order defects, intellectual-property complaints, and account status.", href: "https://sellercentral.amazon.com/performance/dashboard", icon: HeartPulse, status: "Seller Central" },
  { title: "Manage All Inventory", description: "Search listings, update prices and quantities, and inspect active or inactive offers.", href: "https://sellercentral.amazon.com/inventory", icon: Boxes, status: "Seller Central" },
  { title: "Payments", description: "Disbursements, transaction-level fees, refunds, reserves, and settlement reports.", href: "https://sellercentral.amazon.com/payments/dashboard/index.html", icon: CircleDollarSign, status: "Seller Central" },
  { title: "Send to Amazon", description: "Create and track inbound FBA shipments, packing, placement, and carrier details.", href: "https://sellercentral.amazon.com/fba/sendtoamazon", icon: Send, status: "Seller Central" },
  { title: "Add Products", description: "Test whether your account can list an ASIN before sourcing it.", href: "https://sellercentral.amazon.com/product-search", icon: ListPlus, status: "Seller Central" },
  { title: "Revenue Calculator", description: "Confirm exact Amazon fee estimates using real dimensions, category, and fulfillment method.", href: "https://sellercentral.amazon.com/revcal", icon: Workflow, status: "Seller Central" },
];

const API_DOMAINS = [
  ["Listings Restrictions", "Account-specific eligibility before a buy", "highest priority"],
  ["FBA Inventory", "Fulfillable, inbound, reserved, unfulfillable, researching", "planned"],
  ["Finances", "Fees, refunds, settlements, payouts, realized outcome labels", "planned"],
  ["Fulfillment Inbound", "Shipment plans, boxes, placement, receiving progress", "planned"],
  ["Catalog Items", "ASIN attributes, dimensions, identifiers, classifications", "planned"],
  ["Notifications", "Listing issues, buyability changes, inventory events", "planned"],
];

export default function AmazonOpsPage() {
  const inventory = getInventory();
  const money = getMoney();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Amazon account layer"
        title="Amazon operations"
        description="One launchpad for Seller Central workflows now, with SP-API-powered account data replacing manual tracking as credentials become available."
        meta={<Badge tone={inventory.connected || money.connected ? "success" : "warn"}>{inventory.connected || money.connected ? "account data connected" : "SP-API not connected"}</Badge>}
      />

      <Panel title="Seller Central workspaces" icon={<Store size={16} />} right="opens Amazon in a new tab">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {WORKSPACES.map(({ title, description, href, icon: Icon, status }) => (
            <a key={title} href={href} target="_blank" rel="noopener noreferrer" className="group cursor-pointer rounded-xl border border-line bg-bg/40 p-4 transition-colors duration-200 hover:border-accent/40 hover:bg-accent/5">
              <div className="flex items-start justify-between gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-panel2 text-accent"><Icon size={17} /></span>
                <ArrowUpRight size={15} className="text-faint transition-colors group-hover:text-accent" />
              </div>
              <h2 className="mt-4 text-sm font-semibold text-ink">{title}</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{description}</p>
              <div className="num mt-4 text-[10px] uppercase tracking-[0.14em] text-faint">{status}</div>
            </a>
          ))}
        </div>
      </Panel>

      <Panel title="Account data roadmap" icon={<Workflow size={16} />} right="SP-API · server-side only">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-collapse text-left text-sm">
            <thead><tr className="border-b border-line text-[10px] uppercase tracking-[0.14em] text-faint"><th className="pb-3 font-medium">Data domain</th><th className="pb-3 font-medium">What it unlocks</th><th className="pb-3 text-right font-medium">Status</th></tr></thead>
            <tbody className="divide-y divide-line">
              {API_DOMAINS.map(([name, use, status]) => (
                <tr key={name}><td className="py-3 font-medium text-ink">{name}</td><td className="py-3 text-muted">{use}</td><td className="py-3 text-right"><Badge tone={status === "highest priority" ? "accent" : "muted"}>{status}</Badge></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
