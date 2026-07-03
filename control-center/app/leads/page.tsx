import { ListChecks } from "lucide-react";
import { getLeads } from "@/lib/data";
import { Panel, Pill, EmptyState, DataNote, ActionLink } from "@/components/ui";

export default function LeadsPage() {
  const leads = getLeads();
  const hasPipeline = Object.values(leads.pipeline).some((v) => v > 0);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Leads</h1>
        <DataNote source={leads.source} updated={leads.updated} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/find" tone="primary">Analyze a product</ActionLink>
        <ActionLink href="https://sellercentral.amazon.com/product-search" external>Check listing eligibility</ActionLink>
      </div>

      <Panel title="Pipeline" icon={<ListChecks size={16} />}>
        {hasPipeline ? (
          <div className="flex flex-wrap gap-2">
            {Object.entries(leads.pipeline).map(([k, v]) => (
              <Pill key={k} label={k} value={v} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<ListChecks size={20} />}
            title="Pipeline is empty"
            hint="Add a product idea or approve a scout pick — it moves idea → research → buy → ordered → sold."
          />
        )}
      </Panel>

      <Panel title="Leads">
        {leads.leads.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {leads.leads.map((l, i) => (
              <li key={i} className="flex items-center justify-between py-2.5">
                <span>{l.product}</span>
                <span className="num text-muted">{l.status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No leads tracked yet" />
        )}
      </Panel>
    </div>
  );
}
