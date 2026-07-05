// lib/brain-writer.ts — SERVER-ONLY. The only code path allowed to write
// learning-hub/data/ai-brain.json. Mirrors amazon-fba-oa/skills/fba-brain-updater/SKILL.md's
// own documented procedure exactly: read the whole file, change ONLY the one key requested
// (never reformat/drop other fields — this is a dotted-path REPLACE, not a merge, so sibling
// keys including each section's `source:` provenance line are untouched), bump `updated` to
// today's date, then re-sync the bundled control-center/hub-data/ai-brain.json snapshot the
// same skill's own step 6 calls out as a manual, easy-to-forget step.
import fs from "node:fs";
import { hubDataPath, projectRootPath } from "./events-server";

const BRAIN_PATH = hubDataPath("ai-brain.json");
const HUB_DATA_SNAPSHOT_PATH = projectRootPath("control-center/hub-data/ai-brain.json");

export function readBrainRaw(): Record<string, unknown> | null {
  try {
    return JSON.parse(fs.readFileSync(BRAIN_PATH, "utf8")) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function getByPath(obj: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((cur, key) => {
    if (cur === null || typeof cur !== "object") return undefined;
    return (cur as Record<string, unknown>)[key];
  }, obj);
}

function setByPath(obj: Record<string, unknown>, path: string, value: unknown): void {
  const keys = path.split(".");
  let cur: Record<string, unknown> = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i];
    if (cur[k] === null || typeof cur[k] !== "object") {
      throw new Error(`Cannot set "${path}" — "${keys.slice(0, i + 1).join(".")}" is not an object.`);
    }
    cur = cur[k] as Record<string, unknown>;
  }
  cur[keys[keys.length - 1]] = value;
}

// Same "type family" a value must stay within for applyBrainEdit() to accept it — a cheap but
// real guard against a drafted edit silently changing a key's shape (e.g. a threshold number
// getting replaced with a string, or an array getting replaced with a scalar).
export function sameTypeFamily(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) return true; // element-type drift inside an array is fine (e.g. new brand string)
  if (a === null || b === null) return a === b;
  return typeof a === typeof b;
}

export type ApplyResult = { ok: true; previousValue: unknown } | { ok: false; error: string };

// The ONE write path. `key` is a dotted path (e.g. "brands.avoid", "scoring.scoreThreshold")
// that MUST already exist in the brain (this never creates new keys — that would be
// "inventing a business rule," which the fba-brain-updater skill explicitly forbids).
export function applyBrainEdit(key: string, newValue: unknown): ApplyResult {
  const brain = readBrainRaw();
  if (!brain) return { ok: false, error: "Could not read ai-brain.json." };

  const previousValue = getByPath(brain, key);
  if (previousValue === undefined) {
    return { ok: false, error: `Key "${key}" does not exist in ai-brain.json — refusing to create a new one.` };
  }
  if (!sameTypeFamily(previousValue, newValue)) {
    return { ok: false, error: `Type mismatch at "${key}": refusing to replace ${typeof previousValue} with ${typeof newValue}.` };
  }

  try {
    setByPath(brain, key, newValue);
    brain.updated = new Date().toISOString().slice(0, 10);
    const text = JSON.stringify(brain, null, 2) + "\n";
    JSON.parse(text); // step 5 of the skill's procedure — validate before it ever touches disk
    fs.writeFileSync(BRAIN_PATH, text, "utf8");
    fs.writeFileSync(HUB_DATA_SNAPSHOT_PATH, text, "utf8"); // step 6 — the snapshot the skill warns goes stale
    return { ok: true, previousValue };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
