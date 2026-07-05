// lib/anthropic-draft.ts — SERVER-ONLY. Drafts a proposed ai-brain.json edit for ONE brain
// proposal finding (the "approve -> draft immediately, human confirms" flow). Mirrors
// scout/analyst.py's call style (same default model, same "never invent, cite your evidence,
// say so honestly when you can't" posture) but is a completely separate call site — this one
// PROPOSES A BRAIN EDIT, analyst.py only ever attaches an advisory note to a lead.
//
// HARD SAFETY BOUNDARY (enforced here, not just in the prompt): drafting is only attempted
// when propose_updates.py itself already identified a specific `ai_brain_key` for the finding.
// Most proposals don't (ai_brain_key: null — qualitative findings like "no run telemetry
// yet"), and the model is NEVER asked to invent a key to edit — the fba-brain-updater skill's
// own rule ("Don't invent business rules... only encode what a distilled, cited source
// actually specified") applies just as much to an automated draft as a human-typed one.

const MODEL = process.env.ANTHROPIC_DRAFT_MODEL || "claude-sonnet-5";
const MAX_TOKENS = 512;

const SYSTEM_PROMPT = (
  "You are drafting ONE proposed edit to a single key in ai-brain.json, the source-of-truth " +
  "config for an Amazon online-arbitrage sourcing operation. You are given a finding from an " +
  "automated proposal-generator, the exact key it names, and that key's CURRENT value. Draft " +
  "the precise NEW value for that key ONLY — never a different key, never a restructuring.\n\n" +
  "Hard rules: (1) Never invent a business rule beyond what the finding's own evidence " +
  "supports — a small sample size finding should produce a small, conservative change, not an " +
  "aggressive one. (2) Preserve the value's type and shape (an array stays an array; add/" +
  "remove elements, don't replace with a scalar). (3) If the evidence is too weak, ambiguous, " +
  "or doesn't cleanly map to a specific new value, set actionable=false and explain why — " +
  "this is the CORRECT answer far more often than a confident guess. (4) Cite the specific " +
  "evidence (sample size, confidence label, the observed pattern) in your rationale.\n\n" +
  "Call submit_draft with your answer."
);

const DRAFT_TOOL = {
  name: "submit_draft",
  description: "Submit a drafted edit to the named ai-brain.json key, or decline with a reason.",
  input_schema: {
    type: "object",
    properties: {
      actionable: {
        type: "boolean",
        description: "False if the evidence is too weak/ambiguous to responsibly draft a specific new value.",
      },
      proposed_value_json: {
        type: "string",
        description: "The FULL new value for the key, JSON-encoded as a string (e.g. '[\"BrandA\",\"BrandX\"]', '75', 'true'). Required when actionable is true; omit otherwise.",
      },
      rationale: { type: "string", description: "<=100 words. Cite the specific evidence from the finding." },
    },
    required: ["actionable", "rationale"],
  },
};

export type DraftResult =
  | { status: "unavailable"; reason: string }
  | { status: "not_actionable"; reason: string }
  | { status: "error"; reason: string }
  | { status: "ok"; proposedValue: unknown; rationale: string };

export type ProposalFacts = {
  kind: string;
  finding: string;
  sampleSize: number | null;
  confidence: string | null;
  brainKey: string | null;
};

export async function draftProposalEdit(proposal: ProposalFacts, currentValue: unknown): Promise<DraftResult> {
  if (!proposal.brainKey) {
    return { status: "not_actionable", reason: "propose_updates.py didn't identify a specific ai-brain.json key for this finding — drafting is only attempted when one is." };
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return { status: "unavailable", reason: "ANTHROPIC_API_KEY is not configured (see HUMAN_TODO.md item #1)." };
  }

  const input = {
    finding: proposal.finding,
    kind: proposal.kind,
    sample_size: proposal.sampleSize,
    confidence: proposal.confidence,
    ai_brain_key: proposal.brainKey,
    current_value: currentValue,
  };

  let response: Response;
  try {
    response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: MAX_TOKENS,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: JSON.stringify(input) }],
        tools: [DRAFT_TOOL],
        tool_choice: { type: "tool", name: "submit_draft" },
      }),
    });
  } catch (e) {
    return { status: "error", reason: `Request failed: ${e instanceof Error ? e.message : String(e)}` };
  }

  if (!response.ok) {
    return { status: "error", reason: `Anthropic API returned HTTP ${response.status}.` };
  }

  let body: { content?: { type: string; name?: string; input?: Record<string, unknown> }[] };
  try {
    body = await response.json();
  } catch {
    return { status: "error", reason: "Could not parse the Anthropic API response." };
  }

  const block = (body.content ?? []).find((b) => b.type === "tool_use" && b.name === "submit_draft");
  if (!block?.input) {
    return { status: "error", reason: "Model did not return the expected submit_draft tool call." };
  }

  const draftInput = block.input as { actionable?: boolean; proposed_value_json?: string; rationale?: string };
  const rationale = draftInput.rationale ?? "(no rationale given)";
  if (!draftInput.actionable) {
    return { status: "not_actionable", reason: rationale };
  }

  let proposedValue: unknown;
  try {
    proposedValue = JSON.parse(draftInput.proposed_value_json ?? "");
  } catch {
    return { status: "error", reason: "Model marked the edit actionable but proposed_value_json didn't parse as JSON." };
  }

  return { status: "ok", proposedValue, rationale };
}
