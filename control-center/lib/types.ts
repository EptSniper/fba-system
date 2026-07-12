export type Money = {
  source: string;
  updated: string;
  currency: string;
  connected: boolean;
  note?: string;
  summary: {
    invested: number;
    revenue: number;
    fees: number;
    netProfit: number;
    netProfitMTD: number;
    cashInInventory: number;
    pendingPayout: number;
    blendedRoi: number | null;
  };
  recurringCosts: { tool: string; monthly: number; active: boolean }[];
  purchases: Record<string, unknown>[];
  sales: Record<string, unknown>[];
  profitByDay: { date: string; profit: number }[];
};

export type Inventory = {
  source: string;
  updated: string;
  connected: boolean;
  note?: string;
  summary: { unitsOwned: number; atFba: number; inTransit: number; lowStock: number };
  items: {
    product: string;
    asin?: string;
    owned: number;
    atFba: number;
    inTransit?: number;
    status: string;
    // Added for CC2's aged-inventory countdown / cut-loss list (lib/aged-inventory.ts).
    // Optional: no capture flow writes these yet (inventory is genuinely empty today) — both
    // are honest gaps, not omissions, until a real receiving/sale-tracking flow populates them.
    receivedAt?: string;
    lastSaleAt?: string | null;
  }[];
  restock: { product: string; daysLeft: number }[];
};

// Append-only operator ledger. Every manual capture (lead/decision/inventory/outcome)
// is recorded immutably in learning-hub/data/events.jsonl. Decisions and outcomes are the
// human-made ground-truth labels the scout needs before any model can honestly improve.
export type CaptureKind = "lead" | "decision" | "inventory" | "outcome";

export type CaptureEvent = {
  id: string;
  ts: string; // ISO timestamp
  kind: CaptureKind;
  payload: Record<string, unknown>;
};

export type Leads = {
  source: string;
  updated: string;
  pipeline: Record<string, number>;
  leads: { product: string; asin?: string; roi?: number; status: string; notes?: string }[];
};

export type Pick = {
  asin: string;
  title?: string;
  price?: number;
  salesRank?: number;
  estSales?: number;
  offers?: number;
  roi?: number;
  profit?: number;
  score?: number;
  verdict?: string;
  reason?: string;
};

export type Picks = {
  source: string;
  updated: string;
  connected: boolean;
  reason?: string;
  lastRun: string | null;
  picks: Pick[];
};

export type RagCorpus = {
  documents: number;
  chunks: number;
  approxTokens?: number;
  categories?: string[];
  location?: string;
  amazonDocs?: string;
  answers?: string;
};

export type Brain = {
  updated: string;
  model: string;
  criteria: Record<string, unknown>;
  // ML/collector configuration. Optional because older bundled snapshots can legitimately
  // predate these fields; callers must render an unavailable state rather than inventing a
  // Keepa plan rate. `refillRatePerMinute` is non-secret plan telemetry, not a spend limit.
  learning?: {
    tokenBudget?: {
      refillRatePerMinute?: number;
      [key: string]: unknown;
    };
    sampling?: Record<string, unknown>;
    [key: string]: unknown;
  };
  guards?: Record<string, unknown> & { restrictionKeywords?: Record<string, string[]> };
  // Added Phase 1 (Scout + Deal-Finder Expert Upgrade Brief, Prompt 1.1) — category referral
  // rates + the 5-7 offer "goldilocks" bonus. Optional: older bundled snapshots won't have these.
  fees?: {
    referralRates: Record<string, number>;
    minReferralFee: number;
    fuelSurcharge?: number;
    prepCost?: number;
    // Price-banded rates (Code Review 2026-07-02, Finding CS6) — e.g. grocery is really 8% at
    // or below priceThreshold, 15% above it; referralRates.grocery alone is the wrong flat rate
    // once price exceeds the threshold.
    bandedRates?: Record<string, { priceThreshold: number; atOrBelowThreshold: number; aboveThreshold: number }>;
  };
  scoring?: {
    preferredOffers: { min: number; max: number; bonus: number };
    // Single-sourced thresholds (R3 nits) — deal-analyzer.tsx used to hardcode these
    // independently of ai-brain.json's own scoring.worstCaseLossBarUsd/marginHealthThreshold.
    worstCaseLossBarUsd?: number;
    marginHealthThreshold?: number;
  };
  brands: { friendly: string[]; avoid: string[]; source: string };
  tools: string[];
  // Operational doctrine + 2026 policy facts (Scout Agent Build Plan sec 3.5-3.8) — informational
  // only, not consumed by scoring math. Added Code Review 2026-07-02, Finding CS3: this data
  // existed in ai-brain.json but was never rendered anywhere in the control-center.
  operations?: {
    seasonal2026?: {
      primeDayWindow?: { start: string; end: string; role: string };
      backToSchoolBuyWindow?: string;
      q4ArrivalDeadline?: string;
      q4StopSpeculativeBuysAfterWeek?: number;
      toysBuyWindows?: string[];
      januaryReturnsWave?: boolean;
      biasQ4TowardLowReturnCategories?: boolean;
    };
    bankroll?: {
      cashReservePct?: number;
      cutLossDays?: number;
      agedSurchargeDay?: number;
      buckets?: string[];
    };
  };
  policy2026?: {
    payoutHoldDaysAfterDelivery?: number;
    payoutHoldEffective?: string;
    comminglingEnded?: boolean;
    comminglingEndedEffective?: string;
    feeIncreasePerUnit?: number;
    feeIncreaseEffective?: string;
  };
  dealSourcing?: {
    principle?: string;
    retailers?: string[];
    dealAggregatorAPIs?: string[];
    dealTools?: string[];
    ipRisk?: string;
    status?: string;
  };
  knowledge: {
    transcripts: number;
    playbooks: string[];
    fundamentals: number;
    lastDistilled: string;
    ragCorpus?: RagCorpus;
  };
  ingestionLog: { date: string; type: string; item: string; effect: string }[];
};

export type RagManifestSource = {
  id: string;
  title: string;
  category: string;
  access: string;
  status: string;
};

export type RagManifest = {
  updated?: string;
  marketplace?: string;
  compliance?: string;
  categories?: string[];
  sources: RagManifestSource[];
};

export type Deals = {
  source: string;
  updated: string;
  connected: boolean;
  reason?: string;
  principle: string;
  watchedRetailers: string[];
  today: { retailer: string; item: string; dealPrice?: number; amazonPrice?: number; roi?: number; type?: string }[];
};
