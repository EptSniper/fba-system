// lib/aged-inventory.ts — pure date math for the Money page's capital & safety cockpit (CC2
// item 2): days-at-FBA countdown + cut-loss detection. Takes `now` as a parameter (never reads
// the clock itself) so it's exercisable with fixture dates.
//
// inventory.json's items have no receivedAt/lastSaleAt fields yet (genuinely empty inventory —
// nothing has been bought). lib/types.ts's Inventory item type gained both as OPTIONAL fields
// for this feature; until real inventory exists, every function here is exercised only by
// fixtures, and the UI renders an honest empty state (no fabricated aged/cut-loss items).

const DAY_MS = 86_400_000;

export function daysAtFba(receivedAt: string, now: Date): number {
  const received = new Date(receivedAt).getTime();
  return Math.max(0, Math.floor((now.getTime() - received) / DAY_MS));
}

export type AgedTier = "ok" | "amber" | "red" | "surcharge";

// amber@120 / red@150 are UI presentation bands only (not brain-governed — the plan calls only
// the surcharge threshold out as brain-sourced). agedSurchargeDay comes from
// ai-brain.json's operations.bankroll.agedSurchargeDay (Amazon's real 2026 policy date) —
// never hardcode that one.
export function agedTier(days: number, agedSurchargeDay: number): AgedTier {
  if (days >= agedSurchargeDay) return "surcharge";
  if (days >= 150) return "red";
  if (days >= 120) return "amber";
  return "ok";
}

export type AgedInventoryItem = {
  product: string;
  asin?: string;
  receivedAt?: string;
  lastSaleAt?: string | null;
};

// "No sales in operations.bankroll.cutLossDays" — reference point is the last sale if one ever
// happened, otherwise when the item was received (never sold at all). Insufficient data (no
// receivedAt and no lastSaleAt) never flags — silence, not a false positive.
export function isCutLossCandidate(item: AgedInventoryItem, cutLossDays: number, now: Date): boolean {
  const reference = item.lastSaleAt ?? item.receivedAt;
  if (!reference) return false;
  const days = Math.floor((now.getTime() - new Date(reference).getTime()) / DAY_MS);
  return days >= cutLossDays;
}
