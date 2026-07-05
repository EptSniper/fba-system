# Deploy the control center to Vercel

The dashboard is deploy-ready: it bundles a snapshot of the hub data (`hub-data/`), so it
renders real content on Vercel with **no external services required**. Pick one path.

## ⚠️ The last failed deploy ran from the wrong folder
The previous attempt deployed the **`scout/`** folder (the Python rater), so Vercel tried to
build Python and failed with *"No python entrypoint found"*. You must run the deploy from
**`control-center/`** so Vercel detects **Next.js**. The stray Vercel project named **"scout"**
can be deleted in the Vercel dashboard (Project → Settings → delete) — it's not your dashboard.

## Option A — Vercel CLI, one line, no `cd` needed (recommended)

The deploys kept failing because the terminal was in the wrong folder (`scout`, or your home
directory). The fix is `--cwd`, which tells Vercel exactly which folder to deploy — so it doesn't
matter where you run it from:

```
npx vercel --cwd "C:\Users\ahmet\OneDrive\Belgeler\Claude\Projects\Amazon FBA\control-center" --prod
```

Answer the prompts by **typing** (don't paste): Set up and deploy? `y` · scope: your account ·
Link to existing project? `n` (NOT scout/ahmet) · name `oa-control-center` · directory: press Enter ·
keep detected Next.js settings? `y`.

The stray **scout** and **ahmet** projects from the failed runs can be deleted later in the Vercel
dashboard — they're not your dashboard.

`dir package.json` must show the file — that proves you're in the Next.js app (the `scout`
folder has no package.json, which is why `npm install` failed there).

The first `npx vercel --prod` will ask a few questions. Answer them by typing the answer and
pressing Enter (don't paste):

- **Set up and deploy?** → `y`
- **Which scope?** → pick your account
- **Link to existing project?** → `n`  (create a NEW one — do NOT pick "scout")
- **Project name?** → `oa-control-center`
- **In which directory is your code located?** → press Enter (it's `./`)
- **Auto-detected Next.js — keep settings?** → `y`

It then builds and prints your live URL. The stray **"scout"** project from the failed runs can
be deleted in the Vercel dashboard (Project → Settings → Delete).

## Option B — Git + Vercel git integration (auto-deploys + CodeRabbit reviews)
1. Push the repo to GitHub.
2. In Vercel → **Add New Project** → import the repo → set **Root Directory = `control-center`**.
3. Every push deploys; open PRs to get CodeRabbit review before merge.

## Notes
- **Framework**: Next.js 15 (auto-detected; `vercel.json` pins it — `package.json` currently pins `^15.5.18`). Build: `next build`.
- **Data**: live local runs read the sibling `../learning-hub` files; on Vercel it falls back
  to the bundled `hub-data/` snapshot. To refresh the deployed snapshot after feeding new
  info, re-copy the hub JSON into `hub-data/` (or just redeploy from a fresh local run).
- **Secrets, since CC1 (2026-07-03):** the dashboard is read-only ONLY when deployed without
  Supabase env vars. If you set `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in the Vercel
  project, you MUST also set `BASIC_AUTH_USER` + `BASIC_AUTH_PASS` — the /api/ops/* routes
  write real decisions with the service-role key, so `middleware.ts` refuses to serve a
  Supabase-configured deployment that has no operator auth. (The scout's Keepa key, deal-API
  keys, etc. still live with those services, not here.)
- First deploy doubles as the build check — if anything fails, send me the Vercel build log.
