import { MessageSquareText } from "lucide-react";
import { getBrain } from "@/lib/data";
import { KnowledgeAsk } from "@/components/knowledge-ask";
import { PageHeader, Panel, Badge } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default function AskPage() {
  const brain = getBrain();
  const rag = brain.knowledge.ragCorpus;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Knowledge operator"
        title="Ask the sourcing brain"
        description={`Fast answers grounded in your ${brain.knowledge.transcripts} courses, playbooks, and Amazon source notes—not generic memory.`}
        meta={<Badge tone={rag?.chunks ? "success" : "warn"}>{rag?.chunks?.toLocaleString() ?? 0} cited notes ready</Badge>}
      />
      <Panel title="Ask" icon={<MessageSquareText size={16} />} right="live evidence + local fallback">
        <KnowledgeAsk chunkCount={rag?.chunks ?? 0} />
      </Panel>
    </div>
  );
}
