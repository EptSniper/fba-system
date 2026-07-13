// lib/queue-server.ts — SERVER-ONLY. The Review Queue's merge/triage logic (CC1), shared by
// app/queue/page.tsx (initial server-rendered load) and app/api/ops/queue/route.ts (the same
// data as JSON, for any future client-side refresh) — a single source so the two can never
// drift apart.
import {
  getPendingDealMatches,
  getUndecidedReviewLeads,
  supabaseConfigured,
} from "./supabase-server";
import type { LeadExplanation } from "./explain";

export type QueueLeadItem = {
  kind: "lead";
  id: number;
  priority: number;
  asin: string | null;
  title: string | null;
  brand: string | null;
  category: string | null;
  buyCost: number | null;
  sellPrice: number | null;
  profit: number | null;
  roi: number | null;
  monthlySales: number | null;
  bsr: number | null;
  offerCount: number | null;
  amazonPresent: boolean | null;
  score: number | null;
  reason: string | null;
  explanation: LeadExplanation;
  createdAt: string;
};

export type QueueDealMatchItem = {
  kind: "deal_match";
  id: number;
  priority: number;
  dealId: number;
  asin: string | null;
  confidence: number | null;
  method: string | null;
  packMatch: boolean | null;
  llmReason: string | null;
  createdAt: string;
};

export type QueueItem = QueueLeadItem | QueueDealMatchItem;

// Priority is a NORMALIZED (0-1) APPROXIMATION of urgency, computed independently for each
// item type then merged — NOT the same computation as scout/scoring.py's real triage_score()
// (expected_profit * monthly_velocity / buy_cost at a stressed price). Re-deriving that exact
// formula here would create a second, driftable copy of scout's own scoring logic (the thing
// the "single source of truth" rule exists to prevent). This is a documented, honest stand-in:
// leads rank by a simple profit*velocity proxy; deal-matches rank by UNCERTAINTY (lowest
// confidence first — those most need a human's judgment). Real parity would mean scout
// persisting its own triage_score onto the lead row for this to read directly — a natural
// follow-up, not done here.
function normalize(values: number[]): (v: number) => number {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max === min) return () => 0.5;
  return (v: number) => (v - min) / (max - min);
}

export async function buildQueue(): Promise<{ connected: boolean; items: QueueItem[] }> {
  if (!supabaseConfigured()) return { connected: false, items: [] };

  // Queue-worthy leads: scout's OA verdict is "review" AND no decision recorded yet — both
  // conditions applied SERVER-SIDE in one query (Code Review 2026-07-03, Findings #3/#4: the
  // old fetch-300-of-anything-then-subtract approach dropped older review leads out of the
  // window and broke once the decisions table outgrew PostgREST's max-rows cap).
  const [undecidedReviewLeads, pendingMatches] = await Promise.all([
    getUndecidedReviewLeads(300),
    getPendingDealMatches(200),
  ]);
  if (undecidedReviewLeads === null || pendingMatches === null) {
    return { connected: false, items: [] };
  }
  const leadScores = undecidedReviewLeads.map((l) => (l.profit ?? 0) * (l.monthly_sales ?? 1));
  const leadNorm = normalize(leadScores);
  const leadItems: QueueLeadItem[] = undecidedReviewLeads.map((l, i) => ({
    kind: "lead",
    id: l.id,
    priority: leadNorm(leadScores[i]),
    asin: l.asin,
    title: l.title,
    brand: l.brand,
    category: l.category,
    buyCost: l.buy_cost,
    sellPrice: l.sell_price,
    profit: l.profit,
    roi: l.roi,
    monthlySales: l.monthly_sales,
    bsr: l.bsr,
    offerCount: l.offer_count,
    amazonPresent: l.amazon_present,
    score: l.score,
    reason: l.reason,
    explanation: l.explanation,
    createdAt: l.created_at,
  }));

  const matchScores = pendingMatches.map((m) => 1 - (m.confidence ?? 0));
  const matchNorm = normalize(matchScores);
  const matchItems: QueueDealMatchItem[] = pendingMatches.map((m, i) => ({
    kind: "deal_match",
    id: m.id,
    priority: matchNorm(matchScores[i]),
    dealId: m.deal_id,
    asin: m.asin,
    confidence: m.confidence,
    method: m.method,
    packMatch: m.pack_match,
    llmReason: m.llm_reason,
    createdAt: m.created_at,
  }));

  const items: QueueItem[] = [...leadItems, ...matchItems].sort((a, b) => b.priority - a.priority);
  return { connected: true, items };
}
