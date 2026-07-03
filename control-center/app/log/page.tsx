import { getEvents } from "@/lib/data";
import { PageHeader, DataNote } from "@/components/ui";
import { CaptureForms } from "@/components/capture-forms";

export const dynamic = "force-dynamic";

export default function LogPage() {
  const events = getEvents();

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Capture"
        title="Operator Log"
        description="Leads, decisions, inventory, outcomes → local append-only ledger. Never buys or moves money."
        meta={<DataNote source="events.jsonl" updated="local-only" />}
      />
      <CaptureForms initialEvents={events} />
    </div>
  );
}
