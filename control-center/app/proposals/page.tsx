import { ListTodo } from "lucide-react";
import { parseProposals, pendingCount, type ProposalId, type ProposalStatus } from "@/lib/proposals";
import { readAllDecisionEvents, statusMap } from "@/lib/proposal-drafts";
import { hubTrackingPath, readTextFile } from "@/lib/events-server";
import { ProposalsPanel } from "@/components/proposals-panel";
import { Badge, EmptyState, PageHeader, Panel } from "@/components/ui";

// Reads the live sibling learning-hub/tracking/brain-proposals.md + the decision ledger on
// every request (Code Review 2026-07-02, Finding CS8's convention).
export const dynamic = "force-dynamic";

export default function ProposalsPage() {
  const markdown = readTextFile(hubTrackingPath("brain-proposals.md"));
  const runs = markdown === null ? null : parseProposals(markdown);
  const ledgerStatuses = runs === null ? new Map<ProposalId, ProposalStatus>() : statusMap(readAllDecisionEvents());
  const pending = runs === null ? 0 : pendingCount(runs, ledgerStatuses);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        eyebrow="System"
        title="Brain Proposals"
        description="Evidence-based suggestions from scout/propose_updates.py. Approve drafts an exact ai-brain.json edit immediately via Claude; nothing is written until you separately confirm the draft."
        meta={runs !== null ? <Badge tone={pending ? "warn" : "success"}>{pending} pending</Badge> : undefined}
      />

      {runs === null ? (
        <Panel title="Proposals" icon={<ListTodo size={13} />}>
          <EmptyState
            title="Could not read brain-proposals.md"
            hint="Not available in this deployment, or the file doesn't exist yet — it's written by scout/propose_updates.py at the end of every run_daily.py cycle."
          />
        </Panel>
      ) : !runs.length ? (
        <Panel title="Proposals" icon={<ListTodo size={13} />}>
          <EmptyState title="No proposal runs recorded yet" />
        </Panel>
      ) : (
        <ProposalsPanel runs={runs} initialStatuses={Object.fromEntries(ledgerStatuses)} />
      )}
    </div>
  );
}
