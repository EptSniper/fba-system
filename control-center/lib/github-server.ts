// lib/github-server.ts — SERVER-ONLY. Lets the control-center trigger the same GitHub Actions
// workflows a human would via `gh workflow run` / the Actions tab "Run workflow" button, and
// check on the run it just triggered. Built for the Runs Health panel's "run now" buttons
// (2026-07-09): GitHub's own `schedule:` cron is NOT reliably hourly under load (live-observed
// gaps of 1.5-3.5h+ on keepa-collect.yml/train-ranker.yml), so an operator needs a real manual
// trigger, not just a wish that the next cron tick lands soon.
//
// NEVER import this from a "use client" component — GITHUB_PAT must never reach the browser
// bundle, same rule as SUPABASE_SERVICE_ROLE_KEY in lib/supabase-server.ts.
const GITHUB_PAT = process.env.GITHUB_PAT;
const GITHUB_REPO = process.env.GITHUB_REPO; // "owner/repo"
const API_BASE = "https://api.github.com";

// Allowlist — the ONLY workflows this app will ever dispatch. A client request names one of
// these keys, never a raw filename, so there is no path for an API caller to trigger an
// arbitrary workflow in the repo.
export const DISPATCHABLE_WORKFLOWS = {
  "keepa-collect": "keepa-collect.yml",
  "train-ranker": "train-ranker.yml",
} as const;
export type DispatchableWorkflow = keyof typeof DISPATCHABLE_WORKFLOWS;

export function githubConfigured(): boolean {
  return Boolean(GITHUB_PAT && GITHUB_REPO);
}

function headers(): Record<string, string> {
  return {
    Authorization: `Bearer ${GITHUB_PAT}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export async function dispatchWorkflow(
  workflow: DispatchableWorkflow,
  ref = "master",
): Promise<{ ok: boolean; error?: string }> {
  if (!githubConfigured()) return { ok: false, error: "GITHUB_PAT/GITHUB_REPO not configured" };
  const file = DISPATCHABLE_WORKFLOWS[workflow];
  try {
    const res = await fetch(
      `${API_BASE}/repos/${GITHUB_REPO}/actions/workflows/${file}/dispatches`,
      { method: "POST", headers: { ...headers(), "Content-Type": "application/json" }, body: JSON.stringify({ ref }) },
    );
    // GitHub's dispatch endpoint returns 204 with an empty body on success — never a run id
    // (workflow_dispatch is fire-and-forget; see getLatestRun() below for finding the run it
    // started).
    if (res.status === 204) return { ok: true };
    const body = await res.text();
    return { ok: false, error: `GitHub API ${res.status}: ${body.slice(0, 300)}` };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export type WorkflowRunStatus = {
  id: number;
  status: string; // queued | in_progress | completed
  conclusion: string | null; // success | failure | cancelled | null (not yet concluded)
  createdAt: string;
  htmlUrl: string;
};

// The most recent run of a workflow, regardless of what triggered it (schedule or dispatch) --
// good enough for "did the run I just triggered finish, and how" polling, since two runs of the
// same workflow essentially never overlap (each workflow file's own concurrency: group blocks
// that).
export async function getLatestRun(workflow: DispatchableWorkflow): Promise<WorkflowRunStatus | null> {
  if (!githubConfigured()) return null;
  const file = DISPATCHABLE_WORKFLOWS[workflow];
  try {
    const res = await fetch(
      `${API_BASE}/repos/${GITHUB_REPO}/actions/workflows/${file}/runs?per_page=1`,
      { headers: headers(), cache: "no-store" },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { workflow_runs?: Array<Record<string, unknown>> };
    const run = data.workflow_runs?.[0];
    if (!run) return null;
    return {
      id: run.id as number,
      status: run.status as string,
      conclusion: (run.conclusion as string) ?? null,
      createdAt: run.created_at as string,
      htmlUrl: run.html_url as string,
    };
  } catch {
    return null;
  }
}
