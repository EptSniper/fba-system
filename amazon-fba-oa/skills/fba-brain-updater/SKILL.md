---
name: fba-brain-updater
description: >-
  Safely edits ai-brain.json, the single source of truth for the FBA operation. Use this
  WHENEVER the user wants to change the OA criteria, guards, brand lists, tools, or any
  brain value — "update the brain", "change the BSR cap / ROI / profit threshold", "add
  this brand to friendly/avoid", "Claude distilled new info, update ai-brain.json", "adjust
  the red-flag guards". Both scout/config.py and the control-center load this file, so a
  careless edit breaks the scorer AND the dashboard. This skill validates the JSON,
  preserves the `source:` provenance lines, bumps the `updated` date, and records the change.
  Do NOT use it to edit playbooks/markdown (edit those directly) or to write session notes
  (fba-session-journal).
---

# FBA Brain Updater

`learning-hub/data/ai-brain.json` is loaded by `scout/config.py` (the scorer thresholds) and read by the
control-center. It is the one file where a typo silently changes how every product is judged. Treat edits
like a config migration: validate, preserve structure, and leave an audit trail.

## Procedure

1. **Read first.** Read `learning-hub/data/ai-brain.json` in full and `../../references/oa-criteria.md`. Understand
   the section you're changing (`criteria`, `guards`, `brands`, `tools`, `dealSourcing`, etc.) and the `$comment`/`source`
   notes that explain what loads each value.
2. **Make the minimal change.** Edit only the values requested. Do not reformat the whole file or drop fields.
3. **Preserve provenance.** Every section has a `source:` line (e.g. "SINGLE SOURCE — scout/config.py loads these").
   Keep it. If the change alters where a value is used, update the note to stay true.
4. **Bump `updated`** to today's date (ISO `YYYY-MM-DD`).
5. **Validate.** Confirm the file still parses as JSON before finishing (`python -m json.tool` or equivalent). A broken
   brain file can crash the scorer and the dashboard.
6. **Reconcile downstream.** If a threshold changed, flag that `scout/config.py` consumes it and the bundled
   `control-center/hub-data/ai-brain.json` snapshot may now be stale and need a sync — don't assume the dashboard updates itself.

## Guardrails

- Don't invent business rules. Only encode what the user (or a distilled, cited source) actually specified, and note where it came from.
- Keep the criteria as transparent pre-filters — they are not a buy authorization. Don't add anything that implies auto-buying.
- No secrets in the file.

## Output

Show a tight diff-style summary: which keys changed, old → new, and the provenance/date updates. Confirm the JSON
validated. Then state the downstream follow-up (e.g. "scout will pick this up on next run; sync the control-center
snapshot before deploy") and offer to log it via fba-session-journal.
