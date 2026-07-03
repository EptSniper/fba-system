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
  items: { product: string; asin?: string; owned: number; atFba: number; inTransit?: number; status: string }[];
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
  leads: { product: string; asin?: string; roi?: number; status: string }[];
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
  guards?: Record<string, unknown> & { restrictionKeywords?: Record<string, string[]> };
  // Added Phase 1 (Scout + Deal-Finder Expert Upgrade Brief, Prompt 1.1) — category referral
  // rates + the 5-7 offer "goldilocks" bonus. Optional: older bundled snapshots won't have these.
  fees?: { referralRates: Record<string, number>; minReferralFee: number };
  scoring?: { preferredOffers: { min: number; max: number; bonus: number } };
  brands: { friendly: string[]; avoid: string[]; source: string };
  tools: string[];
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

export type Knowledge = {
  updated?: string;
  documents?: { path: string; title: string; type: string }[];
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
