// lib/reports.ts — generic "latest append-only report block" reader, shared by the two
// free-text report files CC2's KPI panel renders (learning-hub/tracking/ops-report.md, written
// by scout/ops_report.py; weekly-reviews.md, written by the fba-weekly-command-review
// scheduled Cowork task). Both are append-only markdown with "## <date> — <title>" block
// headers (oldest first) and freeform bullet prose underneath — rather than regex-parsing
// each sentence into typed fields (fragile against wording changes, and these are meant to be
// read by a human anyway), this just extracts the LAST block's raw text and renders it
// honestly. "render the latest honestly" (CC2 item 4) doesn't require structured fields.

export type ReportBlock = { header: string; body: string };

const HEADER_RE = /^##\s+(.+)$/;

export function latestReportBlock(markdown: string): ReportBlock | null {
  const lines = markdown.split(/\r?\n/);
  let header: string | null = null;
  let bodyLines: string[] = [];
  let sawAnyHeader = false;

  for (const line of lines) {
    const m = HEADER_RE.exec(line.trim());
    if (m) {
      sawAnyHeader = true;
      header = m[1];
      bodyLines = [];
      continue;
    }
    if (header !== null) bodyLines.push(line);
  }

  if (!sawAnyHeader || header === null) return null;
  return { header, body: bodyLines.join("\n").trim() };
}
