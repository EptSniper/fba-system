// lib/supabase-server.ts — SERVER-ONLY read/write layer over the scout's Supabase business
// tables (CC1: runs, leads, deals, deal_matches, search_log). Plain PostgREST REST calls, not
// the @supabase/supabase-js SDK — matches scout/db.py's own approach (see scout/db.py's
// _headers()/_post()), avoids a new dependency for a handful of simple queries, and keeps the
// two codebases' Supabase behavior (retry-free, honest-degrade-on-failure) consistent.
//
// NEVER import this from a "use client" component — SUPABASE_SERVICE_ROLE_KEY must never
// reach the browser bundle. Only import from route.ts files (Node runtime) or server
// components (the default for files with no "use client" directive). Operator access to
// everything that imports this is enforced by middleware.ts (Basic auth).
//
// Every read function returns `null` on ANY failure (missing config, network error, non-2xx
// response) — never throws, never returns a fabricated empty array that could be confused
// with "genuinely queried and found zero rows". Callers must render "not connected" / "could
// not reach Supabase" for null, and a real (possibly empty) EmptyState for [].
import type { LeadExplanation } from "./explain";

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

export function supabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_SERVICE_ROLE_KEY);
}

function headers(extra?: Record<string, string>): Record<string, string> {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY!,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

async function supaGet<T>(pathAndQuery: string): Promise<T[] | null> {
  if (!supabaseConfigured()) return null;
  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/${pathAndQuery}`, {
      headers: headers(),
      cache: "no-store",
    });
    if (!res.ok) {
      console.error(`[supabase-server] GET ${pathAndQuery} -> HTTP ${res.status}`);
      return null;
    }
    return (await res.json()) as T[];
  } catch (err) {
    console.error(`[supabase-server] GET ${pathAndQuery} failed:`, err instanceof Error ? err.message : err);
    return null;
  }
}

async function supaWrite(
  method: "POST" | "PATCH",
  pathAndQuery: string,
  body: Record<string, unknown>,
  extraHeaders?: Record<string, string>,
): Promise<boolean> {
  if (!supabaseConfigured()) return false;
  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/${pathAndQuery}`, {
      method,
      headers: headers({ Prefer: "return=minimal", ...extraHeaders }),
      body: JSON.stringify(body),
    });
    if (!res.ok) console.error(`[supabase-server] ${method} ${pathAndQuery} -> HTTP ${res.status}`);
    return res.ok;
  } catch (err) {
    console.error(`[supabase-server] ${method} ${pathAndQuery} failed:`, err instanceof Error ? err.message : err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Reads — shapes mirror scout/db.py's migrations exactly (001/003/004/005).
// ---------------------------------------------------------------------------

export type SupabaseRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string; // running | success | failed
  asins_scanned: number | null;
  candidates_gated: number | null;
  leads_upserted: number | null;
  tokens_consumed: number | null;
  tokens_left_end: number | null;
  error_summary: string | null;
  host: string | null;
  // Migration 013 (2026-07-09) — per-tier token split + the backtest tier's own rows/ASINs-
  // sampled counts. Null on any run recorded before this migration landed; a real collector run
  // always sets tier1/tier2_tokens (tier3_tokens/backtest_* stay null if tier 3 was skipped).
  tier1_tokens: number | null;
  tier2_tokens: number | null;
  tier3_tokens: number | null;
  backtest_rows_written: number | null;
  backtest_asins_sampled: number | null;
};

export function getRecentRuns(limit = 14): Promise<SupabaseRun[] | null> {
  return supaGet<SupabaseRun>(`runs?order=started_at.desc&limit=${limit}`);
}

// Migration 013 (2026-07-09) — one row per scout/train_ranker.py training run. The durable,
// queryable record of champion/challenger AUC over time that ranker-report.md (cloud runs never
// commit their copy back — train-ranker.yml's own header comment) and the Discord post
// (human-readable, not queryable) never were.
export type SupabaseRankerRun = {
  id: number;
  trained_at: string;
  host: string | null;
  refused: boolean;
  refusal_reason: string | null;
  row_count: number | null;
  train_rows: number | null;
  train_asins: number | null;
  val_rows: number | null;
  val_asins: number | null;
  champion_auc: number | null;
  champion_winners_in_top: number | null;
  challenger_auc: number | null;
  challenger_winners_in_top: number | null;
  verdict: string | null;
  by_tier: Record<string, { total: number; positive: number; negative: number }> | null;
  by_source: Record<string, { n: number; auc: number | null }> | null;
};

export function getRankerRuns(limit = 60): Promise<SupabaseRankerRun[] | null> {
  return supaGet<SupabaseRankerRun>(`ranker_runs?order=trained_at.desc&limit=${limit}`);
}

// A lean projection of backtest_rows for the collection-growth chart — deliberately excludes
// features_snapshot (a large JSONB blob per row, irrelevant to a growth/composition chart).
// Current corpus size (hundreds of rows) makes a full-table pull-and-aggregate-in-Node fine;
// re-evaluate (a Postgres view or an RPC that aggregates server-side) if this ever approaches
// DATA_ENGINE_PLAN's ~50k-row target, where even these 4 columns would be a multi-MB payload.
export type SupabaseBacktestRowLite = {
  created_at: string;
  sample_source: string | null;
  label_quality: string;
  would_have_profited: boolean | null;
};

export function getBacktestRowsForChart(limit = 20000): Promise<SupabaseBacktestRowLite[] | null> {
  return supaGet<SupabaseBacktestRowLite>(
    `backtest_rows?select=created_at,sample_source,label_quality,would_have_profited&order=created_at.asc&limit=${limit}`,
  );
}

export type SupabaseLead = {
  id: number;
  asin: string | null;
  title: string | null;
  brand: string | null;
  category: string | null;
  buy_cost: number | null;
  sell_price: number | null;
  profit: number | null;
  roi: number | null;
  monthly_sales: number | null;
  bsr: number | null;
  offer_count: number | null;
  amazon_present: boolean | null;
  score: number | null;
  verdict: string | null; // scout's OA verdict: "review" (surfaced) | "pass" (rejected)
  reason: string | null;
  found_via: string | null;
  created_at: string;
  explanation: LeadExplanation;
};

export function getSupabaseLeads(limit = 200): Promise<SupabaseLead[] | null> {
  return supaGet<SupabaseLead>(`leads?order=created_at.desc&limit=${limit}`);
}

// The Review Queue's lead set, selected SERVER-SIDE (Code Review 2026-07-03, Findings #3/#4):
// verdict=review AND no decision recorded yet, via PostgREST's left-join anti-join
// (decisions=is.null — verified live against this project's PostgREST version). Doing this in
// one filtered query instead of "fetch newest 300 of any verdict, subtract a separately
// fetched decided-id set" fixes two real bugs at once: older review leads could fall out of
// the 300-row window while the digest still counted them, and the unbounded decisions fetch
// would silently truncate at PostgREST's max-rows cap, resurrecting already-decided leads.
export function getUndecidedReviewLeads(limit = 300): Promise<SupabaseLead[] | null> {
  return supaGet<SupabaseLead>(
    `leads?select=*,decisions!left(lead_id)&decisions=is.null&verdict=eq.review&order=created_at.desc&limit=${limit}`,
  );
}

export type OpenBuyRow = {
  id: number;
  buy_cost: number | null;
  decisions: { bought_qty: number | null; suggested_qty: number | null }[];
};

// CC2's capital & safety cockpit: leads with a "buy" decision and no outcome recorded yet —
// capital still tied up in an open buy. decisions and outcomes have no direct FK to each
// other (both reference leads independently), so PostgREST can't embed one on the other
// directly; both are embedded on leads instead (verified live against this project).
export function getOpenBuyCommitments(limit = 500): Promise<OpenBuyRow[] | null> {
  return supaGet(
    `leads?select=id,buy_cost,decisions!inner(decision,bought_qty,suggested_qty),outcomes!left(lead_id)` +
      `&decisions.decision=eq.buy&outcomes.lead_id=is.null&limit=${limit}`,
  );
}

export function committedCapital(rows: OpenBuyRow[]): number {
  // Defensive dedup by lead id: if a lead somehow has more than one "buy" decision row, the
  // inner-join embed would fan it out into duplicate top-level rows — count each lead once.
  const seenLeadIds = new Set<number>();
  let total = 0;
  for (const row of rows) {
    if (seenLeadIds.has(row.id)) continue;
    seenLeadIds.add(row.id);
    const qty = row.decisions[0]?.bought_qty ?? row.decisions[0]?.suggested_qty ?? 1;
    total += (row.buy_cost ?? 0) * qty;
  }
  return total;
}

export type SupabaseDeal = {
  id: number;
  retailer: string;
  source: string;
  sku: string | null;
  title_raw: string;
  brand: string | null;
  price_current: number | null;
  price_original: number | null;
  discount_pct: number | null;
  url: string | null;
  first_seen: string;
  last_seen: string;
  status: string; // new | matched | discarded
};

export function getSupabaseDeals(limit = 200): Promise<SupabaseDeal[] | null> {
  return supaGet<SupabaseDeal>(`deals?order=last_seen.desc&limit=${limit}`);
}

export type DealMatch = {
  id: number;
  deal_id: number;
  asin: string | null;
  confidence: number | null;
  method: string | null;
  pack_match: boolean | null;
  llm_reason: string | null;
  human_verdict: string | null; // approve | reject | null
  created_at: string;
};

// Only the ones still awaiting a human verdict — that's the queue-relevant set.
export function getPendingDealMatches(limit = 200): Promise<DealMatch[] | null> {
  return supaGet<DealMatch>(`deal_matches?human_verdict=is.null&order=created_at.desc&limit=${limit}`);
}

export type SearchLogRow = {
  id: number;
  brand: string;
  last_run_at: string | null;
  rerun_after_days: number;
};

export function getSearchLogRows(limit = 500): Promise<SearchLogRow[] | null> {
  return supaGet<SearchLogRow>(`search_log?order=brand.asc&limit=${limit}`);
}

// How many brands are due for a re-mining run — same rule as scout/search_log.py: never run,
// or last run older than rerun_after_days. Rendered on the Today page's Runs health panel
// (CC1 item 2's "searches due").
export function searchesDueCount(rows: SearchLogRow[], now = new Date()): number {
  return rows.filter((r) => {
    if (!r.last_run_at) return true;
    const ageDays = (now.getTime() - new Date(r.last_run_at).getTime()) / 86_400_000;
    return ageDays >= r.rerun_after_days;
  }).length;
}

// The nightly deal watch's "look here first" hints (migration 007, TOP100_DEAL_WATCH_PLAN.md
// T3). FRESH only (expires_at > now, filtered server-side), strongest first — the scout
// consumes the same rows as its first discovery pass, and the Deals page shows the operator
// what's steering it. Read-only; the control-center never writes hints.
export type DealHint = {
  id: number;
  brand: string | null;
  store: string | null;
  category: string | null;
  strength: number | null;
  last_seen: string;
  expires_at: string;
};

export function getDealHints(limit = 50): Promise<DealHint[] | null> {
  const nowIso = new Date().toISOString();
  return supaGet<DealHint>(
    `deal_hints?expires_at=gt.${nowIso}&order=strength.desc&limit=${limit}`,
  );
}

// ---------------------------------------------------------------------------
// Writes — human-only, from the Review Queue's Approve/Reject/Watch actions. Mirrors
// scout/db.py's log_decision()/queue_brand_search() shapes exactly, so this is a SECOND
// writer into the SAME tables scout already writes, not a new parallel schema.
//
// human_approved: true is legitimate here because middleware.ts gates every request behind
// operator Basic auth (and refuses to serve a Supabase-configured deployment without auth) —
// it is NOT an unenforced comment-level claim.
// ---------------------------------------------------------------------------

export type LeadDecisionInput = {
  leadId: number;
  decision: "buy" | "wait" | "pass"; // mirrors scout/db.py's decisions.decision values (a
  // Review Queue "watch" maps to "wait" — matches DECISIONS elsewhere in this app)
  reason: string; // reason code + optional free text, joined by the caller (human-readable)
  reasonCode: string; // the structured code alone — decisions.reason_code (migration 005)
  brand?: string | null; // for the brand-growth loop on "buy" (scout/db.py log_decision parity)
};

export async function recordLeadDecision(input: LeadDecisionInput): Promise<boolean> {
  const row: Record<string, unknown> = {
    lead_id: input.leadId,
    decision: input.decision,
    reason: input.reason,
    reason_code: input.reasonCode,
    human_approved: true,
  };
  let ok = await supaWrite("POST", "decisions", row);
  if (!ok) {
    // Migration 005 (decisions.reason_code) may not be applied yet — a decision must never be
    // lost to a missing optional column. Retry once without it; the code still survives in
    // the reason text ("code: text").
    delete row.reason_code;
    ok = await supaWrite("POST", "decisions", row);
    if (ok) console.error("[supabase-server] decisions.reason_code write failed — apply scout/db/migrations/005_decision_reasons.sql");
  }
  // Approved buys feed the brand-growth loop, same as scout/db.py's log_decision() —
  // without this, Review Queue approvals silently starve brand re-mining (Finding #6).
  if (ok && input.decision === "buy" && input.brand) await queueBrandSearch(input.brand);
  return ok;
}

// Mirrors scout/db.py queue_brand_search(): lowercase-normalized brand, ignore-duplicates on
// the brand unique index, never overwrites an existing row's last_run_at.
export async function queueBrandSearch(brand: string): Promise<boolean> {
  const normalized = brand.trim().toLowerCase();
  if (!normalized) return false;
  return supaWrite(
    "POST",
    "search_log?on_conflict=brand",
    { brand: normalized, query_params: null },
    { Prefer: "return=minimal,resolution=ignore-duplicates" },
  );
}

export async function recordDealMatchVerdict(
  dealMatchId: number,
  verdict: "approve" | "reject",
  reason: string,
): Promise<boolean> {
  const row: Record<string, unknown> = { human_verdict: verdict, human_reason: reason };
  let ok = await supaWrite("PATCH", `deal_matches?id=eq.${dealMatchId}`, row);
  if (!ok) {
    // Same migration-005 fallback as recordLeadDecision — the verdict itself must land even
    // if the human_reason column doesn't exist yet.
    delete row.human_reason;
    ok = await supaWrite("PATCH", `deal_matches?id=eq.${dealMatchId}`, row);
    if (ok) console.error("[supabase-server] deal_matches.human_reason write failed — apply scout/db/migrations/005_decision_reasons.sql");
  }
  return ok;
}
