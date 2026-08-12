# Week 3 AI POC — Ask My Recipes (Retrieval & RAG)

A mini **"ask my documents"** app for the **Recipes & Food** topic. Load recipe
documents, ask a question in plain English, and get an answer built **only** from
those documents — **with a citation to the source**. If the answer isn't in the
documents, it says **"I don't know"** instead of inventing one.

This implements the Week-3 brief and carries forward the Week-1 (embeddings,
tokens, hallucination) and Week-2 (structured output, validation/retry,
guardrails, keys in `.env`) foundations.

## Architecture

Standard layered / two-pipeline RAG design:

```
INGESTION PIPELINE   load ─► chunk ─► embed (bi-encoder) ─► store (Chroma / HNSW)
QUERY PIPELINE       validate ─► embed query ─► retrieve top-K ─► rerank (cross-encoder)
                     ─► grounding check ─► grounded generation (cited / "I don't know")
```

| Layer | Folder | Responsibility |
|-------|--------|----------------|
| Core | `app/core` | config (`.env`), logging |
| Models | `app/models` | Pydantic schemas (typed contracts) |
| Ingestion | `app/ingestion` | loaders, chunker (size/overlap), pipeline |
| Embeddings | `app/embeddings` | BGE bi-encoder |
| Vector store | `app/vectorstore` | ChromaDB (HNSW, cosine, metadata filter) |
| Retrieval | `app/retrieval` | dense retriever + cross-encoder reranker |
| Guardrails | `app/guardrails` | input validation, prompt-injection, grounding |
| Generation | `app/generation` | prompts + Gemini structured output (`instructor`) |
| Service | `app/services` | orchestrates the query pipeline |
| Interfaces | `app/api`, `app/cli.py` | FastAPI REST + CLI |

## Tech stack
- **Embeddings:** `sentence-transformers` — `BAAI/bge-small-en-v1.5` (bi-encoder)
- **Reranker:** `BAAI/bge-reranker-base` (cross-encoder)
- **Vector DB:** ChromaDB (local, persistent, HNSW)
- **LLM:** Google **Gemini** (`gemini-2.5-flash`) via `instructor` (structured output)
- **Interfaces:** Typer CLI + FastAPI

## Setup

```powershell
# 1. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your (free) Gemini key
Copy-Item .env.example .env
# then edit .env and set GEMINI_API_KEY=...   (get one at https://aistudio.google.com/apikey)
```

> The first `ingest`/`ask` downloads the BGE models (~150 MB) from Hugging Face.

## Usage — CLI

```powershell
# Build the index from data/raw
python -m app.cli ingest --reset

# Ask questions (grounded + cited)
python -m app.cli ask "What temperature do I bake chocolate chip cookies at?"
python -m app.cli ask "How long do I simmer the Thai green curry?"

# Out-of-corpus question -> should say it doesn't know
python -m app.cli ask "How do I change a car tyre?"

# Try a different chunk size
python -m app.cli ingest --reset --chunk-size 400 --chunk-overlap 60

# Index stats
python -m app.cli stats
```

## Usage — API

```powershell
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/docs
```

- `POST /ingest?reset=true` — build the index
- `POST /ask` — body `{ "question": "..." }`
- `GET /health`

## Compare chunk sizes (mentor check)

```powershell
python -m scripts.evaluate_chunking
```

Runs the same probe questions across chunk sizes **300 / 800 / 1500** and prints
the best-matching chunk and similarity for each — showing why chunk size matters.

## How this meets the mentor's checks
- ✅ **Answers correctly from the documents** — grounded generation over retrieved chunks.
- ✅ **Every answer shows its source** — `citations` + `sources` in every response.
- ✅ **Admits when it doesn't know** — grounding threshold + `can_answer=false` refuse to guess.
- ✅ **More than one chunk size** — `ingest --chunk-size ...` and `evaluate_chunking.py`.

## Adding your own documents
Drop `.md`, `.txt` or `.pdf` files into `data/raw/`, then re-run
`python -m app.cli ingest --reset`.
