# Insurance Claims RAG System — Week 3 AI POC

A **Retrieval-Augmented Generation** app built for the **Insurance Claims** knowledge base (Week 3 — Topic D). Ask questions in plain English and get answers built **only** from your insurance policy documents — with a citation to the source. If the answer isn't in the documents, it says **"I don't know"** instead of inventing one.

---

## Knowledge Base

The following insurance documents are pre-loaded in `data/raw/`:

| Document | Contents |
|----------|---------|
| `insurance_policy_overview.md` | Motor & property coverage, limits, deductibles, policy periods |
| `claims_process.md` | Step-by-step claim filing guide, cashless vs reimbursement, rejection reasons |
| `endorsements_and_riders.md` | IMT-28 (Zero Dep), IMT-29 (Engine), IMT-34 (RTI), IAP-01 (Earthquake) and more |
| `claims_faq.md` | 20+ Q&As covering motor, property, health, and personal accident claims |

You can also upload your own PDF/TXT/MD documents via the UI.

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
| Interfaces | `app/api`, `app/cli.py`, `streamlit_app.py` | FastAPI + CLI + Streamlit UI |

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
| API | FastAPI |
| CLI | Typer + Rich |

---

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your Gemini API key:
```
GEMINI_API_KEY=your-key-here
```
Get a free key at https://aistudio.google.com/apikey

> First run downloads BGE models (~150 MB) from Hugging Face automatically.

---

## Usage Flow

### Step 1 — Ingest documents
Run ingestion once to chunk, embed, and index all documents in `data/raw/`:
```powershell
python -m app.cli ingest --reset
```

### Step 2 — Ask questions

**Streamlit UI** (recommended)
```powershell
streamlit run streamlit_app.py
```
Open **http://localhost:8501** — upload documents, configure chunk size and retrieval settings, and ask questions from the browser.

**FastAPI**
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000/docs** for the interactive API.

**CLI**
```powershell
python -m app.cli ask "How soon must I report a theft claim?"
python -m app.cli ask "What is a total loss in motor insurance?"
python -m app.cli ask "Does Zero Dep cover tyre damage?"
python -m app.cli stats
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server status check |
| `POST` | `/upload` | Upload a document (PDF, TXT, MD) — saves to `data/raw/` |
| `POST` | `/ingest?reset=true` | Chunk and index all documents in `data/raw/` |
| `POST` | `/ask` | Ask a question — returns grounded answer with citations |

**Example curl:**
```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What documents do I need to file a motor claim?"}'
```

**Example response:**
```json
{
  "question": "What documents do I need to file a motor claim?",
  "answer": "To file a motor claim you need: a signed claim form, RC copy, driving licence, policy certificate, FIR (if applicable), and a repair estimate.",
  "can_answer": true,
  "citations": [
    { "source": "claims_process.md", "snippet": "Duly signed claim form, Copy of Registration Certificate..." }
  ],
  "sources": ["claims_process.md"]
}
```

---

## Sample Questions to Try

| Question | Expected behaviour |
|----------|--------------------|
| How soon must I report a theft claim? | Answers with 24-hour deadline, cites `claims_faq.md` |
| What is a total loss in motor insurance? | Answers 75% IDV rule, cross-cites FAQ + endorsements |
| Does Zero Dep cover tyre damage? | Answers no, cites exclusion from `endorsements_and_riders.md` |
| Is earthquake damage covered by default? | Answers no, endorsement IAP-01 required |
| What documents are needed for a motor claim? | Lists all required documents with deadline |
| What is the best stock to buy? | Returns "I don't know" — not in documents |

---

## Chunk Size Comparison

```powershell
python -m scripts.evaluate_chunking
```

Runs probe questions across chunk sizes **300 / 800 / 1500** and prints the best-matching chunk and similarity score — no LLM call needed.

---

## Adding Documents

Drop `.pdf`, `.txt`, or `.md` files into `data/raw/`, then re-ingest:
```powershell
python -m app.cli ingest --reset
```
Or upload directly via the Streamlit UI (Step 1 → Upload tab) or `POST /upload`.
