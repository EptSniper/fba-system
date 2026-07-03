// The API-key registry for the Settings page. Server-only concerns (which .env file(s) each
// key actually gets written to, and how it's live-tested) live in app/api/settings/keys/route.ts
// — this file is the single list both that route and the client UI read, so the two can never
// drift out of sync on what keys exist.
//
// `files` are the REAL, currently-consumed files (verified against the actual scripts that call
// load_dotenv()/read their own .env, not just "where a comment says it should go") — writing
// here is what makes a key ACTUALLY take effect the next time that script runs, not just
// documentation. Every save is ALSO mirrored into the root API_KEYS.env central registry (see
// the route), matching this project's standing "every key lives there too" convention.

export type KeyField = {
  id: string; // exact env var name the real script reads
  label: string;
  secret: boolean; // mask the input by default
  placeholder?: string;
};

export type KeyEntry = {
  id: string; // registry id — stable, used by the API route and the UI
  label: string;
  hint: string;
  group: "Sourcing" | "Discord routing" | "Knowledge" | "Amazon" | "Ops";
  files: string[]; // relative to the project root (parent of control-center/)
  fields: KeyField[];
  testProvider?: string; // scout/key_test.py provider key; omitted = not live-testable
};

const DISCORD_STREAMS: { id: string; envVar: string; label: string; hint: string }[] = [
  { id: "discord_daily_digest", envVar: "DISCORD_WEBHOOK_DAILY_DIGEST", label: "#daily-digest", hint: "The nightly scout summary embed." },
  { id: "discord_scout_picks", envVar: "DISCORD_WEBHOOK_SCOUT_PICKS", label: "#scout-picks", hint: "Individual scored picks the scout posts." },
  { id: "discord_retail_deals", envVar: "DISCORD_WEBHOOK_RETAIL_DEALS", label: "#retail-deals", hint: "Deal Finder source stats after a collection run." },
  { id: "discord_review_queue", envVar: "DISCORD_WEBHOOK_REVIEW_QUEUE", label: "#review-queue", hint: "Analyst disagreements + gray-zone deal matches (stream reserved, not wired to a sender yet)." },
  { id: "discord_brain_proposals", envVar: "DISCORD_WEBHOOK_BRAIN_PROPOSALS", label: "#brain-proposals", hint: "Proposed ai-brain.json tuning, for human review." },
  { id: "discord_system_health", envVar: "DISCORD_WEBHOOK_SYSTEM_HEALTH", label: "#system-health", hint: "Run failures, brain drift, low Keepa tokens." },
  { id: "discord_outcomes", envVar: "DISCORD_WEBHOOK_OUTCOMES", label: "#outcomes", hint: "Realized buy outcomes (stream reserved, not wired to a sender yet)." },
  { id: "discord_fallback", envVar: "DISCORD_WEBHOOK_FALLBACK", label: "Fallback channel", hint: "Catches any stream above with no channel of its own set." },
];

const discordEntries: KeyEntry[] = DISCORD_STREAMS.map((s) => ({
  id: s.id,
  label: s.label,
  hint: s.hint,
  group: "Discord routing",
  files: ["scout/.env"],
  testProvider: "discord_webhook",
  fields: [{ id: s.envVar, label: "Webhook URL", secret: true, placeholder: "https://discord.com/api/webhooks/…" }],
}));

export const KEY_REGISTRY: KeyEntry[] = [
  {
    id: "keepa",
    label: "Keepa",
    hint: "Unlocks live product discovery — price/BSR/offer history, Product Finder. Required for the scout to run at all.",
    group: "Sourcing",
    files: ["scout/.env"],
    testProvider: "keepa",
    fields: [{ id: "KEEPA_KEY", label: "Keepa API key", secret: true, placeholder: "paste your Keepa API key…" }],
  },
  {
    id: "anthropic",
    label: "Anthropic",
    hint: "Powers the analyst pass, weekly brand/category reflection, and the Deal Finder's AI matcher.",
    group: "Sourcing",
    files: ["scout/.env"],
    testProvider: "anthropic",
    fields: [{ id: "ANTHROPIC_API_KEY", label: "Anthropic API key", secret: true, placeholder: "sk-ant-…" }],
  },
  {
    id: "bestbuy",
    label: "Best Buy",
    hint: "Free retail deal feed for the Deal Finder — onSale items with UPCs. Signups from free-email domains (Gmail) are rejected; use a domain email.",
    group: "Sourcing",
    files: ["scout/.env"],
    testProvider: "bestbuy",
    fields: [{ id: "BESTBUY_API_KEY", label: "Best Buy API key", secret: true, placeholder: "paste your Best Buy API key…" }],
  },
  {
    id: "supabase",
    label: "Supabase",
    hint: "The business-memory database — leads, decisions, outcomes, runs telemetry, search-log.",
    group: "Sourcing",
    files: ["scout/.env"],
    testProvider: "supabase",
    fields: [
      { id: "SUPABASE_URL", label: "Project URL", secret: false, placeholder: "https://xxxx.supabase.co" },
      { id: "SUPABASE_SERVICE_KEY", label: "Service role key", secret: true, placeholder: "eyJ…" },
    ],
  },
  ...discordEntries,
  {
    id: "youtube_transcript",
    label: "YouTube Transcript API",
    hint: "Powers the daily research pipeline's transcript fetcher (knowledge-rag/fetch_transcripts.py).",
    group: "Knowledge",
    files: ["knowledge-rag/.env"],
    testProvider: "youtube_transcript",
    fields: [{ id: "YOUTUBE_TRANSCRIPT_API_KEY", label: "API key", secret: true, placeholder: "paste your youtube-transcript.io key…" }],
  },
  {
    id: "research_discord",
    label: "Research alerts channel",
    hint: "Discord webhook for the daily research-pipeline alerts (separate from the scout's routed channels).",
    group: "Knowledge",
    files: ["knowledge-rag/.env"],
    testProvider: "discord_webhook",
    fields: [{ id: "RESEARCH_DISCORD_WEBHOOK_URL", label: "Webhook URL", secret: true, placeholder: "https://discord.com/api/webhooks/…" }],
  },
  {
    id: "spapi",
    label: "Amazon SP-API",
    hint: "Account-specific listing eligibility, real fee estimates, and inventory — once registered with Amazon.",
    group: "Amazon",
    files: ["scout/.env"],
    testProvider: "spapi",
    fields: [
      { id: "SP_API_LWA_CLIENT_ID", label: "LWA client ID", secret: true, placeholder: "amzn1.application-oa2-client…" },
      { id: "SP_API_LWA_CLIENT_SECRET", label: "LWA client secret", secret: true, placeholder: "…" },
      { id: "SP_API_REFRESH_TOKEN", label: "Refresh token", secret: true, placeholder: "Atzr|…" },
    ],
  },
  {
    id: "healthcheck",
    label: "Healthchecks.io",
    hint: "Free dead-man's-switch heartbeat — alerts if the daily scout run never wakes up.",
    group: "Ops",
    files: ["scout/.env"],
    testProvider: "healthcheck",
    fields: [{ id: "HEALTHCHECK_URL", label: "Check URL", secret: false, placeholder: "https://hc-ping.com/…" }],
  },
];

export const CENTRAL_REGISTRY_FILE = "API_KEYS.env";

export function findEntry(id: string): KeyEntry | undefined {
  return KEY_REGISTRY.find((e) => e.id === id);
}
