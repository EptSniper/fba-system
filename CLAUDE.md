# Amazon FBA collaboration instructions

Before working on this project, read [`AI_COLLABORATION_JOURNAL.md`](AI_COLLABORATION_JOURNAL.md) and `learning-hub/tracking/session-archive.md`.

For every session:

- append an in-depth dated entry to `AI_COLLABORATION_JOURNAL.md` covering the request, files inspected and changed, rationale, checks/results, limitations, and exact next safe step;
- never record secrets or full credentials in the journal/docs/tracked files; API keys/tokens go only in `API_KEYS.env` (the central registry) or the component `.env` a script reads — both gitignored. When the user provides a new key, save it there;
- distinguish implemented, tested, configured, deployed, and planned work;
- treat `learning-hub/data/ai-brain.json` as the structured OA brain, while preferring current executable code and newer timestamped evidence when files conflict;
- preserve human approval for purchases and external actions; never auto-buy or move money.

## Skills — check the team before you act (applies to every AI: Cowork, the scheduled task, Claude Code)

This repo ships a 24-skill expert plugin in `amazon-fba-oa/` (`fba-*`). **Standing rule:** before any
non-trivial task, confirm the action matches the goal, then scan the skills index — if the task matches or is
even related to a skill, **use it** (open `amazon-fba-oa/skills/<name>/SKILL.md` and follow it). Chain skills
when several apply; only improvise when nothing fits. The skills encode the rules the code must obey and several
write into the files the code reads (`ai-brain.json`, the RAG corpus, the trackers), so don't re-derive them.

The canonical routing index (what to use when) and the full engineering guide:

@SKILLS_INDEX.md

@CLAUDE_CODE_GUIDE.md

## Codex bootstrap note — 2026-06-27

Codex created this file after the Windows patch helper repeatedly failed to refresh the pre-existing `AGENTS.md` and `learning-hub/tracking/session-archive.md` files in the OneDrive workspace. Those files were intentionally left unchanged rather than replaced unsafely. The complete audit and session record are in `AI_COLLABORATION_JOURNAL.md`.
