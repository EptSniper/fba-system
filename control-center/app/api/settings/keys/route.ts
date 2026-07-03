import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import { NextResponse } from "next/server";
import { CENTRAL_REGISTRY_FILE, KEY_REGISTRY, findEntry } from "@/lib/keys";

// Node runtime (needs fs + child_process) and never cached — every request reads/writes the
// real .env files on disk. Local-operator-only, same convention as /api/capture: on serverless
// (Vercel) the sibling scout/knowledge-rag folders aren't present, so writes/tests there
// honestly 503 instead of crashing.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ROOT = path.join(process.cwd(), "..");
const PYTHON = process.env.PYTHON_BIN || "python";
const execFileAsync = promisify(execFile);

// A value this project treats as "not really set" — the standing placeholder convention (see
// API_KEYS.env's own header) — so the UI never shows a placeholder as a real, working key.
const PLACEHOLDER = "<FILL_ME>";

function resolveFile(rel: string): string {
  return path.join(ROOT, rel);
}

function readEnvFile(abs: string): string {
  try {
    return fs.readFileSync(abs, "utf8");
  } catch {
    return "";
  }
}

function getEnvValue(content: string, key: string): string {
  const line = content.split("\n").find((l) => l.trimStart().startsWith(`${key}=`));
  if (!line) return "";
  return line.slice(line.indexOf("=") + 1).trim();
}

function isSet(value: string): boolean {
  return value.length > 0 && value !== PLACEHOLDER;
}

// Upsert KEY=value into one file's text, preserving every other line (comments, spacing,
// unrelated keys) exactly as-is. Appends a new line if the key isn't present yet.
function upsertEnvLine(content: string, key: string, value: string): string {
  const lines = content.length ? content.split("\n") : [];
  const idx = lines.findIndex((l) => l.trimStart().startsWith(`${key}=`));
  const newLine = `${key}=${value}`;
  if (idx >= 0) {
    lines[idx] = newLine;
    return lines.join("\n");
  }
  const trimmed = content.replace(/\n+$/, "");
  return trimmed ? `${trimmed}\n${newLine}\n` : `${newLine}\n`;
}

function writeField(files: string[], fieldId: string, value: string) {
  for (const rel of files) {
    const abs = resolveFile(rel);
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    const content = readEnvFile(abs);
    fs.writeFileSync(abs, upsertEnvLine(content, fieldId, value), "utf8");
  }
}

function hubMissing(): boolean {
  // Same signal /api/capture uses: the sibling learning-hub folder only exists locally.
  return !fs.existsSync(path.join(ROOT, "learning-hub"));
}

// ---- GET: status only — which fields are SET, never their values -------------------------
export async function GET() {
  const statuses = KEY_REGISTRY.map((entry) => {
    const fieldsSet: Record<string, boolean> = {};
    for (const field of entry.fields) {
      // "set" = true in ANY of the entry's real consuming files (they should agree, but if a
      // manual edit desynced them, treat it as set if the primary/first file has it).
      const value = entry.files
        .map((f) => getEnvValue(readEnvFile(resolveFile(f)), field.id))
        .find((v) => isSet(v));
      fieldsSet[field.id] = isSet(value ?? "");
    }
    return { id: entry.id, fieldsSet };
  });
  return NextResponse.json({ ready: !hubMissing(), keys: statuses });
}

// ---- POST: save / clear / test --------------------------------------------------------
type Body = {
  action: "save" | "clear" | "test";
  id: string;
  values?: Record<string, string>;
};

export async function POST(req: Request) {
  if (hubMissing()) {
    return NextResponse.json(
      { error: "Key management is local-operator-only — the sibling project folders aren't present in this environment." },
      { status: 503 },
    );
  }

  let body: Body;
  try {
    const parsed: unknown = await req.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return NextResponse.json({ error: "Body must be a JSON object." }, { status: 400 });
    }
    body = parsed as Body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const entry = findEntry(body.id);
  if (!entry) {
    return NextResponse.json({ error: `Unknown key id: ${body.id}` }, { status: 400 });
  }

  if (body.action === "save") {
    const values = body.values ?? {};
    const targets = [...entry.files, CENTRAL_REGISTRY_FILE];
    for (const field of entry.fields) {
      const v = values[field.id];
      if (typeof v === "string") writeField(targets, field.id, v.trim());
    }
    return NextResponse.json({ ok: true });
  }

  if (body.action === "clear") {
    const targets = [...entry.files, CENTRAL_REGISTRY_FILE];
    for (const field of entry.fields) writeField(targets, field.id, "");
    return NextResponse.json({ ok: true });
  }

  if (body.action === "test") {
    if (!entry.testProvider) {
      return NextResponse.json({ ok: false, detail: "This key has no live test available." });
    }
    const script = path.join(ROOT, "scout", "key_test.py");
    if (!fs.existsSync(script)) {
      return NextResponse.json({ ok: false, detail: "Test script not found on this machine." });
    }
    const values = body.values ?? {};
    // Each field's value under test: what the user just typed (unsaved), else whatever is
    // already saved to disk — read server-side only, NEVER included in this response.
    const testValues = entry.fields.map((field) => {
      const typed = values[field.id];
      if (typeof typed === "string" && typed.trim()) return typed.trim();
      const saved = entry.files
        .map((f) => getEnvValue(readEnvFile(resolveFile(f)), field.id))
        .find((v) => isSet(v));
      return saved ?? "";
    });

    const env: NodeJS.ProcessEnv = { ...process.env, PYTHONIOENCODING: "utf-8" };
    testValues.forEach((v, i) => {
      env[i === 0 ? "TEST_KEY_VALUE" : `TEST_KEY_VALUE_${i + 1}`] = v;
    });

    try {
      const { stdout } = await execFileAsync(PYTHON, [script, entry.testProvider], {
        timeout: 20_000,
        maxBuffer: 256 * 1024,
        windowsHide: true,
        env,
      });
      const result = JSON.parse(stdout) as { ok: boolean; detail: string };
      return NextResponse.json(result);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Unknown test error";
      return NextResponse.json({
        ok: false,
        detail: process.env.NODE_ENV === "development" ? detail : "Test script failed to run.",
      });
    }
  }

  return NextResponse.json({ error: `Unknown action: ${body.action}` }, { status: 400 });
}
