# Architecture & Implementation Guide — Week 3 AI POC

This document explains **how the project is structured**, **what each piece does**,
and **how a request flows through the system**. It is the companion to `README.md`
(which covers setup and usage).

---

## 1. The big picture

The app is a **Retrieval-Augmented Generation (RAG)** system: it answers questions
using *your* documents instead of the model's general knowledge, cites the source,
and refuses ("I don't know") when the answer isn't in the documents.

It is organized around **two pipelines** and a **clean layered architecture**. The
golden rule of the layering: **dependencies point inwards / downwards**. Interfaces
(CLI, API) call the **service**, the service calls **capability layers**
(ingestion, retrieval, generation, guardrails), and every layer speaks in terms of
**typed Pydantic models**. No layer reaches "up" to the one that called it.

```
                ┌─────────────────────────────────────────────┐
   Interfaces   │   app/cli.py        app/api/routes.py         │
                └───────────────┬───────────────┬───────────────┘
                                │               │
   Service                     ▼               ▼
                        ┌───────────────────────────────┐
                        │   app/services/rag_service.py  │  (query orchestration)
                        └───┬───────────┬───────────┬────┘
                            │           │           │
   Capabilities            ▼           ▼           ▼
              ┌───────────────┐ ┌────────────┐ ┌────────────────┐
              │ retrieval/    │ │ guardrails/│ │ generation/    │
              │ (retriever,   │ │ (validate, │ │ (prompts,      │
              │  reranker)    │ │  grounding)│ │  generator)    │
              └───┬───────────┘ └────────────┘ └───────┬────────┘
                  │                                     │
   Foundations    ▼                                     ▼
        ┌──────────────┐ ┌───────────────┐ ┌─────────────────────┐
        │ embeddings/  │ │ vectorstore/  │ │ ingestion/          │
        │ (bi-encoder) │ │ (ChromaDB)    │ │ (loaders, chunker,  │
        └──────────────┘ └───────────────┘ │  pipeline)          │
                                            └─────────────────────┘
        ┌──────────────────────── core/ (config, logging) ───────────────────────┐
        └──────────────────────── models/ (Pydantic schemas) ────────────────────┘
```

---

## 2. The two pipelines

### 2.1 Ingestion pipeline (offline — run when documents change)

```
data/raw/*.{md,txt,pdf}
      │  loaders.load_directory()        -> list[Document]
      ▼
   chunker.chunk_documents()             -> list[Chunk]     (split by size/overlap)
      │
      ▼
   embedder.embed_documents()            -> list[vector]    (BGE bi-encoder)
      │
      ▼
   ChromaStore.add()                     -> persisted in storage/chroma  (HNSW index)
```

Entry point: **`app/ingestion/pipeline.py :: ingest()`**. Invoked by
`python -m app.cli ingest` or `POST /ingest`.

### 2.2 Query pipeline (online — every question)

```
question
   │  guards.validate_question()         (reject empty / too long / injection)
   ▼
   retriever.retrieve()                  -> top-K candidates   (bi-encoder + Chroma)
   │
   ▼
   reranker.rerank()                     -> top-N reranked     (cross-encoder)
   │
   ▼
   guards.is_grounded()  ── no ──►  return "I don't know"  (never calls the LLM)
   │ yes
   ▼
   generator.generate()                  -> GroundedAnswer     (Gemini + instructor)
   │
   ▼
   AskResponse {answer, can_answer, citations, sources}
```

Entry point: **`app/services/rag_service.py :: RagService.ask()`**. Invoked by
`python -m app.cli ask "..."` or `POST /ask`.

---

## 3. Layer-by-layer: every file and what it does

### `app/core/` — cross-cutting foundations
| File | Responsibility |
|------|----------------|
| `config.py` | A single `Settings` object (pydantic-settings) holding **every tunable knob**: model names, chunk size/overlap, top_k, rerank_top_n, `score_threshold`, paths, and the **`GEMINI_API_KEY` (loaded from `.env`, never hard-coded)**. `get_settings()` is `lru_cache`d so the same config is reused everywhere. |
| `logging.py` | `get_logger(name)` — one consistent log format, configured once. Every module logs through it so you can watch the pipeline run. |

### `app/models/schemas.py` — the typed contracts
The "nouns" that flow between layers. Because they're Pydantic, they validate
themselves and serialize cleanly to JSON for the API.
- **`Document`** — a whole raw file (before chunking).
- **`Chunk`** — one searchable piece: `id`, `text`, `source`, `source_path`, `chunk_index`, `metadata`.
- **`RetrievedChunk`** — a `Chunk` + its relevance `score`.
- **`Citation`** — `{source, snippet}`: a pointer back to the document that supports a claim.
- **`GroundedAnswer`** — *what the LLM is forced to return*: `{can_answer, answer, citations}`.
- **`AskRequest` / `AskResponse` / `IngestResponse`** — the API request/response shapes.

### `app/ingestion/` — get documents into the index
| File | Responsibility |
|------|----------------|
| `loaders.py` | Reads files from disk into `Document`s. Handles `.md`/`.txt` directly and `.pdf` via `pypdf`. Skips unsupported/empty files. `load_directory()` walks the folder recursively. |
| `chunker.py` | **The heart of "chunk size matters."** A dependency-free **recursive character splitter**: it splits on the biggest natural boundary that fits (`\n\n` → `\n` → `. ` → ` ` → hard cut), so chunks stay coherent. Then `_apply_overlap()` slides a window so adjacent chunks share context (an answer split across a boundary isn't lost). Both `chunk_size` and `chunk_overlap` are parameters — that's what lets us A/B different sizes. |
| `pipeline.py` | Orchestrates **load → chunk → embed → store**, with an optional `reset` to rebuild from scratch. Returns an `IngestResponse` summary. |

### `app/embeddings/embedder.py` — text → vectors (bi-encoder)
Wraps `sentence-transformers` `BAAI/bge-small-en-v1.5`. A **bi-encoder** embeds the
query and each chunk **independently**, so retrieval is a fast nearest-neighbour
lookup. Two methods because BGE treats them differently:
- `embed_documents()` — passages, no prefix.
- `embed_query()` — prepends BGE's instruction (`"Represent this sentence for
  searching relevant passages: "`) which measurably improves retrieval.

Vectors are **L2-normalized**, so cosine similarity == dot product (what the vector
DB compares). Loaded once via an `lru_cache`d singleton because the model is heavy.

### `app/vectorstore/chroma_store.py` — the vector database
A thin wrapper over **ChromaDB** (persistent, on-disk, **HNSW** index, **cosine**
space). It stores our precomputed BGE vectors rather than letting Chroma embed.
- `add()` — **upserts** chunks + vectors; the deterministic `chunk.id` dedupes re-ingested content.
- `query()` — top-K nearest neighbours, converts Chroma's cosine *distance* back to a *similarity* (`1 - distance`), and supports a `where` **metadata filter** (e.g. restrict to one source file).
- `reset()` / `count()` — housekeeping for `ingest --reset` and `stats`.

### `app/retrieval/` — two-stage retrieval
| File | Responsibility |
|------|----------------|
| `retriever.py` | **Stage 1 (recall):** embed the query, pull the top-K nearest chunks from Chroma. Fast, casts a wide net. |
| `reranker.py` | **Stage 2 (precision):** a **cross-encoder** (`BAAI/bge-reranker-base`) reads each `(query, chunk)` pair *together* and scores relevance directly — slower but far more accurate, so we only run it on the K candidates from stage 1. Raw scores are logits; we squash them through a **sigmoid** into 0..1 so the grounding threshold is meaningful. Returns the top-N, re-sorted. |

This bi-encoder-then-cross-encoder design is the exact "bi- vs cross-encoder"
trade-off from the Week-3 syllabus: cheap approximate recall, then expensive
accurate precision on a short list.

### `app/guardrails/guards.py` — safety and grounding
Three defenses:
1. **`validate_question()`** — rejects empty / over-long input and screens for
   **prompt-injection** patterns ("ignore previous instructions", "reveal your
   prompt", …), raising `InputValidationError`.
2. **`is_grounded()`** — the **"I don't know" gate**. If the best reranked score is
   below `score_threshold` (**0.55**, calibrated so irrelevant≈0.50 is rejected and
   relevant≈0.73 passes), the service refuses **before ever calling the LLM** — so
   it can't hallucinate and costs nothing.

### `app/generation/` — grounded, cited answers
| File | Responsibility |
|------|----------------|
| `prompts.py` | `SYSTEM_PROMPT` encodes the rules: answer **only** from context, cite sources, say "I don't know" rather than invent, and treat context as **untrusted data** (a light prompt-injection defense). `build_context()` renders the retrieved chunks into a numbered, source-labelled block. |
| `generator.py` | Calls **Gemini** through **`instructor`**, forcing the reply into the `GroundedAnswer` schema with **automatic validation + retry** (`max_retries`). So the program *always* gets `{can_answer, answer, citations}` back — never free text it can't parse. |

### `app/services/rag_service.py` — the query orchestrator
The single brain that runs the query pipeline in order: **validate → retrieve →
rerank → ground-check → generate**, and assembles the final `AskResponse` (including
the deduplicated list of source documents). Both interfaces call this, so CLI and
API behave identically. Note the generator is created **lazily** — retrieval-only
flows and `evaluate_chunking.py` don't need a Gemini key.

### Interfaces
| File | Responsibility |
|------|----------------|
| `app/cli.py` | Typer CLI with `ingest`, `ask`, `stats`. Renders answers, a citations table, and sources with `rich`. |
| `app/api/routes.py` | FastAPI routes: `POST /ingest`, `POST /ask`, `GET /health`. Builds one `RagService` at import (models load once). Maps `InputValidationError` → HTTP 422, ingestion errors → 400. |
| `app/main.py` | Creates the `FastAPI` app, mounts the router, exposes `/docs`. |

### `scripts/evaluate_chunking.py`
Runs the same probe questions across chunk sizes **300 / 800 / 1500** and prints the
best-matching chunk + similarity for each — **evidence for the mentor's "did you try
more than one chunk size?" check**. Uses retrieval only (no LLM key needed).

---

## 4. How one question flows (concrete trace)

`ask "What temperature do I bake chocolate chip cookies at?"`

1. **CLI** parses args → `RagService.ask(question)`.
2. **`validate_question`** — non-empty, short, no injection → passes.
3. **`retriever.retrieve`** — `embed_query()` → Chroma returns the 8 nearest chunks
   (cookie chunks score highest, but some curry/pizza chunks sneak in).
4. **`reranker.rerank`** — cross-encoder rescores the 8, keeps top 4; the cookie
   chunk tops out around **0.73**.
5. **`is_grounded`** — 0.73 ≥ 0.55 → proceed.
6. **`generator.generate`** — builds the context block, calls Gemini via instructor;
   the model returns `GroundedAnswer(can_answer=True, answer="375°F (190°C)…",
   citations=[{source: "chocolate_chip_cookies.md", snippet: "…375°F…"}])`.
7. **Service** attaches `sources=["chocolate_chip_cookies.md"]` → `AskResponse`.
8. **CLI** prints the answer panel + citations table.

For `"How do I change a car tyre?"`: steps 1–4 run, but the best rerank score is
**~0.50 < 0.55**, so step 5 returns the **"I don't know"** refusal and the LLM is
never called.

---

## 5. Key design decisions (and why)

- **Two-stage retrieval** — bi-encoder recall is cheap over the whole corpus;
  cross-encoder precision is expensive, so it only reruns on the short list. Best of both.
- **Grounding gate before generation** — the cheapest, most reliable way to make the
  app "admit it doesn't know": if retrieval isn't confident, don't even ask the LLM.
- **Structured output via `instructor`** — guarantees a parseable, validated answer
  with citations, with retries — the Week-2 "answers your program can trust" idea.
- **Local embeddings** — no per-call cost, offline, and directly matches the
  MTEB/BGE/E5 family the syllabus names. Only generation uses a (free) API.
- **Everything configurable in `config.py`** — chunk size, K, threshold, models — so
  experiments (like chunk-size comparison) are one flag away, and secrets stay in `.env`.
- **Typed models at every boundary** — refactors are safe and the API serializes for free.

---

## 6. Mapping to the course

| Week | Concept | Where it lives |
|------|---------|----------------|
| 1 | Embeddings (text→numbers, meaning not keywords) | `embeddings/embedder.py` |
| 1 | Hallucination (why grounding matters) | `guardrails/guards.py`, `generation/prompts.py` |
| 2 | Structured output + Pydantic | `models/schemas.py`, `generation/generator.py` |
| 2 | Validation & retry | `generator.py` (`instructor` `max_retries`) |
| 2 | Guardrails / prompt injection | `guardrails/guards.py`, `prompts.py` |
| 2 | Keys out of code (`.env`) | `core/config.py`, `.env.example` |
| 3 | Chunking (size & overlap) | `ingestion/chunker.py`, `scripts/evaluate_chunking.py` |
| 3 | Bi-encoder vs cross-encoder | `retrieval/retriever.py` vs `retrieval/reranker.py` |
| 3 | Vector DB (HNSW), top-K, metadata filter | `vectorstore/chroma_store.py` |
| 3 | Grounded generation & citations | `generation/`, `services/rag_service.py` |
| 3 | "I don't know" | `guardrails/guards.py::is_grounded` |
