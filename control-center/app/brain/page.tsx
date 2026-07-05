import { BrainCircuit, Sparkles, Tag, BookOpen, CalendarClock } from "lucide-react";
import { getBrain } from "@/lib/data";
import { Panel, Pill, Badge, DataNote, ActionLink } from "@/components/ui";
import { IngestionFeed } from "@/components/blocks";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default function BrainPage() {
  const brain = getBrain();
  const c = brain.criteria as Record<string, number | boolean>;
  const seasonal = brain.operations?.seasonal2026;
  const bankroll = brain.operations?.bankroll;
  const policy = brain.policy2026;
  const preferredOffers = brain.scoring?.preferredOffers;

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
          {preferredOffers ? (
            <Pill label="goldilocks offers" value={`${preferredOffers.min}-${preferredOffers.max} (+${preferredOffers.bonus}pts)`} />
          ) : null}
        </div>
      </Panel>

      {(seasonal || bankroll || policy) && (
        <Panel title="Operations & 2026 policy" icon={<CalendarClock size={16} />}>
          <p className="mb-3 text-xs text-faint">
            Informational doctrine, not scoring inputs — context for timing and cash-flow decisions.
          </p>
          <div className="grid gap-4 sm:grid-cols-3">
            {seasonal ? (
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted">2026 seasonal calendar</div>
                <ul className="flex flex-col gap-1 text-xs text-ink">
                  {seasonal.primeDayWindow ? (
                    <li>Prime Day sourcing: {seasonal.primeDayWindow.start} – {seasonal.primeDayWindow.end}</li>
                  ) : null}
                  {seasonal.backToSchoolBuyWindow ? <li>Back-to-school: {seasonal.backToSchoolBuyWindow}</li> : null}
                  {seasonal.q4ArrivalDeadline ? <li>Q4 arrival deadline: {seasonal.q4ArrivalDeadline}</li> : null}
                  {seasonal.q4StopSpeculativeBuysAfterWeek ? (
                    <li>Stop speculative Q4 buys after week {seasonal.q4StopSpeculativeBuysAfterWeek}</li>
                  ) : null}
                  {seasonal.toysBuyWindows?.length ? <li>Toys buy windows: {seasonal.toysBuyWindows.join(", ")}</li> : null}
                </ul>
              </div>
            ) : null}
            {bankroll ? (
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted">Bankroll & safety</div>
                <ul className="flex flex-col gap-1 text-xs text-ink">
                  {bankroll.cashReservePct !== undefined ? (
                    <li>Cash reserve: {Math.round(bankroll.cashReservePct * 100)}%</li>
                  ) : null}
                  {bankroll.cutLossDays !== undefined ? <li>Cut-loss after {bankroll.cutLossDays} days</li> : null}
                  {bankroll.agedSurchargeDay !== undefined ? (
                    <li>Aged-inventory surcharge starts day {bankroll.agedSurchargeDay}</li>
                  ) : null}
                  {bankroll.buckets?.length ? <li>Buckets: {bankroll.buckets.join(", ")}</li> : null}
                </ul>
              </div>
            ) : null}
            {policy ? (
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted">2026 policy facts</div>
                <ul className="flex flex-col gap-1 text-xs text-ink">
                  {policy.payoutHoldDaysAfterDelivery !== undefined ? (
                    <li>Payout hold: delivery + {policy.payoutHoldDaysAfterDelivery} days (since {policy.payoutHoldEffective})</li>
                  ) : null}
                  {policy.comminglingEnded ? <li>Commingling ended ({policy.comminglingEndedEffective})</li> : null}
                  {policy.feeIncreasePerUnit !== undefined ? (
                    <li>Fee increase: +${policy.feeIncreasePerUnit}/unit ({policy.feeIncreaseEffective})</li>
                  ) : null}
                </ul>
              </div>
            ) : null}
          </div>
        </Panel>
      )}

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
