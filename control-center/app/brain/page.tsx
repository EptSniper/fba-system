import { BrainCircuit, Sparkles, Tag, BookOpen } from "lucide-react";
import { getBrain } from "@/lib/data";
import { Panel, Pill, Badge, DataNote, ActionLink } from "@/components/ui";
import { IngestionFeed } from "@/components/blocks";

export default function BrainPage() {
  const brain = getBrain();
  const c = brain.criteria as Record<string, number | boolean>;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium">Brain · what the AI knows</h1>
          <p className="mt-0.5 text-xs text-faint">
            One file — ai-brain.json — read by both this dashboard and the scout. Feed me info → I
            distill it → both update.
          </p>
        </div>
        <DataNote source="ai-brain.json" updated={brain.updated} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/ask" tone="primary">Test what the brain knows</ActionLink>
        <ActionLink href="/knowledge">Review source coverage</ActionLink>
      </div>

      <Panel title="Buy / no-buy criteria" icon={<BrainCircuit size={16} />}>
        <div className="flex flex-wrap gap-2">
          <Pill label="bsr ≤" value={`${Math.round(Number(c.bsrMax) / 1000)}k`} />
          <Pill label="sales ≥" value={`${c.minMonthlySales}/mo`} />
          <Pill label="offers" value={`${c.minOffers}–${c.maxOffers}`} />
          <Pill label="roi ≥" value={`${Math.round(Number(c.minRoi) * 100)}%`} />
          <Pill label="profit ≥" value={`$${c.minProfitPerUnit}`} />
          <Pill label="price" value={`$${c.priceMin}–${c.priceMax}`} />
          {c.rejectIfAmazonBuyBox ? <Badge tone="loss">reject if Amazon Buy Box</Badge> : null}
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Brands the finder aims at"
          icon={<Tag size={16} />}
          right={`${brain.brands.friendly.length} known-good · ${brain.brands.avoid.length} avoid`}
        >
          <div className="mb-3 flex flex-wrap gap-1.5">
            {brain.brands.friendly.map((b) => (
              <span key={b} className="rounded-md bg-profit/10 px-2 py-0.5 text-xs text-profit">
                {b}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {brain.brands.avoid.map((b) => (
              <span key={b} className="rounded-md bg-loss/10 px-2 py-0.5 text-xs text-loss">
                {b}
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Knowledge" icon={<BookOpen size={16} />}>
          <div className="flex flex-wrap gap-2">
            <Pill label="transcripts" value={brain.knowledge.transcripts} />
            <Pill label="playbooks" value={brain.knowledge.playbooks.length} />
            <Pill label="fundamentals" value={brain.knowledge.fundamentals} />
            <Pill label="tools" value={brain.tools.length} />
          </div>
          <p className="mt-3 text-xs text-faint">
            Playbooks: {brain.knowledge.playbooks.join(", ")}. Last distilled{" "}
            {brain.knowledge.lastDistilled}.
          </p>
        </Panel>
      </div>

      <Panel title="Ingestion log · feed it, it grows" icon={<Sparkles size={16} />}>
        <IngestionFeed items={brain.ingestionLog} />
      </Panel>
    </div>
  );
}
