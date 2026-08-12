from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="Insurance Claims RAG",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Loading models…")
def load_service(top_k: int, rerank_top_n: int):
    from app.services.rag_service import RagService
    return RagService()


def get_store():
    from app.vectorstore.chroma_store import ChromaStore
    from app.core.config import settings
    return ChromaStore(path=settings.chroma_path, collection_name=settings.collection_name)


with st.sidebar:
    st.title("📋 Insurance Claims RAG")
    st.caption("Week 3 — Retrieval-Augmented Generation")
    st.divider()

    st.subheader("⚙️ Chunking")
    chunk_size = st.slider("Chunk Size (chars)", 100, 2000, 800, step=50,
                           help="Larger = more context per chunk, lower retrieval precision.")
    chunk_overlap = st.slider("Overlap (chars)", 0, 500, 120, step=10,
                              help="Overlap prevents answers from being cut at chunk boundaries.")

    st.subheader("🔍 Retrieval")
    top_k = st.slider("Top K candidates", 4, 20, 8,
                      help="Number of chunks retrieved by the bi-encoder.")
    rerank_top_n = st.slider("Rerank Top N", 2, 8, 4,
                             help="Chunks kept after cross-encoder reranking.")

    st.divider()
    st.subheader("📊 Index Stats")
    try:
        store = get_store()
        c1, c2 = st.columns(2)
        c1.metric("Chunks", store.count())
        c2.metric("Collection", store.collection_name)
    except Exception:
        st.warning("Index not built yet. Go to Upload & Ingest.")

    if st.button("🔄 Refresh Stats"):
        st.rerun()


tab_upload, tab_ask = st.tabs(["📁  Upload & Ingest", "💬  Ask Questions"])


with tab_upload:
    st.header("Document Upload & Ingestion")
    st.markdown("Upload insurance documents (PDF, TXT, Markdown). They will be chunked, embedded, and indexed.")

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
                (raw_dir / f.name).write_bytes(f.read())
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
    col_btn, col_reset = st.columns(2)
    reset = col_reset.checkbox("Reset index before ingesting", value=True)

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
                st.markdown(f"- `{f.name}` — {round(f.stat().st_size / 1024, 1)} KB")
        else:
            st.info("No documents yet. Upload some above.")
    else:
        st.info("data/raw/ does not exist yet.")


with tab_ask:
    st.header("Ask the Documents")
    st.markdown(
        "Ask a question. The system retrieves the most relevant chunks and generates "
        "a **grounded answer with citations** — or says **'I don't know'** if the answer isn't in the documents."
    )

    question = st.text_area("Your question", placeholder="e.g. How soon must I report a theft claim?", height=80)

    if st.button("🔍 Ask", type="primary"):
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
                            st.markdown("**Sources:** " + ", ".join(f"`{s}`" for s in resp.sources))
                    else:
                        st.warning("⚠️ I don't know — the answer is not in the documents.")
                        st.markdown(f"_{resp.answer}_")

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

    if st.session_state.get("history"):
        st.divider()
        st.subheader("🕓 History")
        for item in st.session_state.history[:5]:
            icon = "✅" if item["can"] else "❓"
            with st.expander(f"{icon} {item['q'][:80]}"):
                st.write(item["a"])
                if item["sources"]:
                    st.caption("Sources: " + ", ".join(item["sources"]))
