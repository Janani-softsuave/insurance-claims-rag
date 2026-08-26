# Insurance Claims RAG System — Week 3 + 4 + 5

A **Retrieval-Augmented Generation** app for the Insurance Claims knowledge base. Ask questions in plain English and get answers built **only** from your documents — with a citation to the source. If the answer isn't in the documents, it says **"I don't know"** instead of inventing one.

Week 4 adds **hybrid search, MMR, HyDE, query rewriting**, failure diagnosis, and before/after evaluation metrics.

Week 5 adds a **few-shot generation prompt**, full **trace logging with PII redaction** on every query, seeded random sampling + replay of traces, and a hand-graded **error taxonomy** (see `analysis/week5/`).

---

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: GEMINI_API_KEY=your-key-here
# Get a free key at https://aistudio.google.com/apikey
```

> First run downloads BGE models (~150 MB) from Hugging Face automatically.

---

## Run

```powershell
streamlit run streamlit_app.py
```
Open **http://localhost:8501**

Or via CLI:
```powershell
python -m app.cli ingest --reset
python -m app.cli ask "How soon must I report a theft claim?"
python -m app.cli stats
```

Every `ask` (CLI, Streamlit, or script) writes a redacted trace to `storage/traces/traces.jsonl`.
Sample and replay them with:
```powershell
python -m scripts.collect_week5_traces
python -m app.cli trace sample --seed 42
python -m app.cli trace replay <trace_id>
```

---

## Architecture

```
INGESTION    load ─► chunk ─► embed (bi-encoder) ─► store (ChromaDB / HNSW)

QUERY        validate ─► [transform] ─► retrieve ─► rerank ─► [MMR] ─► ground ─► generate
```

See **ARCHITECTURE.md** for the full file map and **PIPELINE.md** for step-by-step flow diagrams.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Embeddings | `BAAI/bge-small-en-v1.5` (local, bi-encoder) |
| Reranker | `BAAI/bge-reranker-base` (local, cross-encoder) |
| BM25 | `rank-bm25` (keyword search) |
| Vector DB | ChromaDB — HNSW, cosine |
| LLM | Google Gemini `gemini-flash-latest` |
| Structured output | `instructor` + Pydantic |
| UI | Streamlit (4 tabs) |
| CLI | Typer + Rich |
| Tracing | JSONL trace log with regex PII redaction (`app/core/tracing.py`) |

---

## Streamlit Tabs

| Tab | What it does |
|-----|-------------|
| 📁 Upload & Ingest | Upload documents, configure chunk size/overlap, run ingestion |
| 💬 Ask Questions | Ask with configurable retrieval — hybrid, HyDE, MMR, query rewriting |
| 🔍 Inspection View | See retrieved chunks + answer side by side; label failures |
| 📊 Evaluation | Before/after hit-rate@k and MRR for dense vs hybrid retrieval |

---

## Week 4 Retrieval Options (sidebar toggles)

| Toggle | What it does |
|--------|-------------|
| Hybrid Search | BM25 keyword + dense semantic, fused with RRF |
| HyDE | Embeds a Gemini-generated hypothetical answer instead of the question |
| Query Rewriting | Rewrites the question into a precise search query |
| MMR (λ slider) | Diversifies retrieved chunks to reduce redundancy |

---

## Knowledge Base

Pre-loaded documents in `data/raw/`:

| Document | Contents |
|----------|---------|
| `insurance_policy_overview.md` | Motor & property coverage, limits, deductibles |
| `claims_process.md` | Step-by-step claim filing guide |
| `endorsements_and_riders.md` | IMT-28 (Zero Dep), IMT-29 (Engine), IAP-01 (Earthquake) and more |
| `claims_faq.md` | 20+ Q&As covering motor, property, health, and PA claims |

Drop any `.pdf`, `.txt`, or `.md` into `data/raw/` and re-ingest via the UI or CLI.

---

## Evaluation Scripts

```powershell
# Compare chunk sizes 300 / 800 / 1500 — no LLM needed
python -m scripts.evaluate_chunking

# Before/after: dense vs hybrid retrieval (hit-rate@3, MRR)
python -m scripts.evaluate_retrieval

# Run 30 varied questions through the live app to populate traces.jsonl
python -m scripts.collect_week5_traces
```

---

## Week 5 — Error Analysis

`analysis/week5/` holds the graded deliverable: a random, seeded sample of 20 real
traces, read and open-coded by hand, clustered into a named failure taxonomy.

| File | Contents |
|------|---------|
| `taxonomy.md` | One-page ranked list of failure modes — count, frequency %, severity, example `trace_id` |
| `notes.md` | The 20 verbatim open-coding sentences, the seeded sample, replay evidence, the dated prediction, and the benchmark note |
| `sample_trace_ids.json` | The exact seed + trace_ids produced by `app.cli trace sample` |

See **PIPELINE.md** for the trace-logging and error-analysis flow.
