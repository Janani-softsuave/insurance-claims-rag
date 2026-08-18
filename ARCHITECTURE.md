# Architecture — Insurance Claims RAG System (Week 3 + 4)

---

## Layer overview

```
  Interfaces        streamlit_app.py  |  app/cli.py
                           │
  Service           app/services/rag_service.py
                           │
  Capabilities      retrieval/  |  guardrails/  |  generation/  |  evaluation/
                           │
  Foundations       embeddings/  |  vectorstore/  |  ingestion/
                           │
  Core              app/core/config.py  |  app/core/logging.py
  Models            app/models/schemas.py
```

Dependencies flow **inward only** — interfaces call the service, the service calls capabilities, capabilities call foundations. No layer reaches back up.

---

## File map

### `app/core/`
| File | Responsibility |
|------|---------------|
| `config.py` | All settings loaded from `.env` via `pydantic-settings`. Single `Settings` object, `lru_cache`d. Covers chunking, retrieval, Week 4 toggles (hybrid, MMR, HyDE, query rewriting). |
| `logging.py` | `get_logger(name)` — consistent log format across every module. |

### `app/models/schemas.py`
Pydantic types that flow through every layer:
- `Document` — raw file before chunking
- `Chunk` — one searchable text piece with source metadata
- `RetrievedChunk` — chunk + relevance score
- `RetrievedChunkInfo` — serialisable chunk snapshot (for inspection view)
- `GroundedAnswer` — what the LLM is forced to return via `instructor`
- `Citation` — source + verbatim snippet
- `AskResponse` — final response including `retrieved_chunks`, `rewritten_question`, `retrieval_only`
- `IngestResponse` — ingestion summary

### `app/ingestion/`
| File | Responsibility |
|------|---------------|
| `loaders.py` | `load_directory()` → reads `.md`, `.txt`, `.pdf` into `Document` objects. |
| `chunker.py` | Recursive character splitter. Tries `\n\n → \n → ". " → " " → hard cut`. Applies overlap sliding window. Produces deterministic chunk IDs. |
| `pipeline.py` | Orchestrates load → chunk → embed → store. Single `ingest()` entry point for CLI and Streamlit. |

### `app/embeddings/`
| File | Responsibility |
|------|---------------|
| `embedder.py` | `BAAI/bge-small-en-v1.5` bi-encoder. `embed_documents()` (no prefix) for chunks; `embed_query()` (BGE instruction prefix) for questions. `lru_cache`d singleton. |

### `app/vectorstore/`
| File | Responsibility |
|------|---------------|
| `chroma_store.py` | Persistent ChromaDB collection (HNSW, cosine). `add()` upserts chunks + vectors. `query()` returns top-K with similarity score (`1 - distance`). `reset()` drops and recreates. |

### `app/retrieval/`
| File | Responsibility |
|------|---------------|
| `retriever.py` | Dense retrieval — embed query, HNSW nearest-neighbour search. Fast approximate recall. |
| `bm25_retriever.py` | BM25 keyword search (Week 4). Builds `BM25Okapi` index over all stored chunk texts. Catches exact codes, acronyms, names that semantic search misses. |
| `hybrid_retriever.py` | RRF fusion (Week 4). Runs dense + BM25, merges by `1/(60 + rank)`, re-sorts. Loaded in memory from ChromaDB on init. |
| `reranker.py` | Cross-encoder reranker. `BAAI/bge-reranker-base` reads `(question, chunk)` pairs together. Sigmoid of raw logit → 0..1. Keeps top-N. |
| `mmr.py` | Maximal Marginal Relevance (Week 4). Iteratively selects chunks that balance relevance to query vs dissimilarity to already-selected chunks. `λ` slider (1.0 = relevance, 0.0 = diversity). |
| `hyde.py` | Hypothetical Document Embeddings (Week 4). Generates a hypothetical answer via Gemini, embeds the answer text (not the question). Better for vague/indirect questions. Falls back to query embedding on failure. |
| `query_rewriter.py` | Query rewriting (Week 4). Gemini rewrites the user's raw question into a precise, keyword-rich search query. Falls back to original on failure. |

### `app/guardrails/`
| File | Responsibility |
|------|---------------|
| `guards.py` | `validate_question()` — length check + prompt-injection pattern screen. `is_grounded()` — refuses to generate if best rerank score < 0.52, preventing hallucination on out-of-corpus questions. |

### `app/generation/`
| File | Responsibility |
|------|---------------|
| `prompts.py` | System prompt (rules: answer only from context, cite sources, say "I don't know", treat context as untrusted). `build_context()` renders numbered, source-labelled chunks. |
| `generator.py` | Gemini via `instructor`. Forces `GroundedAnswer` schema. Auto-retries on validation failure. |

### `app/services/rag_service.py`
Orchestrates the full query pipeline in order:
1. `validate_question`
2. Query transformation — HyDE or query rewriting (HyDE takes priority)
3. Retrieval — dense or hybrid
4. Cross-encoder reranking
5. MMR diversity reranking (optional)
6. Grounding gate
7. Grounded generation (with retrieval-only fallback on LLM error)

Both interfaces call `RagService.ask()` — same pipeline, same results.

### `app/evaluation/`
| File | Responsibility |
|------|---------------|
| `metrics.py` | `hit_rate_at_k()`, `reciprocal_rank()`, `MRR`, `evaluate()`. Takes a list of `{question, expected_source}` dicts and a retrieval function. |

### Interfaces
| File | Responsibility |
|------|---------------|
| `streamlit_app.py` | 4-tab UI: Upload & Ingest, Ask Questions, Inspection View (failure labelling), Evaluation (before/after metrics). Sidebar controls all Week 4 toggles. |
| `app/cli.py` | Typer CLI: `ingest`, `ask`, `stats`. |

### Scripts
| File | Responsibility |
|------|---------------|
| `scripts/evaluate_chunking.py` | Compares chunk sizes 300/800/1500 — retrieval quality without the LLM. |
| `scripts/evaluate_retrieval.py` | Before/after evaluation table — dense vs hybrid, hit-rate@3 and MRR. |

---

## Week 4 additions at a glance

| Addition | Purpose | File |
|----------|---------|------|
| BM25 retriever | Catches exact keywords/acronyms semantic search misses | `retrieval/bm25_retriever.py` |
| Hybrid search (RRF) | Combines BM25 + dense, improves hit-rate@k | `retrieval/hybrid_retriever.py` |
| MMR | Reduces redundant chunks → LLM sees diverse evidence | `retrieval/mmr.py` |
| HyDE | Hypothetical doc embedding for indirect questions | `retrieval/hyde.py` |
| Query rewriting | Cleans up messy questions before retrieval | `retrieval/query_rewriter.py` |
| Inspection view | Diagnose retrieval vs generation failures | `streamlit_app.py` Tab 3 |
| Evaluation metrics | Before/after numbers (hit-rate@k, MRR) | `evaluation/metrics.py` |
| Evaluation script | CLI before/after table | `scripts/evaluate_retrieval.py` |
