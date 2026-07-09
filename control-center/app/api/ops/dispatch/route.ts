import { NextResponse } from "next/server";
import { DISPATCHABLE_WORKFLOWS, dispatchWorkflow, githubConfigured } from "@/lib/github-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The Runs Health panel's "run now" buttons (2026-07-09) -- the ONLY write path to GitHub
// Actions from this app. Human-only in practice: middleware.ts requires operator Basic auth on
// every request to a Supabase-configured deployment. Triggers a REAL workflow_dispatch run --
// the exact same keepa-collect.yml/train-ranker.yml code path the hourly cron uses, no
// shortcuts, no simulated success.

function isDispatchable(v: unknown): v is keyof typeof DISPATCHABLE_WORKFLOWS {
  return typeof v === "string" && v in DISPATCHABLE_WORKFLOWS;
}

export async function POST(req: Request) {
  if (!githubConfigured()) {
    return NextResponse.json(
      { error: "GITHUB_PAT/GITHUB_REPO aren't configured -- can't trigger a workflow from here." },
      { status: 503 },
    );
  }
  let body: Record<string, unknown>;
  try {
    const parsed: unknown = await req.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return NextResponse.json({ error: "Body must be a JSON object." }, { status: 400 });
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const workflow = body.workflow;
  if (!isDispatchable(workflow)) {
    return NextResponse.json(
      { error: `workflow must be one of: ${Object.keys(DISPATCHABLE_WORKFLOWS).join(", ")}` },
      { status: 400 },
    );
  }

  const result = await dispatchWorkflow(workflow);
  if (!result.ok) {
    return NextResponse.json({ error: result.error ?? "Dispatch failed." }, { status: 502 });
  }
  return NextResponse.json({ ok: true, workflow });
}
