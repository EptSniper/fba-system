import { NextResponse } from "next/server";
import fs from "node:fs";
import type { CaptureEvent, CaptureKind, Inventory, Leads } from "@/lib/types";
import { appendEvent, eventsPath, hubDataPath, hubMissing, readJson } from "@/lib/events-server";

// Node runtime (needs fs) and never cached — every request reads/writes live files.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Capture is a LOCAL-OPERATOR feature. It writes to the sibling learning-hub/data folder,
// which does not exist on serverless (Vercel). There it returns a clear 503 instead of crashing.
// It never performs an external action — it only records what the human already did.
const EVENTS = eventsPath();

const KINDS: CaptureKind[] = ["lead", "decision", "inventory", "outcome"];
// "review" (Code Review 2026-07-02, Finding CS1) — a candidate that's been analyzed and needs
// a human look before moving on, matching the deal-analyzer's own REVIEW verdict and the one
// real captured lead already on file, which predates this allowlist and used "review" as its
// status. Order roughly matches the pipeline's natural progression.
const LEAD_STATUS = ["idea", "researching", "review", "buy", "ordered", "sold", "passed"];
const DECISIONS = ["buy", "test", "wait", "pass"];

// ---- tiny, dependency-free validators -------------------------------------------------
function str(v: unknown, max: number): string {
  return typeof v === "string" ? v.trim().slice(0, max) : "";
}
function reqStr(v: unknown, max: number): string | null {
  const s = str(v, max);
  return s.length ? s : null;
}
function num(v: unknown): number | undefined {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : undefined;
}

// leads.json's roi is stored as a FRACTION. The two known writers now DECLARE their unit
// (deal-analyzer sends roiUnit:"fraction", the Log form sends roiUnit:"percent"), so
// conversion is explicit, not guessed. The magnitude heuristic survives ONLY as a legacy
// fallback for callers that predate the unit field — it corrupts legitimate values on both
// sides of its threshold (a real 180% ROI fraction 1.8 → 0.018; a percent entry "1.4" → 140%),
// which is exactly why declared units replaced it (Code Review 2026-07-03, Finding #2;
// original heuristic from 2026-07-02 Finding CB2).
function normalizeRoiToFraction(v: number | undefined, unit: unknown): number | undefined {
  if (v === undefined) return undefined;
  if (unit === "fraction") return v;
  if (unit === "percent") return v / 100;
  return v > 1.5 ? v / 100 : v; // legacy writers only — no unit declared
}
function intNonNeg(v: unknown): number | undefined {
  const n = num(v);
  return n === undefined ? undefined : Math.max(0, Math.round(n));
}
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

// ---- aggregate updates (only leads + inventory get an aggregate; see note below) ------
// Decisions and outcomes are recorded ONLY in the append-only ledger on purpose: they are
// human labels/rationale, and we never fabricate finances from them — finances stay honestly
// empty until SP-API populates real settlement data.
// Both apply* functions return whether the aggregate file was actually updated — the ledger
// event (appendEvent) is written unconditionally by the caller, but the caller must NOT report
// a bare "ok: true" success when the aggregate silently no-op'd (missing/corrupt JSON file):
// that would be a fake-success response for a partially-failed write.
function applyLead(p: { product: string; asin?: string; roi?: number; status: string; notes?: string }): boolean {
  const leads = readJson<Leads>(hubDataPath("leads.json"));
  if (!leads) return false;
  // notes was accepted in the request payload but silently dropped here before (Code Review
  // 2026-07-02, Finding CS1/CS2) — captured in the append-only ledger event but never actually
  // reaching leads.json, so it could never show up on the Leads page.
  leads.leads.push({ product: p.product, asin: p.asin, roi: p.roi, status: p.status, notes: p.notes });
  leads.pipeline[p.status] = (leads.pipeline[p.status] ?? 0) + 1;
  leads.updated = today();
  fs.writeFileSync(hubDataPath("leads.json"), JSON.stringify(leads, null, 2) + "\n", "utf8");
  return true;
}

function applyInventory(p: {
  product: string;
  asin?: string;
  owned: number;
  atFba: number;
  inTransit: number;
  status: string;
}): boolean {
  const inv = readJson<Inventory>(hubDataPath("inventory.json"));
  if (!inv) return false;
  // Upsert by asin (if given) else by product name.
  const match = (it: Inventory["items"][number]) =>
    (p.asin && it.asin === p.asin) || (!p.asin && it.product === p.product);
  const existing = inv.items.find(match);
  if (existing) {
    existing.owned = p.owned;
    existing.atFba = p.atFba;
    existing.inTransit = p.inTransit;
    existing.status = p.status;
  } else {
    inv.items.push({ product: p.product, asin: p.asin, owned: p.owned, atFba: p.atFba, inTransit: p.inTransit, status: p.status });
  }
  // Recompute the summary deterministically from items so it can never drift.
  inv.summary = {
    unitsOwned: inv.items.reduce((a, it) => a + (it.owned || 0), 0),
    atFba: inv.items.reduce((a, it) => a + (it.atFba || 0), 0),
    inTransit: inv.items.reduce((a, it) => a + (it.inTransit || 0), 0),
    lowStock: inv.items.filter((it) => it.status.toLowerCase().includes("low")).length,
  };
  inv.connected = true; // it now reflects manually-tracked real units
  inv.updated = today();
  fs.writeFileSync(hubDataPath("inventory.json"), JSON.stringify(inv, null, 2) + "\n", "utf8");
  return true;
}

// ---- handlers -------------------------------------------------------------------------
export async function GET() {
  if (hubMissing()) {
    return NextResponse.json({ ready: false, events: [], note: "Capture is local-operator-only." });
  }
  try {
    const raw = fs.existsSync(EVENTS) ? fs.readFileSync(EVENTS, "utf8") : "";
    const events = raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l) as CaptureEvent;
        } catch {
          return null;
        }
      })
      .filter((e): e is CaptureEvent => e !== null)
      .reverse()
      .slice(0, 40);
    return NextResponse.json({ ready: true, events });
  } catch {
    return NextResponse.json({ ready: false, events: [] }, { status: 500 });
  }
}

export async function POST(req: Request) {
  if (hubMissing()) {
    return NextResponse.json(
      { error: "Capture is local-operator-only — the learning-hub data folder isn't present in this environment." },
      { status: 503 },
    );
  }

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = await req.json();
    // req.json() resolves successfully for any valid JSON value, including `null`/a bare
    // number/a string/an array — only an object has a `.kind` to read next.
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return NextResponse.json({ error: "Body must be a JSON object." }, { status: 400 });
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const kind = body.kind as CaptureKind;
  if (!KINDS.includes(kind)) {
    return NextResponse.json({ error: `kind must be one of: ${KINDS.join(", ")}` }, { status: 400 });
  }

  try {
    if (kind === "lead") {
      const product = reqStr(body.product, 120);
      if (!product) return NextResponse.json({ error: "Lead requires a product name." }, { status: 400 });
      const status = LEAD_STATUS.includes(str(body.status, 20)) ? str(body.status, 20) : "idea";
      const payload = {
        product,
        asin: str(body.asin, 20) || undefined,
        roi: normalizeRoiToFraction(num(body.roi), body.roiUnit),
        status,
        sourceSite: str(body.sourceSite, 80) || undefined,
        notes: str(body.notes, 500) || undefined,
      };
      const applied = applyLead(payload);
      const event = appendEvent("lead", payload);
      return NextResponse.json({
        ok: true,
        event,
        ...(applied ? {} : { warning: "Recorded to the ledger, but leads.json is missing or unreadable — the Pipeline count won't reflect this yet." }),
      });
    }

    if (kind === "decision") {
      const product = reqStr(body.product, 120);
      if (!product) return NextResponse.json({ error: "Decision requires a product name." }, { status: 400 });
      const decision = DECISIONS.includes(str(body.decision, 10)) ? str(body.decision, 10) : null;
      if (!decision) return NextResponse.json({ error: `decision must be one of: ${DECISIONS.join(", ")}` }, { status: 400 });
      const payload = {
        product,
        asin: str(body.asin, 20) || undefined,
        decision,
        qty: intNonNeg(body.qty),
        rationale: str(body.rationale, 500) || undefined,
      };
      return NextResponse.json({ ok: true, event: appendEvent("decision", payload) });
    }

    if (kind === "inventory") {
      const product = reqStr(body.product, 120);
      if (!product) return NextResponse.json({ error: "Inventory requires a product name." }, { status: 400 });
      const payload = {
        product,
        asin: str(body.asin, 20) || undefined,
        owned: intNonNeg(body.owned) ?? 0,
        atFba: intNonNeg(body.atFba) ?? 0,
        inTransit: intNonNeg(body.inTransit) ?? 0,
        status: str(body.status, 40) || "in stock",
      };
      const applied = applyInventory(payload);
      const event = appendEvent("inventory", payload);
      return NextResponse.json({
        ok: true,
        event,
        ...(applied ? {} : { warning: "Recorded to the ledger, but inventory.json is missing or unreadable — stock counts won't reflect this yet." }),
      });
    }

    // outcome — the gold label
    const product = reqStr(body.product, 120);
    if (!product) return NextResponse.json({ error: "Outcome requires a product name." }, { status: 400 });
    const payload = {
      product,
      asin: str(body.asin, 20) || undefined,
      boughtQty: intNonNeg(body.boughtQty) ?? 0,
      soldQty: intNonNeg(body.soldQty) ?? 0,
      actualProfit: num(body.actualProfit),
      returns: intNonNeg(body.returns),
      notes: str(body.notes, 500) || undefined,
    };
    return NextResponse.json({ ok: true, event: appendEvent("outcome", payload) });
  } catch (err) {
    console.error("capture write failed:", err);
    return NextResponse.json({ error: "Could not write capture. Check that learning-hub/data is writable." }, { status: 500 });
  }
}
