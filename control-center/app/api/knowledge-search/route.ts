import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const execFileAsync = promisify(execFile);
const MAX_QUESTION_LENGTH = 500;
const CACHE_TTL_MS = 15 * 60 * 1000;
const CACHE_LIMIT = 30;

type Match = {
  id?: string;
  similarity?: number;
  relevance?: number;
  query_coverage?: number;
  citation?: string;
  chunk_text?: string;
  category?: string;
  document_id?: string;
};

type AnswerPoint = {
  text: string;
  citation: string;
  category: string;
  similarity: number;
};

type ExtractiveAnswer = {
  intro: string;
  points: AnswerPoint[];
  evidence_strength: "strong" | "moderate" | "limited";
  caveat: string;
  method: "zero-cost extractive synthesis";
};

type RetrievalPayload = {
  question: string;
  count: number;
  answer: ExtractiveAnswer;
  matches: Match[];
};

type CachedResult = { expires: number; payload: RetrievalPayload };
const answerCache = new Map<string, CachedResult>();

const script = path.resolve(process.cwd(), "..", "knowledge-rag", "ask.py");
const python = process.env.PYTHON_BIN || "python";

// THIS_WEEK.md Prompt W1 — knowledge-rag/server.py keeps the bge model warm in memory instead
// of every call paying a full model load. Try it first; any failure (not running, timeout,
// bad response) falls straight back to the existing cold subprocess path below — this route
// never depends on the server being up, it's purely a latency optimization when it is.
const KNOWLEDGE_SERVER_PORT = process.env.KNOWLEDGE_SERVER_PORT || "8787";
const KNOWLEDGE_SERVER_URL = `http://127.0.0.1:${KNOWLEDGE_SERVER_PORT}`;
const SERVER_TIMEOUT_MS = 3_000;

async function tryLocalServer(question: string, limit: number): Promise<RetrievalPayload | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SERVER_TIMEOUT_MS);
    const res = await fetch(`${KNOWLEDGE_SERVER_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, limit }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return null;
    return (await res.json()) as RetrievalPayload;
  } catch {
    return null; // server not running / timed out / bad response — fall back silently
  }
}

async function runKnowledge(args: string[], timeout = 75_000) {
  const { stdout } = await execFileAsync(python, [script, ...args], {
    timeout,
    maxBuffer: 2 * 1024 * 1024,
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  return JSON.parse(stdout) as unknown;
}

export async function GET() {
  try {
    const health = await runKnowledge(["--health", "--json"], 12_000) as Record<string, unknown>;
    return NextResponse.json(health, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown health-check error";
    console.error("Knowledge health check failed:", detail);
    return NextResponse.json(
      { ready: false, error: "The local knowledge runtime is unavailable." },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Send a valid JSON request." }, { status: 400 });
  }

  const question = typeof (body as { question?: unknown })?.question === "string"
    ? (body as { question: string }).question.trim()
    : "";

  if (!question) {
    return NextResponse.json({ error: "Enter a question first." }, { status: 400 });
  }
  if (question.length > MAX_QUESTION_LENGTH) {
    return NextResponse.json(
      { error: `Keep the question under ${MAX_QUESTION_LENGTH} characters.` },
      { status: 400 },
    );
  }

  const cacheKey = question.toLowerCase().replace(/\s+/g, " ");
  const cached = answerCache.get(cacheKey);
  if (cached && cached.expires > Date.now()) {
    return NextResponse.json(
      { ...cached.payload, source: "supabase", model: "BAAI/bge-base-en-v1.5", cache: "hit", latency_source: "cache" },
      { headers: { "Cache-Control": "no-store", "X-Knowledge-Cache": "HIT" } },
    );
  }
  if (cached) answerCache.delete(cacheKey);

  try {
    const started = Date.now();
    let payload = await tryLocalServer(question, 12);
    let latencySource: "server" | "subprocess" = "server";
    if (!payload?.answer?.points?.length) {
      payload = await runKnowledge(["--json", "--limit", "12", question]) as RetrievalPayload;
      latencySource = "subprocess";
    }
    if (!payload?.answer?.points?.length) {
      throw new Error("Retrieval returned no answer points.");
    }
    answerCache.set(cacheKey, { expires: Date.now() + CACHE_TTL_MS, payload });
    while (answerCache.size > CACHE_LIMIT) {
      const oldest = answerCache.keys().next().value as string | undefined;
      if (!oldest) break;
      answerCache.delete(oldest);
    }
    return NextResponse.json(
      { ...payload, source: "supabase", model: "BAAI/bge-base-en-v1.5", cache: "miss",
        latency_ms: Date.now() - started, latency_source: latencySource },
      { headers: { "Cache-Control": "no-store", "X-Knowledge-Cache": "MISS" } },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown retrieval error";
    console.error("Knowledge retrieval failed:", detail);
    return NextResponse.json(
      {
        error: "The live knowledge brain could not answer right now.",
        detail: process.env.NODE_ENV === "development" ? detail : undefined,
      },
      { status: 503 },
    );
  }
}
