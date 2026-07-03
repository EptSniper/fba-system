"""
ingest.py — assemble the RAG corpus from every document we legitimately own.

No heavy dependencies (pure standard library). It walks our knowledge sources,
splits them into section-aware chunks (~800 tokens, ~100-token overlap, with the
heading path + citation attached to every chunk), and writes two JSONL files that
map 1:1 onto the Postgres schema in the plan:

    corpus/documents.jsonl   id, source_url, source_path, title, source_type,
                             marketplace, category, last_crawled_at, content_hash,
                             version, status
    corpus/chunks.jsonl      id, document_id, chunk_text, heading_path,
                             chunk_index, token_count, citation

`build_index.py` then embeds chunks.jsonl into a vector index. Keeping ingest
(chunking) and build_index (embedding) separate means we can re-chunk without
re-embedding, and the chunks are human-inspectable before any model runs.

Compliance: we ingest only files we own or were given (transcripts, playbooks,
fundamentals, the uploaded PDFs, our own design docs). Amazon's own pages are
NOT bulk-downloaded here — they live in sources/manifest.json as on-demand
sources (see README.md / update_job.md).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.join(HERE, "..", "learning-hub")
OUT = os.path.join(HERE, "corpus")
MARKETPLACE = "US"

# ~800-token target with ~100-token overlap. We approximate tokens as words * 1.3
# (good enough for sizing; the embedder does the real tokenization).
WORDS_PER_CHUNK = 600
WORDS_OVERLAP = 75

# (relative glob dir, file extension, category, source_type). Order = priority.
RULES = [
    ("fundamentals", ".md", "Fundamentals", "our_notes"),
    ("playbooks/sourcing-playbook.md", None, "Arbitrage decision rules", "our_notes"),
    ("playbooks/brands-and-sources.md", None, "Arbitrage decision rules", "our_notes"),
    ("playbooks/ungating-playbook.md", None, "Listing rules", "our_notes"),
    ("playbooks/operations-playbook.md", None, "FBA operations", "our_notes"),
    ("transcripts", ".txt", "Transcripts", "video_transcript"),
    ("transcripts/insights.md", None, "Arbitrage decision rules", "our_notes"),
    ("ai-system", ".md", "APIs and data", "design_doc"),
    ("assets", ".md", "Fundamentals", "our_notes"),
]
# Plus the converted PDFs and fetched Amazon docs inside knowledge-rag/sources.
PDF_DIR = os.path.join(HERE, "sources", "pdfs")
AMAZON_DIR = os.path.join(HERE, "sources", "amazon")
# Articles/papers captured by the daily research pipeline (research-inbox text-sources,
# promoted here after ingest). Front matter may override category/source_type.
RESEARCH_DIR = os.path.join(HERE, "sources", "research")


def _front_matter_field(text: str, field: str, default: str) -> str:
    m = re.search(r"^%s:\s*(.+)$" % re.escape(field), text, re.MULTILINE)
    return m.group(1).strip() if m else default


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _doc_id(path: str) -> str:
    return "doc_" + hashlib.sha256(path.encode()).hexdigest()[:10]


def _title_from(path: str, text: str) -> str:
    # front-matter title:  or first markdown H1, else filename
    m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return os.path.splitext(os.path.basename(path))[0]


def _iter_source_files():
    """Yield (abspath, category, source_type) for every file to ingest."""
    for rel, ext, category, stype in RULES:
        base = os.path.join(HUB, rel)
        if ext is None:  # a single explicit file
            if os.path.isfile(base):
                yield base, category, stype
            continue
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if name.lower().endswith(ext):
                    yield os.path.join(base, name), category, stype
    if os.path.isdir(PDF_DIR):
        for name in sorted(os.listdir(PDF_DIR)):
            if name.lower().endswith(".md"):
                # category is declared in each PDF's front matter; default below
                yield os.path.join(PDF_DIR, name), "APIs and data", "user_pdf"
    if os.path.isdir(AMAZON_DIR):
        for name in sorted(os.listdir(AMAZON_DIR)):
            if name.lower().endswith(".md"):
                p = os.path.join(AMAZON_DIR, name)
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(800)
                cat = _front_matter_field(head, "category", "Policy")
                stype = _front_matter_field(head, "source_type", "amazon_public")
                yield p, cat, stype
    if os.path.isdir(RESEARCH_DIR):
        for name in sorted(os.listdir(RESEARCH_DIR)):
            if name.lower().endswith(".md"):
                p = os.path.join(RESEARCH_DIR, name)
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(800)
                cat = _front_matter_field(head, "category", "Research articles")
                stype = _front_matter_field(head, "source_type", "research_article")
                yield p, cat, stype


def _strip_front_matter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :]
    return text


def _sectionize(text: str):
    """Split markdown into (heading_path, body) blocks. Plain text -> one block."""
    lines = text.splitlines()
    blocks, stack, buf = [], [], []
    has_headings = any(re.match(r"^#{1,6}\s", ln) for ln in lines)
    if not has_headings:
        return [([], text)]
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            if buf:
                blocks.append((list(stack), "\n".join(buf).strip()))
                buf = []
            level = len(m.group(1))
            stack = stack[: level - 1]
            while len(stack) < level - 1:
                stack.append("")
            stack = stack[: level - 1] + [m.group(2).strip()]
        else:
            buf.append(ln)
    if buf:
        blocks.append((list(stack), "\n".join(buf).strip()))
    return [(hp, body) for hp, body in blocks if body]


def _chunk_words(body: str):
    words = body.split()
    if not words:
        return []
    if len(words) <= WORDS_PER_CHUNK:
        return [body]
    out, i = [], 0
    step = WORDS_PER_CHUNK - WORDS_OVERLAP
    while i < len(words):
        out.append(" ".join(words[i : i + WORDS_PER_CHUNK]))
        i += step
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    docs, chunks = [], []
    cat_counts: dict[str, int] = {}
    today = dt.date.today().isoformat()

    for path, category, stype in _iter_source_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        text = _strip_front_matter(raw)
        if not text.strip():
            continue
        did = _doc_id(path)
        title = _title_from(path, raw)
        rel_path = os.path.relpath(path, os.path.join(HERE, ".."))
        docs.append(
            {
                "id": did,
                "source_url": None,
                "source_path": rel_path.replace("\\", "/"),
                "title": title,
                "source_type": stype,
                "marketplace": MARKETPLACE,
                "category": category,
                "last_crawled_at": today,
                "content_hash": _sha(raw),
                "version": 1,
                "status": "active",
            }
        )
        ci = 0
        for heading_path, body in _sectionize(text):
            for piece in _chunk_words(body):
                wc = len(piece.split())
                citation = f"{title} ({rel_path})"
                if heading_path:
                    citation += " › " + " › ".join(h for h in heading_path if h)
                chunks.append(
                    {
                        "id": f"{did}::{ci}",
                        "document_id": did,
                        "chunk_text": piece,
                        "heading_path": [h for h in heading_path if h],
                        "chunk_index": ci,
                        "token_count": max(1, round(wc * 1.3)),
                        "citation": citation,
                        "category": category,
                    }
                )
                ci += 1
        cat_counts[category] = cat_counts.get(category, 0) + 1

    with open(os.path.join(OUT, "documents.jsonl"), "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    toks = sum(c["token_count"] for c in chunks)
    print(f"Ingested {len(docs)} documents -> {len(chunks)} chunks (~{toks:,} tokens)")
    print("By category:")
    for cat in sorted(cat_counts):
        n = sum(1 for c in chunks if c["category"] == cat)
        print(f"  {cat:28} {cat_counts[cat]:>2} docs  {n:>4} chunks")
    print(f"\nWrote:\n  {os.path.join('corpus','documents.jsonl')}\n  {os.path.join('corpus','chunks.jsonl')}")


if __name__ == "__main__":
    main()
