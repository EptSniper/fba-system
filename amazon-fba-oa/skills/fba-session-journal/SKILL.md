---
name: fba-session-journal
description: >-
  Writes the mandatory session entry in AI_COLLABORATION_JOURNAL.md for the Amazon FBA
  project. Use this AT THE END of any working session that changed files, AND whenever the
  user says "log this session", "update the journal", "write the handoff", "record what we
  did", or "add a journal entry". The project's CLAUDE.md/AGENTS.md require a dated, in-depth
  entry every session so Claude and Codex never repeat or hide work. It enforces the exact
  entry structure, the implemented/tested/configured/deployed/planned distinction, the
  no-secrets rule, and an exact next-safe-step. Use it proactively before wrapping up. Do
  NOT use it for Amazon product leads (that is fba-lead-capture) or ai-brain edits
  (fba-brain-updater).
---

# FBA Session Journal

`AI_COLLABORATION_JOURNAL.md` is the durable handoff between AI sessions — the workspace root isn't always
a git repo, so this journal *is* the change history. A vague or dishonest entry causes the next session to
repeat work or trust something that was never tested. Your job is to produce an entry that a different AI
could act on tomorrow with zero context loss.

## Before writing

Read the top of `AI_COLLABORATION_JOURNAL.md` (the "How every AI must use this file" rules and the
source-of-truth hierarchy) and the most recent entry, so the new entry matches house style and goes
**newest-first** in the Session log. Also read `../../references/guardrails.md`.

## Required structure (append newest-first under "## Session log")

Use a dated heading like `### YYYY-MM-DD — [Agent] Session NN: <short title>` then these sections:

- **Request and constraints** — what the user asked, and any limits they set (e.g. "no paid API").
- **Evidence inspected** — files read, commands run, what was actually examined (not assumed).
- **Implementation / changes** — what changed and the rationale (the *why*, not just the *what*).
- **Files changed** — explicit list (new vs modified).
- **Verification** — what was checked and the result, using precise status words (see below).
- **Limitations / honest status** — what is NOT done, NOT tested, or still assumed.
- **Exact next safe step** — the single most valuable, lowest-risk next action.

## The status words are not interchangeable

State precisely which of these applies to each piece of work, and never upgrade one to another:
**implemented** (code written) · **tested** (actually run, with the result) · **configured** (settings/keys placed) ·
**deployed** (live somewhere) · **planned** (intended only). "Tests pass" must mean you ran them this session;
if you only wrote them, say so.

## Hard rules

- **No secrets.** Never write API keys, tokens, passwords, service-role keys, or full webhook URLs.
- Distinguish real outcomes from architectural intentions. If an older doc conflicts with current code, record the
  conflict rather than silently "fixing" status.
- Keep claims inspectable: point to files/commands a reader can re-run.

## Output

Append the formatted entry directly to `AI_COLLABORATION_JOURNAL.md` (newest-first). Then show the user a 3–5 line
summary of what you logged and the recorded next safe step. Offer to also add the short cross-pointers in
`AGENTS.md` / `learning-hub/tracking/session-archive.md` if those are part of the session.
