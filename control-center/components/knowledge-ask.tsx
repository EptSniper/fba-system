"use client";

import * as React from "react";
import {
  ArrowRight,
  BookOpen,
  Database,
  LoaderCircle,
  RotateCcw,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

type Answer = { title: string; keywords: string[]; body: string; source: string };
type LiveMatch = {
  id?: string;
  similarity?: number;
  relevance?: number;
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
type LiveResult = {
  question: string;
  count: number;
  answer: ExtractiveAnswer;
  matches: LiveMatch[];
  source: "supabase";
  model: string;
};
type Health = {
  ready: boolean;
  fastembed?: boolean;
  supabase?: boolean;
  model?: string;
  error?: string;
};
type SearchState = "idle" | "loading" | "live" | "fallback";

const ANSWERS: Answer[] = [
  {
    title: "What makes a strong OA candidate?",
    keywords: ["good product", "candidate", "buy", "criteria", "winner"],
    body: "Start with BSR at or below 200,000, at least about 50 monthly sales, 3–25 competitive offers, 30%+ ROI, and $3+ profit per unit. Then require stable price history, flat or falling offer count, no meaningful Amazon Buy Box share, account eligibility, and low IP/FBA restriction risk.",
    source: "field-sops.md · product-research-template.md",
  },
  {
    title: "How do I read a Keepa chart?",
    keywords: ["keepa", "chart", "graph", "price history", "rank"],
    body: "Read the 90-day and one-year views together. Frequent rank drops indicate demand. Stable or rising Buy Box price is healthy; rising offers while price falls is a price-war warning. Check Amazon's in-stock periods, Buy Box share, seasonality, and the lowest historical price your margin must survive.",
    source: "field-sops.md · sourcing-playbook.md",
  },
  {
    title: "How do I get ungated?",
    keywords: ["ungated", "gating", "approval", "invoice", "eligible"],
    body: "First test the ASIN in Seller Central because approval is account-specific. Prefer auto-ungated products while the account is new. For invoice approval, follow the current Amazon request exactly, use authentic supply-chain documents from an accepted source, and never alter invoices. Re-check the requirement at the time you apply.",
    source: "ungating-playbook.md · SP-API Listings Restrictions notes",
  },
  {
    title: "How many units should I buy?",
    keywords: ["units", "quantity", "how many", "test buy", "inventory"],
    body: "For a new product, test roughly 5–10 units. A larger buy should be based on variation-level monthly sales divided by price-competitive sellers, then reduced by 30–50% for uncertainty. Confirm the worst-case historical price still breaks even and avoid concentrating the bankroll in one ASIN.",
    source: "sourcing-playbook.md · product-research-template.md",
  },
  {
    title: "What ROI is safe?",
    keywords: ["roi", "profit", "margin", "safe", "fees"],
    body: "The current working floor is 30% ROI and $3 profit per unit after referral, FBA, fuel, prep, inbound shipping, and the real landed cost. That is a screening threshold, not a guarantee: returns, price compression, storage, placement fees, taxes, and account eligibility can still invalidate the deal.",
    source: "ai-brain.json · fees-explained-simply.md",
  },
  {
    title: "How does the scout improve?",
    keywords: ["learn", "smarter", "model", "outcome", "improve", "accuracy"],
    body: "Every surfaced lead needs a later realized outcome: bought quantity, sold quantity, time to sell, actual ROI/profit, returns, Buy Box share, and whether you would rebuy. Strong outcomes must outrank weak public proxies. Challengers are evaluated offline and promoted only when they beat the current model; drift and calibration are monitored, while hard compliance gates always remain in force.",
    source: "scout_pro/ARCHITECTURE.md · ai-architecture.md",
  },
];

const SUGGESTIONS = [
  "What makes a good product?",
  "How do I read a Keepa chart?",
  "What ROI is safe?",
  "How does the scout improve?",
];

function bestAnswer(query: string) {
  const normalized = query.toLowerCase().trim();
  if (!normalized) return ANSWERS[0];
  const ranked = ANSWERS.map((answer) => ({
    answer,
    score: answer.keywords.reduce(
      (score, word) => score + (normalized.includes(word) ? word.length : 0),
      0,
    ),
  })).sort((a, b) => b.score - a.score);
  return ranked[0].score > 0 ? ranked[0].answer : null;
}

function LocalAnswer({ answer }: { answer: Answer | null }) {
  if (!answer) {
    return (
      <div className="flex min-h-40 flex-col items-center justify-center text-center">
        <Search size={22} className="text-faint" />
        <h2 className="mt-3 text-sm font-semibold text-ink">No confident local match</h2>
        <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">
          Try one of the suggested searches or retry the live knowledge brain. This interface will not invent an answer from a weak match.
        </p>
      </div>
    );
  }
  return (
    <>
      <div className="mb-3 flex items-center gap-2 text-profit">
        <ShieldCheck size={17} />
        <span className="num text-[10px] font-semibold uppercase tracking-[0.18em]">local verified fallback</span>
      </div>
      <h2 className="text-lg font-semibold text-ink">{answer.title}</h2>
      <p className="mt-3 max-w-4xl text-sm leading-7 text-muted">{answer.body}</p>
      <div className="mt-5 flex items-center gap-2 border-t border-line pt-4 text-xs text-faint">
        <BookOpen size={14} />
        <span>Sources: {answer.source}</span>
      </div>
    </>
  );
}

export function KnowledgeAsk({ chunkCount = 0 }: { chunkCount?: number }) {
  const [query, setQuery] = React.useState("What makes a good product?");
  const [state, setState] = React.useState<SearchState>("idle");
  const [result, setResult] = React.useState<LiveResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [health, setHealth] = React.useState<Health | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    let active = true;
    fetch("/api/knowledge-search", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json() as Health;
        if (active) setHealth({ ...payload, ready: response.ok && payload.ready });
      })
      .catch(() => {
        if (active) setHealth({ ready: false, error: "Health check failed." });
      });
    return () => {
      active = false;
      abortRef.current?.abort();
    };
  }, []);

  const runSearch = async (nextQuestion = query) => {
    const question = nextQuestion.trim();
    if (!question) {
      setError("Enter a question first.");
      setState("fallback");
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setQuery(question);
    setState("loading");
    setError(null);
    setResult(null);

    try {
      const response = await fetch("/api/knowledge-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      const payload = await response.json() as LiveResult | { error?: string };
      if (!response.ok) {
        throw new Error("error" in payload && payload.error ? payload.error : "Live search failed.");
      }
      const live = payload as LiveResult;
      if (!live.matches?.length) {
        setError("The live brain found no relevant passages. Showing the local fallback instead.");
        setState("fallback");
        return;
      }
      setResult(live);
      setState("live");
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "Live search failed.");
      setState("fallback");
    }
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void runSearch();
  };

  const choose = (suggestion: string) => {
    void runSearch(suggestion);
  };

  const localAnswer = bestAnswer(query);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-bg/45 px-3.5 py-3 text-xs" role="status">
        <span className="flex items-center gap-2 text-muted">
          <Database size={15} className={health?.ready ? "text-profit" : health ? "text-warn" : "text-faint"} />
          {health?.ready ? "Knowledge runtime ready" : health ? "Knowledge runtime needs attention" : "Checking knowledge runtime…"}
        </span>
        <span className="num text-[10px] uppercase tracking-[0.12em] text-faint">
          {health?.ready ? "local embeddings · Supabase read-only" : health ? "local fallback available" : "checking"}
        </span>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label className="relative flex-1">
          <span className="sr-only">Ask the Amazon FBA knowledge base</span>
          <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            className="field min-h-12 pl-10 pr-3"
            value={query}
            maxLength={500}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask about sourcing, Keepa, ROI, ungating, or the scout…"
          />
        </label>
        <button
          type="submit"
          disabled={state === "loading"}
          className="inline-flex min-h-12 cursor-pointer items-center justify-center gap-2 bg-accent px-5 text-sm font-semibold text-white transition-all duration-200 hover:brightness-110 disabled:cursor-wait disabled:opacity-70"
        >
          {state === "loading" ? <LoaderCircle size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {state === "loading" ? "Searching…" : "Search brain"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            disabled={state === "loading"}
            onClick={() => choose(suggestion)}
            className="cursor-pointer rounded-full border border-line bg-panel2/55 px-3 py-1.5 text-xs text-muted transition-colors hover:border-line2 hover:text-ink disabled:cursor-wait disabled:opacity-60"
          >
            {suggestion}
          </button>
        ))}
      </div>

      <div className="mt-5 min-h-52 rounded-xl border border-line bg-bg/40 p-5 sm:p-6" aria-live="polite" aria-busy={state === "loading"}>
        {state === "loading" ? (
          <div className="flex min-h-44 flex-col items-center justify-center text-center">
            <LoaderCircle size={24} className="animate-spin text-accent" />
            <h2 className="mt-3 text-sm font-semibold text-ink">
              Searching {chunkCount ? chunkCount.toLocaleString() : "the"} cited knowledge notes
            </h2>
            <p className="mt-1 max-w-md text-xs leading-relaxed text-muted">The first search can take longer while the local embedding model starts.</p>
          </div>
        ) : state === "live" && result ? (
          <>
            <div className="mb-3 flex items-center gap-2 text-profit">
              <ShieldCheck size={17} />
              <span className="num text-[10px] font-semibold uppercase tracking-[0.18em]">cited zero-cost answer</span>
            </div>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-ink">Answer to “{result.question}”</h2>
                <p className="mt-1 text-xs text-muted">{result.answer.intro}</p>
              </div>
              <span className="num rounded-full border border-line2 bg-panel2 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-muted">
                {result.answer.evidence_strength} evidence
              </span>
            </div>
            <ol className="mt-5 grid gap-3">
              {result.answer.points.map((point, index) => (
                <li key={`${point.citation}-${index}`} className="rounded-lg border border-line bg-panel2/45 p-4">
                  <p className="text-sm leading-6 text-ink">{point.text}</p>
                  <div className="mt-3 flex items-start gap-2 border-t border-line pt-3 text-[11px] leading-relaxed text-faint">
                    <BookOpen size={13} className="mt-0.5 shrink-0" />
                    <span>[{index + 1}] {point.citation}</span>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-4 flex gap-2 rounded-lg border border-warn/25 bg-warn/5 p-3 text-xs leading-relaxed text-muted">
              <TriangleAlert size={16} className="mt-0.5 shrink-0 text-warn" />
              {result.answer.caveat}
            </div>
            <details className="mt-4 rounded-lg border border-line bg-bg/30">
              <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-muted transition-colors hover:text-ink">
                Inspect retrieved evidence ({result.count} passages)
              </summary>
              <ol className="grid gap-3 border-t border-line p-3">
                {result.matches.slice(0, 6).map((match, index) => {
                  const passage = match.chunk_text ?? "";
                  return (
                    <li key={`${match.id ?? match.document_id ?? match.citation ?? "match"}-${index}`} className="rounded-lg border border-line bg-panel2/35 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-medium text-ink">{match.citation || "Project knowledge source"}</span>
                        <span className="num text-[10px] uppercase tracking-[0.12em] text-faint">semantic match {Math.round((match.similarity ?? 0) * 100)}%</span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-muted">{passage.slice(0, 700)}{passage.length > 700 ? "…" : ""}</p>
                    </li>
                  );
                })}
              </ol>
            </details>
          </>
        ) : (
          <>
            {error ? (
              <div className="mb-5 flex flex-col gap-3 rounded-lg border border-warn/35 bg-warn/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex gap-3">
                  <TriangleAlert size={18} className="mt-0.5 shrink-0 text-warn" />
                  <div><p className="text-sm font-medium text-ink">Live search unavailable</p><p className="mt-1 text-xs leading-relaxed text-muted">{error} The cited local fallback remains available below.</p></div>
                </div>
                <button type="button" onClick={() => void runSearch()} className="inline-flex min-h-9 cursor-pointer items-center justify-center gap-2 rounded-md border border-line2 px-3 text-xs font-medium text-ink transition-colors hover:bg-panel2">
                  <RotateCcw size={14} /> Retry
                </button>
              </div>
            ) : null}
            <LocalAnswer answer={localAnswer} />
          </>
        )}
      </div>
      <p className="mt-3 text-xs leading-relaxed text-faint">
        Zero-cost mode: local embeddings retrieve from Supabase, then a deterministic reranker prefers structured playbooks and extracts cited answer points. No paid model, service-role key, or business data is exposed to the browser.
      </p>
    </div>
  );
}
