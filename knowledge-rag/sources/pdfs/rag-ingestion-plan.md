---
title: Practical plan for ingesting Amazon Arbitrage & FBA help docs into your AI (RAG)
source_type: user_pdf
category: APIs and data
collected: 2026-06-23
---

Practical plan for ingesting Amazon Arbitrage and
FBA help documentation into your AI assistant
Executive summary
You can build a strong Amazon-focused assistant, but there is an important constraint at the very
beginning: a plan to ingest “every single document” has to be framed as a coverage program, not a one-
time scrape. Amazon’s seller knowledge surface spans multiple official properties, including Seller Central
Help, program policy and agreement pages, Sell on Amazon educational content and Seller University, and
Selling Partner API documentation. It also changes frequently, includes locale variants, and in some cases
exposes JavaScript-heavy or sign-in-gated surfaces. In practice, the right target is: complete as observable
under approved access, continuously monitored, versioned, and measurable. 1


The technical best practice is to use a section-aware RAG pipeline, not to rely on fine-tuning as your main
knowledge-ingestion mechanism. For this domain, the assistant needs to answer against current policy text,
fee changes, restrictions, invoice requirements, listing approvals, and FBA workflows. Dense retrieval alone
is enough for a prototype; for a production assistant, hybrid retrieval plus reranking is better. Amazon’s own
seller-facing agreement and Agent Policy also make compliance a first-class design concern: Seller Central’s
agreement says agents must identify themselves as automated systems, and Amazon’s Conditions of Use
restrict extracting and re-utilizing substantial parts of Amazon Service content without express written
consent. 2


Because you did not specify compute or budget constraints, the most practical default is: start with open-
source embeddings and a local vector index for prototyping, then graduate to Qdrant or pgvector for
production if you need filtering, versioning, and multi-user access controls. For extraction, use Requests
plus Beautiful Soup for simple HTML, Playwright only as a fallback for JavaScript-rendered pages, Trafilatura
or Unstructured for main-content cleanup, and PyMuPDF for PDFs. 3


Coverage and source discovery
For Amazon Arbitrage/FBA, the biggest conceptual mistake is to search only for the word “arbitrage.” In
the official Amazon corpus, the operational material relevant to arbitrage is spread across policy and
workflow pages rather than a single “retail arbitrage” help hub. The most relevant official policy surfaces are
the FBA program pages, drop shipping policy, listing restrictions, restricted products, invoice requirements,
approvals, used-sold-as-new prevention, condition rules, and source/authenticity-related documents. That is
the policy surface your assistant should treat as authoritative for arbitrage-related questions. 4


Your primary seed set should come from official Amazon domains and hubs that already aggregate seller
guidance. The most important seeds are Seller Central Help, the Program Policies index, the Policies/
agreements/guidelines hub, the FBA getting-started and FBA inventory hubs, Seller University on Sell on




                                                      1
Amazon, and SP-API documentation for programmatic operational details. These hubs significantly reduce
discovery blind spots because they link to child pages and related topics. 5


A practical discovery strategy should combine four paths. First, crawl outward from seed hubs on approved
domains. Second, run repeated search-engine discovery over the canonical Seller Central reference pattern
and related domains. Third, capture linked PDFs and downloads that appear inside approval and policy
pages. Fourth, maintain a “frontier” of newly discovered but unclassified pages for review and recrawl.
Amazon’s help pages show stable document-like identifiers in URLs such as .../help/hub/reference/
external/G... , while locale and session parameters vary; that makes doc-ID normalization feasible.        6




You should explicitly separate authoritative and secondary content. Official help pages, policy pages,
agreements, fee notices, Seller University, and SP-API docs belong in the authoritative corpus. Seller Forums
can still be useful, but only as a clearly lower-trust secondary corpus because discussion threads mix seller
experience with non-authoritative advice. If you include them at all, tag them separately and down-rank
them. 7


Completeness is made harder by three Amazon realities. First, help pages often appear in many locales and
parameterized URL forms. Second, some pages are tool-like or sign-in-dependent. Third, page rendering
can be JS-heavy enough that a plain HTML fetch only sees a shell. You should therefore define coverage in
terms of: discovered docs, normalized docs, successfully extracted docs, deduplicated docs, and change-
monitored docs. 8


A strong initial discovery query set looks like this:



  site:sellercentral.amazon.com/help/hub/reference/external "Fulfillment by
  Amazon"
  site:sellercentral.amazon.com/help/hub/reference/external "FBA"
  site:sellercentral.amazon.com/help/hub/reference/external "drop shipping policy"
  site:sellercentral.amazon.com/help/hub/reference/external "invoice requirements"
  site:sellercentral.amazon.com/help/hub/reference/external "restricted products"
  site:sellercentral.amazon.com/help/hub/reference/external "listing restrictions"
  site:sellercentral.amazon.com/help/hub/reference/external "used sold as new"
  site:sell.amazon.com/learn Seller University FBA
  site:developer-docs.amazon.com/sp-api/docs FBA inventory


These queries mirror the official domain patterns Amazon already exposes across Help, Sell on Amazon,
and SP-API. 9


Compliance and copyright
The most important legal point is that Amazon’s published Conditions of Use are not neutral about large-
scale extraction. Amazon states that content included in or made available through an Amazon Service is
Amazon’s or its suppliers’ property, and that you may not extract or re-utilize parts of the content, use data-
mining or similar extraction tools, or create and publish your own database featuring substantial parts of an
Amazon Service without express written consent. If you want a defensible “ingest everything” program, the




                                                        2
safest route is to obtain written permission or use an Amazon-approved export/API path where one exists.
 10




For Seller Central specifically, the compliance burden is now higher because the Amazon Services Business
Solutions Agreement references an Agent Policy, and the agreement snippet publicly states that agents
must clearly identify themselves as automated systems and comply with the Agent Policy at all times. Public
snippets from the Agent Policy also indicate that agents must not conceal that access or interaction comes
from an agent, including by mimicking the speed or pattern of human activity. That means “quiet” or
disguised crawling is the wrong design pattern. 11


Robots rules matter, but not in the way many teams assume. The Robots Exclusion Protocol is a standard for
crawler behavior, but the standard itself explicitly says robots rules are not a form of access authorization.
In other words, even if a path is crawlable under robots, that does not override Amazon’s terms of use,
agreement terms, or any site-specific restrictions. Compliance therefore has to be evaluated against both
robots behavior and contractual terms. 12


The practical compliance hierarchy I would use is this. Best: obtain Amazon permission or rely on approved
APIs, exports, or user-triggered document capture. Acceptable with counsel review: small-scale internal
indexing of documents you are entitled to access, with no redistribution, auditable access logs, attribution
back to source pages, and explicit agent identification. Highest risk: unattended bulk crawling of Seller
Central and re-hosting a large internal mirror of Amazon’s help corpus. That last model runs directly into
the published extraction and re-utilization language. 13


From a copyright standpoint, the safest product behavior is to store retrieved text for internal retrieval,
answer with citations and short excerpts, and always send the user back to the original Amazon page for
full context. Avoid training a model to reproduce Amazon help pages verbatim or exposing a bulk
downloadable copy of the corpus. Also preserve source URL, title, and retrieval trace so the assistant’s
outputs remain anchored and attributable. 14


Ingestion and indexing design
The ingestion pipeline should be built around seed discovery, controlled crawling, structured extraction,
section-aware chunking, embedding, and filtered retrieval. Do not start from a blind web spider. Start
from a curated seed list, keep an allowlist of domains and path prefixes, normalize document IDs, and
collect both content and metadata. That makes the corpus explainable and maintainable. 15


A controlled crawler should prefer lightweight HTTP requests first. Requests provides keep-alive and
connection pooling automatically, and it exposes text plus response headers cleanly. Pair that with Beautiful
Soup for HTML link extraction and fallback parsing. For Amazon pages where the fetched HTML is just a
shell or includes the “You need to enable JavaScript to run this app” message, trigger a Playwright fallback
only for those pages. That keeps the pipeline efficient instead of rendering every page in a browser. 16


For main-content extraction and cleanup, use a layered strategy rather than one parser. Trafilatura is strong
for extracting readable main text and metadata from web pages. Unstructured is useful when you need
element-aware partitioning for HTML, PDFs, and mixed document types. For PDFs, PyMuPDF is the most




                                                      3
practical first-line choice because it supports raw text, blocks, words, tables, and OCR workflows; use OCR
only for scanned PDFs or image-only pages. 17


Tables, FAQs, bullet lists, and embedded visuals need to be preserved as structure, not flattened blindly. In
Amazon policy material, a table may hold fee tiers, a bulleted list may encode compliance criteria, and an
FAQ question may be the exact retrieval key users later ask. When cleaning, preserve heading hierarchy,
convert tables to Markdown or normalized CSV fragments, keep each FAQ pair as a mini-section, and store
alt text or nearby captions for images where they convey policy content. 18


Chunking should be section-aware and model-aware. LangChain’s text splitters exist specifically to break
large documents into retrievable units that fit within model context windows. For short-context embedding
models like all-MiniLM-L6-v2 , which truncates text longer than 256 word pieces, keep chunks tighter:
roughly 250–400 tokens, with 15–20% overlap. For bge-small-en-v1.5 and bge-base-en-v1.5 ,
whose public serving docs list 512 maximum input tokens, a safer operational range is 300–500 tokens. For
long-context models like bge-m3 or OpenAI’s text-embedding-3-* , you can push chunks larger, but
for policy retrieval I still prefer smaller section-based chunks because they cite and rerank better.    19




The metadata you keep is as important as the text. At minimum, every chunk should retain: canonical URL,
original URL, domain, doc ID, title, heading path, section title, locale, marketplace, source type, crawl
timestamp, raw content hash, normalized content hash, ETag, Last-Modified, extraction tool/version, chunk
index, parent document version, and access scope. ETag and Last-Modified are particularly useful because
HTTP exposes them as validators for change detection and conditional re-fetch. 20


The tools below are the ones I would actually recommend for this ingestion stack.


                            Recommended                                                                 Official
  Layer                                             Why it fits this project
                            option                                                                      docs

                                                    Mature and simple; automatic keep-alive
  Basic HTTP fetch          Requests                                                                     21
                                                    and pooling

  HTML parsing              Beautiful Soup          Fast DOM navigation and cleanup                      22


                                                    Browser automation for pages that only
  JS fallback               Playwright                                                                   23
                                                    render meaningful content client-side

                                                    Main-text and metadata extraction from
  Boilerplate removal       Trafilatura                                                                  24
                                                    web pages

  Complex document                                  HTML/PDF/doc partitioning for LLM
                            Unstructured                                                                 25
  partitioning                                      pipelines

  PDF extraction            PyMuPDF                 Text, tables, blocks, words, OCR support             26


                            LangChain text          Standard splitter utilities for retrievable
  Chunking                                                                                               27
                            splitters               chunks

                            Sentence                Standard library for embedding and
  Embedding runtime                                                                                      28
                            Transformers            reranking




                                                        4
                            Recommended                                                               Official
  Layer                                             Why it fits this project
                            option                                                                    docs

                                                    Production serving for open embedding
  Embedding serving         Hugging Face TEI                                                             29
                                                    and reranker models

For embeddings, I would use one of three tracks. For a small local prototype, use all-MiniLM-L6-v2 . For
a better open-source English retriever with very manageable storage, use bge-small-en-v1.5 or bge-
base-en-v1.5 . For a more ambitious production retriever that can support hybrid or multilingual
scenarios, use bge-m3 . If you prefer an API instead of self-hosting, OpenAI’s
text-embedding-3-small and text-embedding-3-large remain strong options, with the added
ability to shorten dimensions.    30




  Embedding model           Type        Dimensions      Input limit or behavior      Best use here            Docs

                                                        Intended for sentences/
  sentence-
                            Open-                       short paragraphs;            Fast local
  transformers/                                 384                                                            31
                            source                      truncates over 256           prototype
  all-MiniLM-L6-v2
                                                        word pieces

                                                                                     Best default
  BAAI/bge-small-           Open-                       Public serving docs list
                                                384                                  open-source               32
  en-v1.5                   source                      512 max input tokens
                                                                                     starting point

                                                                                     Higher recall,
  BAAI/bge-base-            Open-                       Public serving docs list
                                                768                                  moderate                  33
  en-v1.5                   source                      512 max input tokens
                                                                                     storage

                                                                                     Higher quality if
  BAAI/bge-large-           Open-                       Public serving docs list
                                               1024                                  storage/latency           34
  en-v1.5                   source                      512 max input tokens
                                                                                     are acceptable

                                                        Supports dense, sparse,
                            Open-                       and multigranular            Best advanced
  BAAI/bge-m3                                  1024                                                            35
                            source                      retrieval; up to 8192        hybrid option
                                                        tokens in model docs

  text-                                                 8192-token max input;
                                               1536                                  Strong API
  embedding-3-              API                         dimensions can be                                      36
                                             default                                 baseline
  small                                                 shortened

  text-                                                 8192-token max input;
                                               3072                                  Best API
  embedding-3-              API                         dimensions can be                                      36
                                             default                                 retrieval quality
  large                                                 shortened


For the vector database, choose based on the stage of the project, not hype. FAISS is best for a local
prototype. Qdrant is the strongest production choice in this set if you want native filtering, hybrid retrieval,
and payload metadata. Chroma is convenient for small projects and local-first teams. pgvector is excellent




                                                        5
when your organization already centers operations on Postgres and wants vector search inside the
relational stack. 37


  Vector
               Best stage             Strengths                           Main tradeoff                 Docs
  store

                                      Extremely strong local              Not a complete
  FAISS        Prototype / local      similarity search; GPU options      application database by        38

                                      available                           itself

                                      Vector DB with payload
                                                                          Separate service to
  Qdrant       Production             metadata, search APIs, hybrid                                      39
                                                                          operate
                                      search, multivector support

                                      Simple local/cloud developer        Less enterprise-oriented
               Prototype to
  Chroma                              experience; dense, sparse,          than Qdrant/Postgres           40
               small production
                                      metadata search                     stacks

               Production when                                            ANN and scaling
                                      Reuse SQL, transactions, and
  pgvector     already on                                                 ergonomics depend on           41
                                      existing ops
               Postgres                                                   your Postgres practice


Retrieval and prompting
For this use case, I recommend three retrieval architectures, in this order.


Baseline dense RAG is enough to get to value quickly. You embed chunks, embed the query, pull top-k
neighbors, and answer from those chunks with citations. This is the fastest path to a working assistant and
is appropriate if your corpus is modest and mostly English. 42


Recommended production architecture: hybrid retrieval plus reranking. This works better for Amazon
documentation because user questions often mix semantics and exact terminology. Examples include exact
fee names, packaging rules, acronyms, program names, report type values, and policy names. bge-m3
explicitly supports dense, sparse, and multigranular retrieval, and Qdrant’s hybrid query support makes
dense+sparse fusion practical in one system. Then rerank the candidate set with a cross-encoder. Sentence
Transformers’ documentation explicitly recommends retrieve-then-rerank patterns, and its MS MARCO
cross-encoder tables expose the throughput/quality tradeoff. 43


Fine-tuning should be reserved for behavior, not as the main way to ingest Amazon’s factual corpus.
OpenAI’s guidance frames prompt engineering, RAG, and fine-tuning as separate optimization levers; fine-
tuning is for getting the model to perform specific tasks or output styles better, while RAG is the right
mechanism for grounding on external knowledge. For your assistant, that means: do not fine-tune on raw
help pages to “teach” policy facts. Instead, fine-tune only if you later want better answer formatting, better
citation style, better question classification, or better refusal behavior. 44


Reranking is worth it here. The cross-encoder approach in Sentence Transformers is described as slower but
generally higher performing than a bi-encoder, and the published MS MARCO table reports about 1,800
docs/sec for cross-encoder/ms-marco-MiniLM-L6-v2 . If you rerank 50 candidates, the pure model



                                                       6
pass implied by that published throughput is about 28 milliseconds before application overhead; reranking
100 candidates is about 56 milliseconds. That is a very reasonable trade for policy accuracy. 45


Prompting should be strict and boring. Your system prompt should say, in effect: answer only from
retrieved Amazon documents; prefer current policy pages over educational summaries; cite every
substantive claim; if the retrieved context is insufficient, say so; if sources conflict, surface the conflict and
cite both; never fabricate a policy, fee, or approval rule. OpenAI’s prompt guidance explicitly recommends
locking citation format if your application requires citations. 46


For context packing, do not just stuff the top-k chunks into the prompt. First, deduplicate by document and
heading path. Second, merge adjacent chunks from the same section when they are part of the same
answer. Third, cap the final prompt to a small number of strong chunks rather than a large number of weak
ones. Fourth, place the dynamic RAG results later in the prompt, after the stable instructions, because that
is friendlier to provider-side prompt caching and reduces unnecessary token processing. 47


If you use structured outputs, include an explicit cannot_answer or insufficient_evidence field.
OpenAI’s structured outputs guide warns that a model can hallucinate to satisfy a schema when the input is
unrelated to the schema, so your prompt and schema should make abstention an allowed and expected
outcome. 48


Operations, evaluation, security, and cost
Refreshing the corpus should use change-aware crawling, not full re-downloads. HTTP already provides
the validators you need: ETag identifies a specific resource version, Last-Modified is a weaker
validator, and If-Modified-Since allows conditional re-fetches that return 304 Not Modified when
content has not changed. Store these headers at the document level and reindex only the documents
whose normalized content hash has changed. 20


Amazon’s seller content changes often enough that you should not treat the corpus as static. Public
examples include program-policy change notices, fee changes, inbound placement fee changes, SP-API
release notes, and other date-stamped update pages. That means your crawl schedule should be tiered:
change hubs and fee pages daily; major policy and FBA hubs every few days; stable evergreen educational
pages weekly. 49


Evaluation should be built in from the first index, not after launch. OpenAI’s evaluation best-practices
guidance emphasizes continuous evaluation, and Anthropic’s evaluation guidance makes the same point
from the prompt-engineering side. For this assistant, create a test set with at least five categories: direct
factual policy questions, fee questions, document-location questions, conflict/ambiguity questions, and
unanswerable questions. Track not just answer quality, but also citation coverage, source fidelity, retrieval
recall, abstention correctness, and latency. 50


Hallucination mitigation should be layered. First, use retrieval plus reranking. Second, instruct the model to
answer only from evidence. Third, require citations tied to actual retrieved chunks. Fourth, add an output
guardrail or judge pass to detect unsupported claims. OpenAI’s hallucination-guardrails cookbook describes
exactly this kind of output-checking workflow. 51




                                                         7
Security matters because this assistant will likely run against sensitive account-linked data or privileged
seller workflows. Use least privilege for every component and every principal. Keep the raw document
bucket separate from the vector index. Use short-lived credentials for the crawler or browser session if you
must access authenticated pages. Store access scope in metadata so the retriever never returns a chunk a
user should not see. NIST defines least privilege as restricting access to the minimum necessary, and
OWASP’s LLM/agent guidance should shape your threat model, especially around prompt injection and
sensitive information disclosure. 52


Prompt injection is not only a web-search problem. In a retrieval system, it can arrive inside a crawled page,
an uploaded PDF, or user-provided “helpful notes.” Your assistant should treat retrieved text as data, not as
trusted instructions. Strip or sandbox suspicious instruction-like content in documents, keep system
instructions separate from retrieved context, and never let retrieved text invoke tools or alter policies.
OWASP explicitly identifies prompt injection as the leading GenAI application risk. 53


The main cost tradeoff is between embedding quality, vector size, and infrastructure simplicity. Larger
vectors generally improve recall but cost more to store and search. For 100,000 chunks stored as raw
float32 vectors, 384-dimensional vectors occupy about 146.5 MiB, 768-dimensional vectors about 293.0 MiB,
1024-dimensional vectors about 390.6 MiB, 1536-dimensional vectors about 585.9 MiB, and 3072-
dimensional vectors about 1.17 GiB before metadata and indexing overhead.


For embedding API cost, the official docs currently make the economics of small and mid-sized corpora look
very favorable. OpenAI’s embedding guide states that text-embedding-3-small yields roughly 62,500
pages per dollar under an assumption of about 800 tokens per page, and its model page currently lists a
cost of $0.02 per 1M tokens. Cloudflare’s Workers AI pricing page lists the same order of magnitude for
hosted BAAI embeddings: $0.020/M input tokens for bge-small-en-v1.5 , $0.067/M for bge-base-en-
v1.5 , $0.204/M for bge-large-en-v1.5 , and $0.012/M for bge-m3 . Under a purely illustrative
assumption of 20,000 pages at 800 tokens each, those rates imply about $0.32 for bge-small , $1.07 for
bge-base , $3.26 for bge-large , and $2.08 for OpenAI text-embedding-3-large . Because provider
pricing can change, the right production habit is to calculate it from the current pricing page during
deployment, not to hard-code stale numbers into your design. 54


Implementation roadmap
The roadmap below assumes no budget or compute constraints were specified and that you want a
practical, engineering-first rollout rather than a research prototype.


                                                                  Estimated
  Milestone          Deliverable                                               Required skills
                                                                      effort

                     Approved source list, compliance                          Product owner, technical
  Scope and                                                          0.5–1.5
                     memo, domain/path allowlist, seed                         lead, counsel/compliance
  policy review                                                         days
                     URLs                                                      review

                     Seed crawler, URL normalizer, dedupe
  Discovery
                     rules, discovery queue, crawl                 1–2 days    Python, HTTP, web scraping
  crawler
                     manifest




                                                      8
                                                                Estimated
 Milestone          Deliverable                                               Required skills
                                                                    effort

                    HTML/PDF extraction, boilerplate
 Extraction                                                                   Python, document parsing,
                    cleanup, table/FAQ preservation,             2–4 days
 pipeline                                                                     text processing
                    metadata capture

                    Chunker, embedding job, vector store
 Indexing                                                                     NLP/ML engineering, data
                    schema, versioned document/chunk             1–3 days
 pipeline                                                                     engineering
                    IDs

                    Retriever, reranker, citation formatter,                  Backend, LLM/RAG, prompt
 Query service                                                   2–4 days
                    answer synthesis prompt                                   design

                    Conditional fetch, change detection,
 Refresh and
                    partial reindex, dashboards, failure         1–3 days     Backend, ops, observability
 monitoring
                    alerts

 Evaluation         Gold QA set, citation tests,
                                                                 1–3 days     QA, LLM evals, analytics
 harness            hallucination checks, regression suite

 Security           Access controls, injection tests, secret                  Security engineering,
                                                                 1–2 days
 hardening          handling, audit logging                                   backend

 Production         Staging, canary, feedback loop,
                                                                 1–2 days     DevOps, product, support
 rollout            ongoing coverage review

If you want the shortest realistic path, build milestones one through five first and use open-source
embeddings + FAISS. If you want the best long-run production path, move to Qdrant + hybrid retrieval +
reranking by the time you finish milestones six through nine. 55


Reference artifacts
A good vector-store record should look more like a document registry than a bare “text + embedding” row.


 Field                             Type             Purpose

  chunk_id                         string           Stable unique ID for the chunk

                                                    Stable parent document ID, ideally normalized from
  doc_id                           string
                                                    Amazon’s external/G... identifier

  canonical_url                    string           Normalized URL used for retrieval and citation

  source_url                       string           Exact fetched URL before normalization

                                                      sellercentral.amazon.com ,
  domain                           string             sell.amazon.com , developer-
                                                    docs.amazon.com , etc.




                                                      9
 Field                            Type            Purpose

                                                  help_page , policy , agreement ,
  source_type                     enum            seller_university , sp_api , pdf ,
                                                  secondary_forum

  title                           string          Document title

  section_title                   string          Local heading for the chunk

  heading_path                    array[string]   Full heading ancestry

  locale                          string          en-US , fr-FR , etc.

  marketplace                     string          US , CA , EU , global , unknown

                                                  Human-readable update text parsed from page when
  last_updated_text               string/null
                                                  present

  etag                            string/null     HTTP validator

                                  datetime/
  last_modified                                   HTTP validator
                                  null

  content_hash                    string          Hash of normalized content

                                                  trafilatura , bs4 , playwright , pymupdf ,
  extraction_method               string
                                                  etc.

  chunk_index                     int             Position within parent document

  chunk_text                      text            Cleaned chunk text

  token_count                     int             Approximate token count

  embedding_model                 string          Embedding model used

  embedding_version               string          Version tag for re-embedding

                                                  public , seller-authenticated , internal-
  access_scope                    enum
                                                  only

  retrieval_weight                float           Optional source-priority weighting

  is_authoritative                bool            True for official Amazon docs

  version_created_at              datetime        When this version entered the index

  supersedes_doc_version          string/null     Link to previous doc version


The pipeline diagram below is the architecture I would recommend for a robust implementation.




                                                   10
                                                                                                HTML simple       BeautifulSoup and
                                                                                                                     Trafilatura


   Seed URLs and search   URL normalization and
         discovery              allowlist         HTTP fetch with Requests        HTML or PDF                                                                                           User query     Query embedding
                                                                                                HTML dynamic      Playwright fallback

                                                                                                                                         Structured document
                                                                                                                                                 JSON
                                                                                                                                                                                                                                                             Prompt builder with
                                                                                                                                                               Section aware chunking   Embeddings       Vector store        Retriever   Optional reranker                         LLM answer
                                                                                                    PDF        PyMuPDF or Unstructured                                                                                                                           citations


                           ETag Last-Modified
                            change monitor


                                                                                                                                                                                                     Document registry and
                                                                                                                                                                                                        metadata store




The minimal example below uses Requests, Beautiful Soup, LangChain text splitters, Sentence
Transformers, and FAISS. Those are all documented in their official docs, and the embedding models used
here are openly available.                                                   56




  # pip install requests beautifulsoup4 trafilatura pymupdf langchain-text-
  splitters
  # pip install sentence-transformers faiss-cpu


  from __future__ import annotations

  import hashlib
  import json
  import re
  import time
  from collections import deque
  from dataclasses import dataclass, asdict
  from pathlib import Path
  from typing import Iterable
  from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

  import fitz # PyMuPDF
  import numpy as np
  import requests
  import trafilatura
  from bs4 import BeautifulSoup
  from langchain_text_splitters import RecursiveCharacterTextSplitter
  from sentence_transformers import SentenceTransformer
  import faiss

  ALLOWED_DOMAINS = {
      "sellercentral.amazon.com",
      "sell.amazon.com",
      "developer-docs.amazon.com",
  }

  ALLOWED_PREFIXES = (
      "/help/hub/reference/",
      "/learn/",
      "/sp-api/docs/",
  )




                                                                                                                                                        11
SEED_URLS = [
    "https://sellercentral.amazon.com/help/hub/reference/",
    "https://sellercentral.amazon.com/help/hub/reference/external/G521",
    "https://sellercentral.amazon.com/help/hub/reference/external/G53921",
    "https://sellercentral.amazon.com/help/hub/reference/external/G201074410",
    "https://sell.amazon.com/learn/seller-university",
    "https://developer-docs.amazon.com/sp-api/docs/welcome",
]


OUT_DIR = Path("amazon_docs")
OUT_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "YourCompanyKnowledgeIndexer/1.0 (+contact@example.com)",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

@dataclass
class Document:
    doc_id: str
    canonical_url: str
    source_url: str
    domain: str
    source_type: str
    title: str
    heading_path: list[str]
    locale: str | None
    etag: str | None
    last_modified: str | None
    content_hash: str
    extraction_method: str
    text: str



def normalize_url(url: str) -> str:
    """Drop noisy query params, keep locale-ish params when relevant."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc not in ALLOWED_DOMAINS:
        return ""

    clean_pairs = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):



                                       12
        if k.lower() in {
            "locale", "mons_sel_locale"
        }:
            clean_pairs.append((k, v))


    path = re.sub(r"/+$", "", parsed.path)
    return urlunparse((parsed.scheme, parsed.netloc, path, "",
urlencode(clean_pairs), ""))



def url_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        return False
    return parsed.path.startswith(ALLOWED_PREFIXES)



def make_doc_id(url: str) -> str:
    # Prefer Amazon's stable external/G... pattern when present.
    m = re.search(r"/external/([A-Z0-9]+)$", url)
    if m:
        return m.group(1)
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]



def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        href = normalize_url(href)
        if href and url_allowed(href):
            links.append(href)
    return sorted(set(links))



def extract_html(url: str, html: str, response: requests.Response) -> Document:
    soup = BeautifulSoup(html, "html.parser")

    # Fast title fallback
    title = soup.title.get_text(" ", strip=True) if soup.title else url

    # Remove obvious chrome for fallback extraction
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Try main-content extraction first
    extracted = trafilatura.extract(



                                          13
        html,
        url=url,
        include_links=False,
        include_formatting=True,
        output_format="markdown",
        favor_precision=True,
    )

    if extracted:
        text = extracted.strip()
        extraction_method = "trafilatura"
    else:
        text = soup.get_text("\n", strip=True)
        extraction_method = "bs4"

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Basic locale parsing
    locale = None
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query))
    locale = q.get("locale") or q.get("mons_sel_locale")

    return Document(
        doc_id=make_doc_id(url),
        canonical_url=normalize_url(url),
        source_url=url,
        domain=parsed.netloc,
        source_type="html",
        title=title,
        heading_path=[],
        locale=locale,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        content_hash=content_hash,
        extraction_method=extraction_method,
        text=text,
    )



def extract_pdf(url: str, content: bytes, response: requests.Response) ->
Document:
    pdf = fitz.open(stream=content, filetype="pdf")
    pages = []
    for page in pdf:
        # sort=True gives a more natural reading order
        pages.append(page.get_text("text", sort=True))



                                       14
    text = "\n\n".join(pages).strip()
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return Document(
        doc_id=make_doc_id(url),
        canonical_url=normalize_url(url),
        source_url=url,
        domain=urlparse(url).netloc,
        source_type="pdf",
        title=pdf.metadata.get("title") or url,
        heading_path=[],
        locale=None,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        content_hash=content_hash,
        extraction_method="pymupdf",
        text=text,
    )



def fetch(url: str) -> tuple[Document | None, list[str]]:
    try:
         resp = SESSION.get(url, timeout=30)
         resp.raise_for_status()
    except Exception as exc:
         print(f"ERROR {url}: {exc}")
         return None, []

    ctype = resp.headers.get("Content-Type", "").lower()
    if "application/pdf" in ctype or url.lower().endswith(".pdf"):
        doc = extract_pdf(url, resp.content, resp)
        return doc, []

    html = resp.text
    doc = extract_html(url, html, resp)
    links = extract_links(html, url)
    return doc, links



def crawl(seeds: Iterable[str], max_pages: int = 200) -> list[Document]:
    queue = deque(normalize_url(u) for u in seeds)
    seen = set()
    docs: list[Document] = []

    while queue and len(docs) < max_pages:
        url = queue.popleft()
        if not url or url in seen:
            continue



                                          15
        seen.add(url)

        doc, links = fetch(url)
        if doc and doc.text:
            docs.append(doc)
            print(f"OK {len(docs):03d}     {doc.doc_id}    {doc.title[:80]}")
        else:
            print(f"SKIP {url}")


        for link in links:
            if link not in seen:
                queue.append(link)

        time.sleep(1.5)   # be conservative

    return docs



def chunk_documents(docs: list[Document]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )
    chunks = []

    for doc in docs:
        parts = splitter.split_text(doc.text)
        for idx, chunk in enumerate(parts):
            chunks.append(
                {
                     "chunk_id": f"{doc.doc_id}:{idx}",
                     "doc_id": doc.doc_id,
                     "title": doc.title,
                     "canonical_url": doc.canonical_url,
                     "source_type": doc.source_type,
                     "locale": doc.locale,
                    "chunk_index": idx,
                    "text": chunk,
                }
            )
    return chunks



def build_faiss_index(chunks: list[dict], model_name: str = "BAAI/bge-small-en-
v1.5"):
    model = SentenceTransformer(model_name)
    texts = [c["text"] for c in chunks]



                                          16
    vectors = model.encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype("float32")

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    faiss.write_index(index, str(OUT_DIR / "index.faiss"))
    with open(OUT_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
        for row in chunks:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return model, index, chunks



def load_chunks(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows



def query(question: str, model: SentenceTransformer, index: faiss.Index,
chunks: list[dict], top_k: int = 8):
    q = model.encode([question], normalize_embeddings=True).astype("float32")
    scores, ids = index.search(q, top_k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        row = chunks[idx].copy()
        row["score"] = float(score)
        results.append(row)
    return results



if __name__ == "__main__":
    docs = crawl(SEED_URLS, max_pages=100)

    with open(OUT_DIR / "documents.jsonl", "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(asdict(doc), ensure_ascii=False) + "\n")



                                       17
       chunks = chunk_documents(docs)
       model, index, chunks = build_faiss_index(chunks)

       question = "What documents matter most for FBA sellers doing retail
  arbitrage?"
      hits = query(question, model, index, chunks, top_k=5)

       print("\nTop results:\n")
       for h in hits:
           print(f"[{h['score']:.3f}] {h['title']}                {h['canonical_url']}")
           print(h["text"][:500], "\n")


If Seller Central pages render only an application shell for your direct fetches, add a Playwright fallback for
the small subset of pages that need browser rendering instead of converting your whole crawler into a
browser bot. 57



  # pip install playwright
  # python -m playwright install chromium

  from playwright.sync_api import sync_playwright

  def fetch_with_playwright(url: str) -> str:
      with sync_playwright() as p:
          browser = p.chromium.launch(headless=True)
          page = browser.new_page()
          page.goto(url, wait_until="networkidle", timeout=60000)
          html = page.content()
          browser.close()
          return html


A high-quality testing checklist for this assistant should cover more than relevance. It should verify
grounding, freshness, and safe failure behavior, because those matter more than eloquence in a policy
assistant. The evaluation frameworks from OpenAI and Anthropic both emphasize explicit success criteria,
ongoing regression testing, and continuous evaluation. 50


Testing checklist


     • Verify that every answered factual claim cites at least one retrieved Amazon source chunk.
     • Verify that the cited chunk actually contains the evidence claimed.
     • Verify that the assistant abstains when retrieval returns weak or no evidence.
     • Verify that forum or community content never outranks authoritative policy pages unless the user
       explicitly asks for community advice.
     • Verify that locale-specific answers do not mix US and non-US policy pages without saying so.
     • Verify that “latest fee/policy” questions prefer date-stamped update pages over evergreen
       summaries.



                                                      18
          • Verify that adjacent chunks from the same section are merged correctly and not cited as separate
            contradictory sources.
          • Verify that tables and bullets survive extraction in a usable form.
          • Verify that malicious text inside retrieved documents cannot override system instructions.
          • Verify that access-scoped documents cannot be retrieved by unauthorized users.
          • Verify that re-crawling unchanged pages does not trigger unnecessary re-embedding.
          • Verify that a changed document produces a new document version and supersedes the old one
            without orphaned citations.

Sample evaluation queries


          • What Amazon policy pages are most relevant if I source inventory from retail stores and send it to
            FBA?
          • What is the current drop shipping policy, and how does it differ from buying inventory first and
            reselling it through FBA?
          • Which official pages explain invoice requirements for appealing a policy violation?
          • What official Amazon pages should I read before listing used books via FBA?
          • What restrictions apply to products that require approval before listing?
          • What official FBA pages explain inbound shipment creation and prep requirements?
          • What pages discuss used-sold-as-new condition issues and how to prevent them?
          • What are the latest 2026 US FBA fee changes mentioned in official Amazon pages?
          • If I ask about “arbitrage,” can you show me the closest official policy pages even if Amazon doesn’t
            use that exact term?
          • Which part of the source text supports your answer that invoices must contain supplier information?
          • I’m not asking for community opinions. Show me only official Amazon pages about authenticity,
            invoices, and FBA restrictions.
          • If there is no official Amazon source answering my question, say that directly and do not guess.

The most important practical conclusion is this: you can absolutely build a very strong Amazon FBA/
arbitrage assistant, but the professional version is not “scrape everything once.” It is: define source scope,
normalize and version official documents, retrieve by section with citations, refresh continuously,
and stay inside Amazon’s published agreement and copyright boundaries—or get permission for
anything broader. 58



 1    5    Amazon Seller Central Help
https://sellercentral.amazon.com/help/hub/reference/?utm_source=chatgpt.com

 2   11    Amazon Services Business Solutions Agreement
https://sellercentral.amazon.com/help/hub/reference/external/G1791?utm_source=chatgpt.com

 3   56    Quickstart — Requests 2.34.2 documentation
https://requests.readthedocs.io/en/latest/user/quickstart/?utm_source=chatgpt.com

 4    9     49   Changes to program policies
https://sellercentral.amazon.com/help/hub/reference/external/GQHQGBTD7XB7EECN?utm_source=chatgpt.com

 6   Get started with Fulfillment by Amazon (FBA)
https://sellercentral.amazon.com/help/hub/reference/external/G53921?locale=zh-TW&utm_source=chatgpt.com




                                                            19
 7   Learn about Seller University | Sell on Amazon
https://sell.amazon.com/learn/seller-university?utm_source=chatgpt.com

 8   Agent Policy
https://sellercentral.amazon.com/help/hub/reference/external/GS83KH2MA7HM69PH?utm_source=chatgpt.com

10   13   14   58   Conditions of use
https://shipping.amazon.com/site-terms?utm_source=chatgpt.com

12   RFC 9309: Robots Exclusion Protocol
https://www.rfc-editor.org/info/rfc9309/?utm_source=chatgpt.com

15   Program Policies
https://sellercentral.amazon.com/help/hub/reference/external/G521?utm_source=chatgpt.com

16   21   Requests: HTTP for Humans - Read the Docs
https://requests.readthedocs.io/?utm_source=chatgpt.com

17   24   Trafilatura
https://trafilatura.readthedocs.io/?utm_source=chatgpt.com

18   25   Partitioning
https://docs.unstructured.io/open-source/core-functionality/partitioning?utm_source=chatgpt.com

19   27   Text splitter integrations - Docs by LangChain
https://docs.langchain.com/oss/python/integrations/splitters?utm_source=chatgpt.com

20   ETag header - HTTP - MDN Web Docs
https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag?utm_source=chatgpt.com

22   Beautiful Soup 4.14.3 documentation - Crummy
https://www.crummy.com/software/BeautifulSoup/bs4/doc/?utm_source=chatgpt.com

23   57   Installation | Playwright Python
https://playwright.dev/python/docs/intro?utm_source=chatgpt.com

26   PyMuPDF documentation
https://pymupdf.readthedocs.io/?utm_source=chatgpt.com

28   SentenceTransformers Documentation — Sentence ...
https://sbert.net/?utm_source=chatgpt.com

29   huggingface/text-embeddings-inference
https://github.com/huggingface/text-embeddings-inference?utm_source=chatgpt.com

30   31   sentence-transformers/all-MiniLM-L6-v2
https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2?utm_source=chatgpt.com

32   bge-small-en-v1.5 - Workers AI
https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/?utm_source=chatgpt.com

33   bge-base-en-V1.5 - Workers AI
https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/?utm_source=chatgpt.com

34   bge-large-en-v1.5 - Workers AI
https://developers.cloudflare.com/workers-ai/models/bge-large-en-v1.5/?utm_source=chatgpt.com




                                                             20
35   43   BAAI/bge-m3
https://huggingface.co/BAAI/bge-m3?utm_source=chatgpt.com

36   54   Vector embeddings | OpenAI API
https://developers.openai.com/api/docs/guides/embeddings?utm_source=chatgpt.com

37   38   55   Welcome to Faiss Documentation — Faiss documentation
https://faiss.ai/index.html?utm_source=chatgpt.com

39   Qdrant Documentation
https://qdrant.tech/documentation/?utm_source=chatgpt.com

40   Chroma Docs: Introduction
https://docs.trychroma.com/docs/overview/introduction?utm_source=chatgpt.com

41   pgvector/pgvector: Open-source vector similarity search for ...
https://github.com/pgvector/pgvector?utm_source=chatgpt.com

42   Build a semantic search engine with LangChain
https://docs.langchain.com/oss/python/langchain/knowledge-base?utm_source=chatgpt.com

44   Optimizing LLM Accuracy | OpenAI API
https://developers.openai.com/api/docs/guides/optimizing-llm-accuracy?utm_source=chatgpt.com

45   Usage — Sentence Transformers documentation
https://sbert.net/docs/cross_encoder/usage/usage.html?utm_source=chatgpt.com

46   Prompt guidance | OpenAI API
https://developers.openai.com/api/docs/guides/prompt-guidance?utm_source=chatgpt.com

47   Latency optimization | OpenAI API
https://developers.openai.com/api/docs/guides/latency-optimization?utm_source=chatgpt.com

48   Structured model outputs | OpenAI API
https://developers.openai.com/api/docs/guides/structured-outputs?utm_source=chatgpt.com

50   Evaluation best practices | OpenAI API
https://developers.openai.com/api/docs/guides/evaluation-best-practices?utm_source=chatgpt.com

51   Retrieve & Re-Rank Pipeline
https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html?utm_source=chatgpt.com

52   least privilege - Glossary - NIST CSRC
https://csrc.nist.gov/glossary/term/least_privilege?utm_source=chatgpt.com

53   LLM01:2025 Prompt Injection - OWASP Gen AI Security Project
https://genai.owasp.org/llmrisk/llm01-prompt-injection/?utm_source=chatgpt.com




                                                             21
