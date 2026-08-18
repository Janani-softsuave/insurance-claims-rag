# Pipeline — Insurance Claims RAG System (Week 3 + 4)

---

## Pipeline 1 — Ingestion

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION PIPELINE                                  │
│               Streamlit: Upload & Ingest tab  |  CLI: ingest                │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────┐
  │   User / Streamlit   │  Upload file  OR  Run Ingestion on data/raw/
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────────────────────────────────────┐
  │  STEP 1 — LOAD                 app/ingestion/loaders │
  │                                                      │
  │  Reads every file from data/raw/                     │
  │  .md / .txt  →  plain text read                      │
  │  .pdf        →  pypdf extracts text per page         │
  │                                                      │
  │  Output: list[Document]                              │
  │    { text, source, source_path, metadata }           │
  └──────────────────────┬───────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │  STEP 2 — CHUNK                app/ingestion/chunker │
  │                                                      │
  │  Recursive character splitter                        │
  │  Boundaries tried: \n\n → \n → ". " → " " → hard    │
  │                                                      │
  │  Config (tunable via sidebar):                       │
  │    chunk_size    = 800 chars (default)               │
  │    chunk_overlap = 120 chars (default)               │
  │                                                      │
  │  Output: list[Chunk]                                 │
  │    { id, text, source, chunk_index, metadata }       │
  └──────────────────────┬───────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │  STEP 3 — EMBED              app/embeddings/embedder │
  │                                                      │
  │  Model: BAAI/bge-small-en-v1.5  (local, offline)    │
  │  Type:  Bi-encoder                                   │
  │                                                      │
  │  chunk text  →  384-dim float vector (L2-normalised) │
  │                                                      │
  │  Output: list[vector]                                │
  └──────────────────────┬───────────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────────┐
  │  STEP 4 — STORE            app/vectorstore/chroma    │
  │                                                      │
  │  Database: ChromaDB  (local, persistent on disk)     │
  │  Index:    HNSW  (Hierarchical Navigable Small World)│
  │  Space:    Cosine similarity                         │
  │  Location: storage/chroma/                           │
  │                                                      │
  │  Also stores all chunk texts for BM25 index (W4)     │
  └──────────────────────────────────────────────────────┘
```

---

## Pipeline 2 — Query (Week 3 baseline)

```
User question
    │
    ▼
[VALIDATE]          app/guardrails/guards.py
    Not empty / ≤1000 chars / no prompt injection
    FAIL → refuse (no LLM called)
    │
    ▼
[EMBED QUERY]       app/embeddings/embedder.py
    BGE query instruction prefix + question → 384-dim vector
    │
    ▼
[RETRIEVE top-K]    app/retrieval/retriever.py
    ChromaDB HNSW cosine search  →  8 candidates
    │
    ▼
[RERANK]            app/retrieval/reranker.py
    BAAI/bge-reranker-base cross-encoder
    sigmoid(logit) → 0..1 score  →  top 4
    │
    ▼
[GROUND CHECK]      app/guardrails/guards.py
    best score < 0.52  →  "I don't know"  (no LLM)
    │
    ▼
[GENERATE]          app/generation/generator.py
    Gemini (gemini-flash-latest) + instructor → GroundedAnswer
    503/error  →  retrieval-only fallback
    │
    ▼
AskResponse { answer, can_answer, citations, sources, retrieved_chunks }
```

---

## Pipeline 2 — Query (Week 4 extended — all options)

```
User question
    │
    ▼
[VALIDATE]          app/guardrails/guards.py
    │
    ▼
[QUERY TRANSFORMATION]          (choose one — HyDE takes priority)
    │
    ├── HyDE ON    app/retrieval/hyde.py
    │     Gemini generates a hypothetical answer document
    │     Embed the hypothetical doc (not the question)
    │     → better vector for vague / indirect questions
    │     Falls back to query embedding on LLM failure
    │
    ├── Query Rewriting ON    app/retrieval/query_rewriter.py
    │     Gemini rewrites messy question → precise keyword-rich query
    │     Falls back to original on failure
    │
    └── Neither → embed original question
    │
    ▼
[RETRIEVE top-K]          (choose one)
    │
    ├── Dense only    app/retrieval/retriever.py
    │     BGE bi-encoder + ChromaDB HNSW  →  top-K by cosine
    │
    └── Hybrid ON    app/retrieval/hybrid_retriever.py
          Dense retrieval  (top-K by cosine)
          +
          BM25 keyword search  app/retrieval/bm25_retriever.py
            tokenized index over all chunks
            catches exact codes, acronyms, names
          │
          RRF fusion:  score = Σ 1/(60 + rank)  per list
          Merged, re-sorted  →  top-K
    │
    ▼
[CROSS-ENCODER RERANK]    app/retrieval/reranker.py
    BAAI/bge-reranker-base reads (question, chunk) pairs together
    sigmoid(logit) → 0..1  →  top-N sorted by score
    │
    ▼
[MMR DIVERSITY RERANK]    app/retrieval/mmr.py     (optional)
    Iteratively selects chunks that are relevant but not redundant
    MMR(chunk) = λ · sim(chunk, query) - (1-λ) · max_sim(chunk, selected)
    λ slider: 1.0 = pure relevance, 0.0 = pure diversity
    │
    ▼
[GROUND CHECK]      app/guardrails/guards.py
    best rerank score < 0.52  →  "I don't know"
    │
    ▼
[GENERATE]          app/generation/generator.py
    Gemini + instructor → GroundedAnswer { can_answer, answer, citations }
    503/error → retrieval-only fallback (raw chunks shown)
    │
    ▼
AskResponse {
    question, rewritten_question,
    answer, can_answer, citations, sources,
    retrieval_only, retrieved_chunks
}
```

---

## Failure Diagnosis (Week 4)

```
When an answer is wrong, label it using the Inspection View tab:

  🔴 Retrieval failure
       Wrong document fetched — the retrieved chunks don't contain the answer.
       Fix: try hybrid search, query rewriting, or HyDE.

  🟡 Generation failure
       Right document fetched — but the answer is wrong or incomplete.
       Fix: adjust the prompt, increase rerank_top_n, or try MMR for diversity.

  ✅ Correct
       Both retrieval and generation worked as expected.
```

---

## Evaluation (Week 4)

```
scripts/evaluate_retrieval.py   (CLI)
Evaluation tab in Streamlit

Before (Dense only):
  retrieve(question, top_k=3) for each test query
  hit-rate@3 = fraction of queries where expected_source in top-3
  MRR = mean 1/rank of first correct source

After (Hybrid BM25+Dense):
  same queries, same k, hybrid retriever
  before/after delta printed as numbers
```

---

## Technology at each step

| Step | Technology |
|------|-----------|
| Load | `pypdf`, plain file I/O |
| Chunk | Custom recursive splitter |
| Embed (docs + query) | `BAAI/bge-small-en-v1.5` bi-encoder |
| Store + search | `ChromaDB` — HNSW, cosine space |
| BM25 keyword search | `rank-bm25` — BM25Okapi |
| Hybrid fusion | RRF (Reciprocal Rank Fusion) |
| Rerank | `BAAI/bge-reranker-base` cross-encoder |
| MMR | Custom iterative selection |
| HyDE | Gemini generation → BGE embedding |
| Query rewriting | Gemini generation |
| Generation | Gemini `gemini-flash-latest` + `instructor` |
| Structured output | `Pydantic` `GroundedAnswer` schema |
