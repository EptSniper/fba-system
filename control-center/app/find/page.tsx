import { Target } from "lucide-react";
import { getBrain, getPicks } from "@/lib/data";
import { Panel, Pill, EmptyState, Badge, DataNote } from "@/components/ui";
import { PickCard } from "@/components/blocks";
import { DealAnalyzer } from "@/components/deal-analyzer";
import { PageHeader } from "@/components/ui";

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
          }}
          guards={{
            priceSpikeRatio: Number(g.priceSpikeRatio ?? 1.5),
            offersRiseRatio: Number(g.offersRiseRatio ?? 1.4),
            amazonBuyBoxShareMax: Number(g.amazonBuyBoxShareMax ?? 0.2),
          }}
          groceryMinRoi={Number(c.exceptions?.groceryMinRoi ?? 0.25)}
          referralRates={brain.fees?.referralRates ?? { default: 0.15 }}
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
