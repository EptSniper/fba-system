import { NextResponse } from "next/server";
import { DISPATCHABLE_WORKFLOWS, getLatestRun, githubConfigured } from "@/lib/github-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Polled by the Runs Health panel after a "run now" click to show queued -> in_progress ->
// completed(success/failure) instead of leaving the operator guessing whether the dispatch
// actually did anything (workflow_dispatch itself is fire-and-forget -- GitHub returns 204
// immediately, before the run even starts).

export async function GET(req: Request) {
  if (!githubConfigured()) {
    return NextResponse.json({ connected: false });
  }
  const workflow = new URL(req.url).searchParams.get("workflow");
  if (!workflow || !(workflow in DISPATCHABLE_WORKFLOWS)) {
    return NextResponse.json(
      { error: `workflow query param must be one of: ${Object.keys(DISPATCHABLE_WORKFLOWS).join(", ")}` },
      { status: 400 },
    );
  }
  const run = await getLatestRun(workflow as keyof typeof DISPATCHABLE_WORKFLOWS);
  if (!run) {
    return NextResponse.json({ connected: true, run: null });
  }
  return NextResponse.json({ connected: true, run });
}
