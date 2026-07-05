import { ClipboardCheck } from "lucide-react";
import { PageHeader, Panel } from "@/components/ui";
import { ReviewQueue } from "@/components/review-queue";
import { buildQueue } from "@/lib/queue-server";

// Reads live Supabase business tables on every request (Code Review 2026-07-02, Finding CS8's
// convention, extended to the new Supabase-backed pages).
export const dynamic = "force-dynamic";

export default async function QueuePage() {
  const { connected, items } = await buildQueue();

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="Command"
        title="Review Queue"
        description="Everything waiting on a human decision — scout leads and deal-match verifications, triage-ordered. Every action requires a reason code and writes a real decision to Supabase."
      />

      <Panel title={`Queue (${items.length})`} icon={<ClipboardCheck size={16} />}>
        <ReviewQueue initialItems={items} connected={connected} />
      </Panel>
    </div>
  );
}
