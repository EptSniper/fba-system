// lib/explain.ts — one-line summary of a scout lead's explanation JSONB (scoring.explain_oa()
// output stored in leads.explanation). Shared by app/leads/page.tsx and
// components/review-queue.tsx — the two previously carried separate copies that had ALREADY
// drifted (the Review Queue's omitted the hard-reject reason, hiding it exactly where the
// human decision gets made — Code Review 2026-07-03). No secrets; safe for the client bundle.

// analyst_note is scout/analyst.py's optional LLM second-opinion pass (Scout Agent Build Plan
// Prompt S1) merged into this same JSONB column, never consumed by scoring — advisory only.
export type AnalystNote = {
  status?: string;
  disagrees_with_rules?: boolean;
  qualitative_risk?: string;
  narrative?: string;
  unknowns?: string[];
  memory_used?: boolean;
} | null;

export type LeadExplanation = {
  scored_checks?: unknown[];
  adjustments?: unknown[];
  hard_reject?: string | null;
  analyst_note?: AnalystNote;
} | null;

export function explainSummary(explanation: LeadExplanation): string | null {
  if (!explanation) return null;
  const checks = (explanation.scored_checks as { passed?: boolean }[] | undefined) ?? [];
  const passed = checks.filter((c) => c.passed).length;
  const adj = (explanation.adjustments as unknown[] | undefined)?.length ?? 0;
  const parts = [`${passed}/${checks.length} checks passed`];
  if (adj) parts.push(`${adj} adjustment${adj === 1 ? "" : "s"}`);
  if (explanation.hard_reject) parts.push(`hard reject: ${explanation.hard_reject}`);
  return parts.join(" · ");
}
