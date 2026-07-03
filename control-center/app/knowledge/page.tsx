import { Library, ShieldCheck, ScrollText } from "lucide-react";
import { getBrain, getRagManifest } from "@/lib/data";
import { Panel, Badge, Pill, EmptyState, DataNote, ActionLink } from "@/components/ui";
import { KpiCard } from "@/components/blocks";
import { Reveal, Counter } from "@/components/motion";

const statusTone: Record<string, string> = {
  collected: "success",
  index_only: "info",
  pending: "warn",
};

export default function KnowledgePage() {
  const brain = getBrain();
  const rag = brain.knowledge.ragCorpus;
  const manifest = getRagManifest();
  const sources = manifest.sources ?? [];

  const byStatus = (s: string) => sources.filter((x) => x.status === s).length;

  return (
    <div className="flex flex-col gap-6">
      <Reveal>
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-accent"><Library size={18} /></span>
            <h1 className="text-xl font-semibold tracking-tight">Knowledge base</h1>
          </div>
          <DataNote source="RAG corpus" updated={`brain ${brain.updated}`} />
        </header>
      </Reveal>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/ask" tone="primary">Ask the knowledge brain</ActionLink>
        <ActionLink href="/brain">Inspect distilled brain</ActionLink>
      </div>

      {rag ? (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Documents", value: rag.documents, kind: "num" as const },
              { label: "Cited chunks", value: rag.chunks, kind: "num" as const, tone: "accent" as const },
              { label: "Approx tokens", value: rag.approxTokens ?? 0, kind: "num" as const },
              { label: "Categories", value: rag.categories?.length ?? 0, kind: "num" as const },
            ].map((k, i) => (
              <Reveal key={k.label} delay={i * 0.05}>
                <KpiCard label={k.label} tone={k.tone ?? "ink"} value={<Counter value={k.value} kind={k.kind} />} />
              </Reveal>
            ))}
          </section>

          <Reveal>
            <Panel title="How it answers" icon={<ShieldCheck size={16} />} right="retrieve · cite · refuse">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-md border border-line bg-panel2/50 p-3">
                  <div className="mb-1 text-sm font-medium text-profit">Can I profit?</div>
                  <p className="text-[13px] text-muted">
                    The scout — BSR, ROI, offers, Buy-Box + the price-spike / offers-rising / Amazon-share guards.
                  </p>
                </div>
                <div className="rounded-md border border-line bg-panel2/50 p-3">
                  <div className="mb-1 text-sm font-medium text-accent">Am I allowed?</div>
                  <p className="text-[13px] text-muted">
                    This knowledge base — gating, IP/authenticity, restricted products, invoices, FBA eligibility — answered from cited Amazon passages.
                  </p>
                </div>
              </div>
              <p className="mt-3 text-[13px] text-faint">
                Retrieval-augmented, not fine-tuned — every answer cites its source and dates it, so policy advice never goes silently stale.
              </p>
            </Panel>
          </Reveal>

          <Reveal>
            <Panel title="Coverage" icon={<ScrollText size={16} />} right={`${sources.length} Amazon sources tracked`}>
              <div className="mb-3 flex flex-wrap gap-2">
                <Pill label="collected" value={byStatus("collected")} />
                <Pill label="indexed (on-demand)" value={byStatus("index_only")} />
                <Pill label="pending" value={byStatus("pending")} />
              </div>
              <ul className="flex flex-col divide-y divide-line">
                {sources.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-[13px]">
                    <span className="min-w-0">
                      <span className="block truncate text-ink">{s.title}</span>
                      <span className="num text-xs text-faint">{s.category} · access: {s.access}</span>
                    </span>
                    <Badge tone={statusTone[s.status] ?? "muted"}>{s.status.replace("_", " ")}</Badge>
                  </li>
                ))}
              </ul>
              {manifest.compliance ? (
                <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-faint">
                  {manifest.compliance}
                </p>
              ) : null}
            </Panel>
          </Reveal>
        </>
      ) : (
        <EmptyState
          icon={<Library size={20} />}
          title="Knowledge base not built yet"
          hint="Run knowledge-rag/ingest.py then build_index.py build."
        />
      )}
    </div>
  );
}
