# Guardrails — shared across the skill suite

Every skill in this plugin operates under these rules. They exist because the project's whole
premise is an honest, auditable system that a beginner can trust — not a confident-sounding one.

## 1. Separate the two questions, always

A buy decision has two independent failure modes. Never let a "yes" on one imply a "yes" on the other:

- **Am I allowed?** Account-specific eligibility, ungating, IP/brand risk, hazmat, meltable,
  expiration, condition, FBA eligibility, variation issues. Checked in Seller Central / SP-API.
- **Can it profit?** Keepa history, SellerAmp math, true landed cost, Amazon fees, offer/price
  trends, Buy Box rotation, worst-case price.

A product can be highly profitable and still be un-sellable for this account, and vice versa. Report
on both axes separately.

## 2. Humans approve purchases and external actions

No skill auto-buys, lists, moves money, or takes an irreversible external action. Skills recommend,
calculate, and explain. The final buy/list/spend decision is the operator's. Output a VERDICT of
BUY / NO-BUY / REVIEW as a recommendation, never an executed action.

## 3. Honesty about status

Distinguish **implemented**, **tested**, **configured**, **deployed**, and **planned** — these words
are not interchangeable. Don't present estimated or disconnected data as live. Honest empty states are
correct; inventing numbers to look complete is a defect.

## 4. No secrets, ever

Never write API keys, tokens, passwords, service-role keys, or full webhook URLs into any file,
journal entry, or output. Credentials live server-side in untracked `.env` files only.

## 5. Source-of-truth order when files disagree

1. Real, timestamped business/account data (Amazon, Keepa, Supabase, observed outcomes).
2. Current executable code and passing tests (`scout/`, `scout_pro/`, `knowledge-rag/`, `control-center/`).
3. Live structured data in `learning-hub/data/`, especially `ai-brain.json`.
4. The generated RAG corpus.
5. Current playbooks/specs in `learning-hub/`.
6. Historical session notes / older READMEs (rationale, but may be stale).
7. Raw transcripts and creator claims (practitioner input, not verified Amazon policy).

## 6. Cite and stay inspectable

When a claim comes from a project file or the knowledge base, point to where it came from. Prefer
maintained playbooks/specs over raw transcript opinion. Don't invent bridging prose that sounds
authoritative but isn't grounded.
