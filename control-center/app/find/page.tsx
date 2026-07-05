import { Target } from "lucide-react";
import { getBrain, getPicks } from "@/lib/data";
import { Panel, Pill, EmptyState, Badge, DataNote } from "@/components/ui";
import { PickCard } from "@/components/blocks";
import { DealAnalyzer } from "@/components/deal-analyzer";
import { PageHeader } from "@/components/ui";

// Reads live sibling learning-hub/ files on every request (Code Review 2026-07-02, Finding
// CS8) — without this, Next.js may statically cache the page at build time and serve stale
// data even though the underlying file changed.
export const dynamic = "force-dynamic";

export default function FindPage() {
  const picks = getPicks();
  const brain = getBrain();
  const c = brain.criteria as Record<string, number | boolean> & {
    exceptions?: { groceryMinRoi?: number };
  };
  const g = (brain.guards ?? {}) as Record<string, unknown> & {
    priceSpikeRatio?: number;
    offersRiseRatio?: number;
    amazonBuyBoxShareMax?: number;
    currentVsAvg90PriceCaution?: number;
    restrictionKeywords?: Record<string, string[]>;
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Sourcing workspace"
        title="Find and rate products"
        description="Run the deal math, enforce the hard gates, then verify eligibility and history before money moves."
        meta={<Badge tone={picks.connected ? "success" : "warn"}>
          {picks.connected ? "live" : "scout offline"}
        </Badge>}
      />

      <Panel title="Deal analyzer" icon={<Target size={16} />} right="live estimate · nothing saved unless you click Save">
        <DealAnalyzer
          criteria={{
            bsrMax: Number(c.bsrMax),
            minMonthlySales: Number(c.minMonthlySales),
            minOffers: Number(c.minOffers),
            maxOffers: Number(c.maxOffers),
            minRoi: Number(c.minRoi),
            minProfitPerUnit: Number(c.minProfitPerUnit),
            priceMin: Number(c.priceMin),
            priceMax: Number(c.priceMax),
          }}
          guards={{
            priceSpikeRatio: Number(g.priceSpikeRatio ?? 1.5),
            offersRiseRatio: Number(g.offersRiseRatio ?? 1.4),
            amazonBuyBoxShareMax: Number(g.amazonBuyBoxShareMax ?? 0.2),
            priceCautionRatio: Number(g.currentVsAvg90PriceCaution ?? 1.15),
          }}
          groceryMinRoi={Number(c.exceptions?.groceryMinRoi ?? 0.25)}
          referralRates={brain.fees?.referralRates ?? { default: 0.15 }}
          bandedRates={brain.fees?.bandedRates ?? {}}
          minReferralFee={Number(brain.fees?.minReferralFee ?? 0.3)}
          fuelSurcharge={Number(brain.fees?.fuelSurcharge ?? 0.035)}
          prepCost={Number(brain.fees?.prepCost ?? 0.5)}
          worstCaseLossBarUsd={Number(brain.scoring?.worstCaseLossBarUsd ?? 2)}
          marginHealthThreshold={Number(brain.scoring?.marginHealthThreshold ?? 0.2)}
          friendlyBrands={brain.brands.friendly}
          avoidBrands={brain.brands.avoid}
          restrictionKeywords={g.restrictionKeywords ?? {}}
        />
      </Panel>

      <Panel title="Buy / no-buy criteria the rater uses" icon={<Target size={16} />}>
        <div className="flex flex-wrap gap-2">
          <Pill label="bsr ≤" value={`${Math.round(Number(c.bsrMax) / 1000)}k`} />
          <Pill label="sales ≥" value={`${c.minMonthlySales}/mo`} />
          <Pill label="offers" value={`${c.minOffers}–${c.maxOffers}`} />
          <Pill label="roi ≥" value={`${Math.round(Number(c.minRoi) * 100)}%`} />
          <Pill label="profit ≥" value={`$${c.minProfitPerUnit}`} />
          <Pill label="price" value={`$${c.priceMin}–${c.priceMax}`} />
          {c.rejectIfAmazonBuyBox ? <Badge tone="loss">reject if Amazon Buy Box</Badge> : null}
        </div>
        <p className="mt-3 text-xs text-faint">
          Read live from ai-brain.json — the same file the scout scores on. Feed Claude new
          guidance and this updates everywhere at once.
        </p>
      </Panel>

      <Panel
        title="Scored picks"
        right={<DataNote source={picks.source} updated={picks.updated} />}
      >
        {picks.picks.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {picks.picks.map((p) => (
              <PickCard key={p.asin} pick={p} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={<Target size={20} />}
            title="No picks yet"
            hint={picks.reason ?? "Add a paid Keepa key to scout/.env and run it — picks land here and on Discord."}
          />
        )}
      </Panel>
    </div>
  );
}
