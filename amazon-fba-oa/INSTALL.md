# Installing the amazon-fba-oa skills

You have two ways to get these into Claude. The skills already exist as `.md` files (you can read/edit
them any time in `amazon-fba-oa/skills/<name>/SKILL.md`). To make Claude actually *use* them, register
them under Settings.

## Option A — install the whole plugin (recommended, all 24 at once)

This folder is a self-contained plugin with a `.claude-plugin/marketplace.json`, so Claude can install
the entire set in one step.

1. Open Claude desktop → **Settings → Capabilities** (the "Customization / Skills" area).
2. Choose to **add a plugin / marketplace from a local folder**.
3. Point it at this folder:
   `C:\Users\ahmet\OneDrive\Belgeler\Claude\Projects\Amazon FBA\amazon-fba-oa`
4. Install the **amazon-fba-oa** plugin. All 24 `fba-` skills now appear in your skills list and will
   trigger automatically when relevant (e.g. ask "buy or pass on this ASIN?" → `fba-deal-analyst`).

To update later: edit any `SKILL.md`, bump the version in `.claude-plugin/plugin.json`, and refresh.

## Option B — install one skill at a time

If you only want specific skills, each `skills/<name>/` folder is a standalone skill. Zip the folder with
a `.skill` extension (e.g. `fba-deal-analyst.skill`) and open it — Claude shows a **Save skill** install
button. Repeat per skill. (Option A is easier for the full set.)

## Verify it worked

After installing, start a new session in this project and try a trigger phrase:

- "run the gates on this ASIN: sells $30, cost $14, BSR 25k, 4 sellers, 3P buy box, Crayola" → should invoke **fba-deal-analyst**
- "where should I source today?" → **fba-sourcing-scout**
- "log this session" → **fba-session-journal**

If a skill doesn't trigger, it's usually because the request was a one-liner Claude can answer directly —
the skills are tuned to fire on substantive, multi-step asks.

## Note on what these skills change

They change *how Claude works*, not your business data. Buying rules live in `learning-hub/data/ai-brain.json`
(edit via `fba-brain-updater`). Nothing in this plugin buys anything or moves money — every purchase stays a
human decision.
