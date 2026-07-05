import fs from "node:fs";
import path from "node:path";
import { HUB_DATA_DIR } from "./events-server";
import type { Money, Inventory, Leads, Picks, Brain, Deals, RagManifest, CaptureEvent } from "./types";

// Bundled snapshots of the hub data. Static imports are traced into the build, so these
// are GUARANTEED to exist on Vercel (which has no sibling learning-hub/ folder).
import brainBundled from "@/hub-data/ai-brain.json";
import moneyBundled from "@/hub-data/finances.json";
import inventoryBundled from "@/hub-data/inventory.json";
import leadsBundled from "@/hub-data/leads.json";
import picksBundled from "@/hub-data/picks.json";
import dealsBundled from "@/hub-data/deals.json";
import manifestBundled from "@/hub-data/rag-manifest.json";

// Local dev reads the LIVE sibling hub so edits show instantly; on serverless (Vercel) the
// sibling folder isn't there, so readJson throws and we return the bundled snapshot instead.
// Everything is read server-side — nothing leaks to the client, no secrets.
// The hub path itself lives in ONE place — lib/events-server.ts (the write side) owns
// HUB_DATA_DIR and this read side imports it, so the two can never point at different
// directories.
const DATA = HUB_DATA_DIR;

function live<T>(file: string, bundled: T): T {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return bundled; // Vercel / missing sibling -> the bundled snapshot (honest, real data)
  }
}

export function getBrain(): Brain {
  return live<Brain>(path.join(DATA, "ai-brain.json"), brainBundled as unknown as Brain);
}

export function getMoney(): Money {
  return live<Money>(path.join(DATA, "finances.json"), moneyBundled as unknown as Money);
}

export function getInventory(): Inventory {
  return live<Inventory>(path.join(DATA, "inventory.json"), inventoryBundled as unknown as Inventory);
}

export function getLeads(): Leads {
  return live<Leads>(path.join(DATA, "leads.json"), leadsBundled as unknown as Leads);
}

export function getPicks(): Picks {
  return live<Picks>(path.join(DATA, "picks.json"), picksBundled as unknown as Picks);
}

export function getDeals(): Deals {
  return live<Deals>(path.join(DATA, "deals.json"), dealsBundled as unknown as Deals);
}

export function getRagManifest(): RagManifest {
  // Live file lives in knowledge-rag/sources/ (a different sibling than the hub).
  const sibling = path.join(process.cwd(), "..", "knowledge-rag", "sources", "manifest.json");
  return live<RagManifest>(sibling, manifestBundled as unknown as RagManifest);
}

// Read the append-only operator ledger, newest first. Local-only: on serverless the sibling
// hub folder isn't present, so this returns [] instead of throwing. `limit` caps the feed.
export function getEvents(limit = 40): CaptureEvent[] {
  try {
    const raw = fs.readFileSync(path.join(DATA, "events.jsonl"), "utf8");
    const events = raw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        try {
          return JSON.parse(line) as CaptureEvent;
        } catch {
          return null;
        }
      })
      .filter((e): e is CaptureEvent => e !== null);
    return events.reverse().slice(0, limit);
  } catch {
    return [];
  }
}
