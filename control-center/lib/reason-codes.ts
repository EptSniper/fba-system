// lib/reason-codes.ts — THE reason-code vocabulary for human decisions (Review Queue, CC1).
// Single source shared by the client picker (components/review-queue.tsx) and the server
// validator (app/api/ops/decide/route.ts) so the UI can never offer a code the API rejects
// (Code Review 2026-07-03, reuse finding). Contains no secrets — safe for the client bundle.
// The same strings land in Supabase decisions.reason_code / deal_matches.human_reason
// (migration 005), so renaming a code is a data migration, not a refactor.

export const REASON_CODES = [
  { code: "ip-risk", label: "IP / brand risk" },
  { code: "price-war", label: "Price war" },
  { code: "slow-mover", label: "Slow mover" },
  { code: "bad-match", label: "Bad match" },
  { code: "gated", label: "Gated / ineligible" },
  { code: "thin-margin", label: "Thin margin" },
  { code: "other", label: "Other" },
] as const;

export type ReasonCode = (typeof REASON_CODES)[number]["code"];

const CODE_SET: ReadonlySet<string> = new Set(REASON_CODES.map((r) => r.code));

export function isReasonCode(v: unknown): v is ReasonCode {
  return typeof v === "string" && CODE_SET.has(v);
}
