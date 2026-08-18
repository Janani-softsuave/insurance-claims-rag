# Insurance Claims RAG System — Week 3 AI POC

A **Retrieval-Augmented Generation** app for the Insurance Claims knowledge base. Ask questions in plain English and get answers built **only** from your documents — with a citation to the source. If the answer isn't in the documents, it says **"I don't know"** instead of inventing one.

---

## Architecture

```
INGESTION    load ─► chunk ─► embed (bi-encoder) ─► store (ChromaDB / HNSW)

QUERY        validate ─► embed query ─► retrieve top-K ─► rerank (cross-encoder)
             ─► grounding check ─► grounded generation (cited / "I don't know")
```

| Layer | Folder | Responsibility |
|-------|--------|----------------|
| Core | `app/core` | Config from `.env`, logging |
| Models | `app/models` | Pydantic schemas |
| Ingestion | `app/ingestion` | Loaders, chunker, pipeline |
| Embeddings | `app/embeddings` | BGE bi-encoder |
| Vector store | `app/vectorstore` | ChromaDB (HNSW, cosine) |
| Retrieval | `app/retrieval` | Dense retriever + cross-encoder reranker |
| Guardrails | `app/guardrails` | Input validation, prompt-injection, grounding gate |
| Generation | `app/generation` | Prompts + Gemini via `instructor` |
| Service | `app/services` | Query pipeline orchestrator |
| Interfaces | `app/cli.py`, `streamlit_app.py` | CLI + Streamlit UI |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Embeddings | `BAAI/bge-small-en-v1.5` (local, bi-encoder) |
| Reranker | `BAAI/bge-reranker-base` (local, cross-encoder) |
| Vector DB | ChromaDB — HNSW index, cosine space |
| LLM | Google Gemini (`gemini-flash-latest`) |
| Structured output | `instructor` + Pydantic |
| UI | Streamlit |
| CLI | Typer + Rich |

---

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set: GEMINI_API_KEY=your-key-here
# Get a free key at https://aistudio.google.com/apikey
```

> First run downloads BGE models (~150 MB) from Hugging Face automatically.

---

## Running the App

### Streamlit UI
```powershell
streamlit run streamlit_app.py
```
Open **http://localhost:8501** — upload documents, configure chunking, and ask questions from the browser.

### CLI
```powershell
# Ingest documents
python -m app.cli ingest --reset

# Ask a question
python -m app.cli ask "How soon must I report a theft claim?"

# Try a different chunk size
python -m app.cli ingest --reset --chunk-size 300 --chunk-overlap 50

# Index stats
python -m app.cli stats
```

---

## Knowledge Base

Pre-loaded documents in `data/raw/`:

| Document | Contents |
|----------|---------|
| `insurance_policy_overview.md` | Motor & property coverage, limits, deductibles |
| `claims_process.md` | Step-by-step claim filing guide |
| `endorsements_and_riders.md` | IMT-28 (Zero Dep), IMT-29 (Engine), IAP-01 (Earthquake) and more |
| `claims_faq.md` | 20+ Q&As covering motor, property, health, and PA claims |

Drop `.pdf`, `.txt`, or `.md` files into `data/raw/` and re-ingest, or upload via the Streamlit UI.

---

## Chunk Size Comparison

```powershell
python -m scripts.evaluate_chunking
```

Runs probe questions across chunk sizes **300 / 800 / 1500** and prints the best-matching chunk and similarity score for each — no LLM call needed.
