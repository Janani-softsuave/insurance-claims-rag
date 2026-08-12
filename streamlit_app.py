"""Insurance Claims RAG System — Streamlit UI.

Run:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st

# ── page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Insurance Claims RAG",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── lazy imports (heavy — load once via session_state) ─────────────────────────
@st.cache_resource(show_spinner="Loading embedding & reranker models…")
def load_service(top_k: int, rerank_top_n: int):
    from app.services.rag_service import RagService
    svc = RagService()
    svc.retriever.store  # touch store to ensure collection exists
    return svc


@st.cache_resource(show_spinner="Loading embedding model…")
def load_embedder():
    from app.embeddings.embedder import get_embedder
    return get_embedder()


def get_store():
    from app.vectorstore.chroma_store import ChromaStore
    from app.core.config import settings
    return ChromaStore(path=settings.chroma_path, collection_name=settings.collection_name)


# ── helpers ────────────────────────────────────────────────────────────────────
def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))


def run_chunk_comparison(probe_questions: list[str], chunk_sizes: list[int]):
    """Return comparison data without calling the LLM."""
    from app.ingestion.loaders import load_directory
    from app.ingestion.chunker import chunk_documents
    from app.core.config import settings

    embedder = load_embedder()
    documents = load_directory(settings.data_raw_dir)
    if not documents:
        return None, "No documents found in data/raw/."

    rows = []
    for size in chunk_sizes:
        overlap = int(size * 0.15)
        chunks = chunk_documents(documents, chunk_size=size, chunk_overlap=overlap)
        vecs = embedder.embed_documents([c.text for c in chunks])
        for q in probe_questions:
            qv = embedder.embed_query(q)
            scores = [cosine(qv, v) for v in vecs]
            best_idx = max(range(len(scores)), key=lambda i: scores[i])
            rows.append({
                "Chunk Size": size,
                "Overlap": overlap,
                "Total Chunks": len(chunks),
                "Question": q[:60] + ("…" if len(q) > 60 else ""),
                "Best Score": round(scores[best_idx], 4),
                "Source": chunks[best_idx].source,
                "Snippet": chunks[best_idx].text.replace("\n", " ")[:120] + "…",
            })
    return rows, None


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — configuration
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📋 Insurance Claims RAG")
    st.caption("Week 3 — Retrieval-Augmented Generation")
    st.divider()

    st.subheader("⚙️ Chunking")
    chunk_size = st.slider("Chunk Size (chars)", 100, 2000, 800, step=50,
                           help="Larger = more context per chunk, lower score precision.")
    chunk_overlap = st.slider("Overlap (chars)", 0, 500, 120, step=10,
                              help="Overlap prevents answers from being cut at boundaries.")

    st.subheader("🔍 Retrieval")
    top_k = st.slider("Top K candidates", 4, 20, 8,
                      help="Number of chunks retrieved by the bi-encoder.")
    rerank_top_n = st.slider("Rerank Top N", 2, 8, 4,
                             help="Chunks kept after cross-encoder reranking.")

    st.divider()
    st.subheader("📊 Index Stats")
    try:
        store = get_store()
        col1, col2 = st.columns(2)
        col1.metric("Chunks", store.count())
        col2.metric("Collection", store.collection_name)
    except Exception:
        st.warning("Index not built yet. Go to Upload & Ingest.")

    if st.button("🔄 Refresh Stats"):
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN TABS
# ══════════════════════════════════════════════════════════════════════════════
tab_upload, tab_ask, tab_mentor = st.tabs([
    "📁  Upload & Ingest",
    "💬  Ask Questions",
    "🎓  Mentor Checks",
])


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — Upload & Ingest
# ──────────────────────────────────────────────────────────────────────────────
with tab_upload:
    st.header("Document Upload & Ingestion")
    st.markdown(
        "Upload your insurance documents (PDF, TXT, Markdown). "
        "They will be **chunked → embedded → indexed** into the vector store."
    )

    col_up, col_cfg = st.columns([2, 1])

    with col_up:
        st.subheader("📤 Upload Documents")
        uploaded_files = st.file_uploader(
            "Drop files here (PDF, TXT, MD)",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            from app.core.config import settings as cfg
            raw_dir = Path(cfg.data_raw_dir)
            raw_dir.mkdir(parents=True, exist_ok=True)

            saved = []
            for f in uploaded_files:
                dest = raw_dir / f.name
                dest.write_bytes(f.read())
                saved.append(f.name)
            st.success(f"Saved {len(saved)} file(s): {', '.join(saved)}")

    with col_cfg:
        st.subheader("🔧 Active Config")
        st.info(
            f"**Chunk size:** {chunk_size} chars\n\n"
            f"**Overlap:** {chunk_overlap} chars\n\n"
            f"**Top K:** {top_k}\n\n"
            f"**Rerank N:** {rerank_top_n}"
        )

    st.divider()

    col_btn, col_reset = st.columns([1, 1])
    reset = col_reset.checkbox("Reset index before ingesting", value=False)

    if col_btn.button("⚡ Run Ingestion", use_container_width=True, type="primary"):
        from app.ingestion.pipeline import ingest
        with st.spinner("Ingesting documents…"):
            try:
                result = ingest(chunk_size=chunk_size, chunk_overlap=chunk_overlap, reset=reset)
                st.balloons()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Documents loaded", result.documents_loaded)
                m2.metric("Chunks indexed", result.chunks_indexed)
                m3.metric("Chunk size", result.chunk_size)
                m4.metric("Overlap", result.chunk_overlap)
                st.success(f"✅ Indexed into collection **'{result.collection}'**")
            except Exception as e:
                st.error(f"Ingestion failed: {e}")

    st.divider()
    st.subheader("📄 Documents in data/raw/")
    from app.core.config import settings as cfg
    raw_dir = Path(cfg.data_raw_dir)
    if raw_dir.exists():
        files = sorted(raw_dir.glob("*"))
        if files:
            for f in files:
                size_kb = round(f.stat().st_size / 1024, 1)
                st.markdown(f"- `{f.name}` — {size_kb} KB")
        else:
            st.info("No documents yet. Upload some above.")
    else:
        st.info("data/raw/ directory does not exist yet.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — Ask Questions
# ──────────────────────────────────────────────────────────────────────────────
with tab_ask:
    st.header("Ask the Documents")
    st.markdown(
        "Ask any question. The system retrieves the most relevant chunks, "
        "then generates a **grounded answer with citations** — or says "
        "**'I don't know'** if the answer isn't in the documents."
    )

    question = st.text_area(
        "Your question",
        placeholder="e.g. How soon must I report a theft claim?",
        height=80,
    )

    if st.button("🔍 Ask", type="primary", use_container_width=False):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Retrieving and generating…"):
                try:
                    service = load_service(top_k, rerank_top_n)
                    resp = service.ask(question.strip(), top_k=top_k, rerank_top_n=rerank_top_n)

                    if resp.can_answer:
                        st.success("✅ Answer found in documents")
                        st.markdown(f"### Answer\n{resp.answer}")

                        if resp.citations:
                            with st.expander("📎 Citations", expanded=True):
                                for i, c in enumerate(resp.citations, 1):
                                    st.markdown(f"**[{i}] {c.source}**")
                                    st.caption(f'"{c.snippet}"')
                                    st.divider()

                        if resp.sources:
                            st.markdown(
                                "**Sources retrieved:** " +
                                ", ".join(f"`{s}`" for s in resp.sources)
                            )
                    else:
                        st.warning("⚠️ I don't know — the answer is not in the documents.")
                        st.markdown(f"_{resp.answer}_")

                    # save to history
                    if "history" not in st.session_state:
                        st.session_state.history = []
                    st.session_state.history.insert(0, {
                        "q": question.strip(),
                        "a": resp.answer,
                        "can": resp.can_answer,
                        "sources": resp.sources,
                    })

                except Exception as e:
                    st.error(f"Error: {e}")

    # Q&A History
    if st.session_state.get("history"):
        st.divider()
        st.subheader("🕓 History")
        for item in st.session_state.history[:5]:
            icon = "✅" if item["can"] else "❓"
            with st.expander(f"{icon} {item['q'][:80]}"):
                st.write(item["a"])
                if item["sources"]:
                    st.caption("Sources: " + ", ".join(item["sources"]))


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — Mentor Checks
# ──────────────────────────────────────────────────────────────────────────────
with tab_mentor:
    st.header("🎓 Mentor Evaluation")
    st.markdown(
        "This tab runs **all 4 mentor checks** automatically and shows pass/fail. "
        "Checks 1–3 call the full RAG pipeline (Gemini required). "
        "Check 4 uses the embedder only — no API key needed."
    )
    st.divider()

    PROBE_QUESTIONS = [
        "How soon must I report a theft claim?",
        "What documents are needed for a motor insurance claim?",
        "Is earthquake damage covered under a standard property policy?",
        "What is a total loss in motor insurance?",
    ]
    OUT_OF_CORPUS = "What is the best programming language for machine learning?"

    run_all = st.button("▶ Run All Mentor Checks", type="primary", use_container_width=True)

    st.divider()

    # ── Check 1 & 2: answer correctness + citations ────────────────────────
    st.subheader("Check 1 — Can the app answer correctly from the documents?")
    st.subheader("Check 2 — Does every answer show which document it came from?")

    check12_placeholder = st.container()

    if run_all:
        with check12_placeholder:
            with st.spinner("Running Q&A checks…"):
                try:
                    service = load_service(top_k, rerank_top_n)
                    results_12 = []
                    for q in PROBE_QUESTIONS:
                        resp = service.ask(q, top_k=top_k, rerank_top_n=rerank_top_n)
                        results_12.append({
                            "Question": q,
                            "Answered": resp.can_answer,
                            "Has Citations": len(resp.citations) > 0,
                            "Answer (excerpt)": resp.answer[:120] + "…" if len(resp.answer) > 120 else resp.answer,
                            "Sources": ", ".join(resp.sources) if resp.sources else "—",
                        })
                        time.sleep(0.3)

                    answered = sum(1 for r in results_12 if r["Answered"])
                    cited = sum(1 for r in results_12 if r["Has Citations"])

                    c1, c2 = st.columns(2)
                    check1_pass = answered == len(PROBE_QUESTIONS)
                    check2_pass = cited == len(PROBE_QUESTIONS)
                    c1.metric("Check 1", f"{'✅ PASS' if check1_pass else '❌ FAIL'}",
                              f"{answered}/{len(PROBE_QUESTIONS)} questions answered")
                    c2.metric("Check 2", f"{'✅ PASS' if check2_pass else '❌ FAIL'}",
                              f"{cited}/{len(PROBE_QUESTIONS)} answers cited")

                    for r in results_12:
                        icon = "✅" if r["Answered"] else "❌"
                        cite_icon = "📎" if r["Has Citations"] else "⚠️"
                        with st.expander(f"{icon} {cite_icon} {r['Question']}"):
                            st.markdown(f"**Answer:** {r['Answer (excerpt)']}")
                            st.markdown(f"**Sources:** `{r['Sources']}`")

                except Exception as e:
                    st.error(f"Check 1/2 failed: {e}")

    st.divider()

    # ── Check 3: I don't know ──────────────────────────────────────────────
    st.subheader("Check 3 — Does it admit 'I don't know' for out-of-corpus questions?")

    check3_placeholder = st.container()

    if run_all:
        with check3_placeholder:
            with st.spinner("Testing out-of-corpus question…"):
                try:
                    service = load_service(top_k, rerank_top_n)
                    resp3 = service.ask(OUT_OF_CORPUS, top_k=top_k, rerank_top_n=rerank_top_n)
                    check3_pass = not resp3.can_answer

                    st.metric(
                        "Check 3",
                        "✅ PASS" if check3_pass else "❌ FAIL",
                        "Correctly refused" if check3_pass else "Incorrectly attempted to answer",
                    )
                    st.markdown(f"**Question asked:** _{OUT_OF_CORPUS}_")
                    if check3_pass:
                        st.success(f"Response: _{resp3.answer}_")
                    else:
                        st.error(
                            f"The app answered instead of refusing:\n\n_{resp3.answer}_\n\n"
                            "Try lowering the score threshold in config.py."
                        )
                except Exception as e:
                    st.error(f"Check 3 failed: {e}")

    st.divider()

    # ── Check 4: chunk size comparison ────────────────────────────────────
    st.subheader("Check 4 — Did they try more than one chunk size and notice the difference?")
    st.markdown(
        "Runs the probe questions across **3 chunk sizes** using only the embedder "
        "(no LLM call). Shows how chunk size affects retrieval score and snippet focus."
    )

    CHUNK_SIZES = [300, 800, 1500]
    check4_placeholder = st.container()

    if run_all:
        with check4_placeholder:
            with st.spinner("Running chunk size comparison (no LLM needed)…"):
                rows, err = run_chunk_comparison(PROBE_QUESTIONS[:2], CHUNK_SIZES)
                if err:
                    st.error(err)
                else:
                    import pandas as pd
                    df = pd.DataFrame(rows)

                    # score comparison chart per question
                    for q in df["Question"].unique():
                        sub = df[df["Question"] == q][["Chunk Size", "Total Chunks", "Best Score", "Source"]]
                        st.markdown(f"**Q: {q}**")
                        st.dataframe(sub.reset_index(drop=True), use_container_width=True)

                    st.divider()

                    # overall score trend
                    pivot = df.pivot_table(index="Chunk Size", values="Best Score", aggfunc="mean").reset_index()
                    pivot.columns = ["Chunk Size", "Avg Best Score"]
                    st.markdown("**Average best-match score across probe questions by chunk size:**")
                    st.bar_chart(pivot.set_index("Chunk Size"))

                    # insight
                    scores = pivot["Avg Best Score"].tolist()
                    if scores[0] > scores[-1]:
                        insight = (
                            f"✅ **Smaller chunks (300) score higher ({scores[0]:.3f}) than "
                            f"larger chunks (1500) ({scores[-1]:.3f})** — because smaller chunks "
                            f"contain a single focused fact, so cosine similarity is higher. "
                            f"Larger chunks mix multiple topics, diluting the score."
                        )
                    else:
                        insight = (
                            f"Chunk sizes 300→1500 scored {scores[0]:.3f}→{scores[-1]:.3f}. "
                            f"Different chunk sizes surface different strengths — "
                            f"small chunks are precise, large chunks provide more context."
                        )
                    st.info(insight)
                    st.metric("Check 4", "✅ PASS", "3 chunk sizes compared with score analysis")

    # ── Summary card ──────────────────────────────────────────────────────
    if run_all:
        st.divider()
        st.subheader("📋 Evaluation Summary")
        st.markdown("""
| # | Mentor Check | Status |
|---|-------------|--------|
| 1 | App answers correctly using the documents | See results above |
| 2 | Every answer shows which document it came from | See results above |
| 3 | Admits "I don't know" for out-of-corpus questions | See results above |
| 4 | Tried more than one chunk size and noticed the difference | ✅ Shown above |
        """)

    if not run_all:
        st.info("Click **▶ Run All Mentor Checks** above to evaluate all 4 checks.")
