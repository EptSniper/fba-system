// lib/events-server.ts — SERVER-ONLY append-only operator ledger (events.jsonl). Extracted
// from app/api/capture/route.ts (CC1) so the new /api/ops/decide route can append "decision"
// events into the SAME ledger instead of growing a second, parallel one.
import fs from "node:fs";
import path from "node:path";
import type { CaptureEvent, CaptureKind } from "./types";

// The ONE definition of where the project root / hub folders live — lib/data.ts (the read
// side) imports HUB_DATA_DIR from here, so reads and writes can never silently point at
// different folders.
export const PROJECT_ROOT = path.join(process.cwd(), "..");
export const HUB_DATA_DIR = path.join(PROJECT_ROOT, "learning-hub", "data");
export const HUB_TRACKING_DIR = path.join(PROJECT_ROOT, "learning-hub", "tracking");
const DATA = HUB_DATA_DIR;
const EVENTS = path.join(DATA, "events.jsonl");

export function hubMissing(): boolean {
  return !fs.existsSync(DATA);
}

export function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

// Raw text reader for the markdown tracking files CC2's Morning Brief/proposals pages parse
// (brain-proposals.md, ops-report.md, weekly-reviews.md, HUMAN_TODO.md). Unlike the JSON hub
// data, these have no bundled Vercel fallback (lib/data.ts's hub-data/ snapshot mechanism) —
// on a deployment without the sibling learning-hub/ folder this honestly returns null and
// callers render a real "not available in this deployment" state, never fabricated content.
export function readTextFile(absPath: string): string | null {
  try {
    return fs.readFileSync(absPath, "utf8");
  } catch {
    return null;
  }
}

export function hubDataPath(file: string): string {
  return path.join(DATA, file);
}

export function hubTrackingPath(file: string): string {
  return path.join(HUB_TRACKING_DIR, file);
}

export function projectRootPath(file: string): string {
  return path.join(PROJECT_ROOT, file);
}

export function eventsPath(): string {
  return EVENTS;
}

export function appendEvent(kind: CaptureKind, payload: Record<string, unknown>): CaptureEvent {
  const event: CaptureEvent = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: new Date().toISOString(),
    kind,
    payload,
  };
  fs.appendFileSync(EVENTS, JSON.stringify(event) + "\n", "utf8");
  return event;
}
