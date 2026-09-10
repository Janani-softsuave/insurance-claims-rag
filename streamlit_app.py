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
def load_service(use_hybrid: bool):
    from app.services.rag_service import RagService
    return RagService(use_hybrid=use_hybrid)


def get_store():
    from app.vectorstore.chroma_store import ChromaStore
    from app.core.config import settings
    return ChromaStore(path=settings.chroma_path, collection_name=settings.collection_name)


with st.sidebar:
    st.title("📋 Insurance Claims RAG")
    st.caption("Week 3 + 4 — Retrieval & RAG / Debugging")
    st.divider()

    st.subheader("⚙️ Chunking")
    chunk_size = st.slider("Chunk Size (chars)", 100, 2000, 800, step=50)
    chunk_overlap = st.slider("Overlap (chars)", 0, 500, 120, step=10)

    st.subheader("🔍 Retrieval")
    top_k = st.slider("Top K candidates", 4, 20, 8)
    rerank_top_n = st.slider("Rerank Top N", 2, 8, 4)
    use_hybrid = st.toggle("Hybrid Search (BM25 + Dense)", value=False,
                           help="Combines keyword (BM25) and semantic search via RRF fusion.")

    st.subheader("🧠 Query Transformation")
    use_hyde = st.toggle("HyDE", value=False,
                         help="Generate a hypothetical answer and embed that instead of the question. "
                              "Better for vague or indirect questions.")
    use_rewriting = st.toggle("Query Rewriting", value=False,
                              help="Rewrites the question into a precise search query before retrieval. "
                                   "Ignored when HyDE is on.")

    st.subheader("🎯 Reranking")
    use_mmr = st.toggle("MMR (Diversity)", value=False,
                        help="Maximal Marginal Relevance — reduces redundant chunks so the LLM "
                             "sees diverse evidence. λ controls relevance vs diversity balance.")
    mmr_lambda = st.slider("MMR λ (relevance ↔ diversity)", 0.0, 1.0, 0.5, step=0.1,
                           disabled=not use_mmr,
                           help="1.0 = pure relevance (no diversity), 0.0 = pure diversity.")

    st.divider()
    st.subheader("📊 Index Stats")
    try:
        store = get_store()
        c1, c2 = st.columns(2)
        c1.metric("Chunks", store.count())
        c2.metric("Collection", store.collection_name)
    except Exception:
        st.warning("Index not built yet.")

    if st.button("🔄 Refresh Stats"):
        st.rerun()


tab_upload, tab_ask, tab_inspect, tab_eval, tab_agent = st.tabs([
    "📁 Upload & Ingest",
    "💬 Ask Questions",
    "🔍 Inspection View",
    "📊 Evaluation",
    "🤖 Agent vs Workflow",
])

with tab_upload:
    st.header("Document Upload & Ingestion")
    st.info(
        "**Step 1 (optional):** Upload documents — saved to `data/raw/`.\n\n"
        "**Step 2:** Click **Run Ingestion** to chunk, embed, and index all documents."
    )

    col_up, col_cfg = st.columns([2, 1])
    with col_up:
        st.subheader("📤 Upload New Document (optional)")
        uploaded_files = st.file_uploader(
            "Drop files here — saved to data/raw/",
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
            st.success(f"Saved {len(saved)} file(s): {', '.join(saved)} — now click Run Ingestion.")

    with col_cfg:
        st.subheader("🔧 Active Config")
        active = [f"**Chunk:** {chunk_size}c / {chunk_overlap}c overlap", f"**Top K:** {top_k} | **Rerank N:** {rerank_top_n}"]
        if use_hybrid: active.append("🔀 Hybrid search")
        if use_hyde: active.append("🧠 HyDE")
        elif use_rewriting: active.append("✏️ Query rewriting")
        if use_mmr: active.append(f"🎯 MMR (λ={mmr_lambda})")
        st.info("\n\n".join(active))

    st.divider()
    col_btn, col_reset = st.columns(2)
    reset = col_reset.checkbox("Reset index before ingesting", value=True,
                               help="Check when changing chunk size or replacing documents.")

    if "ingesting" not in st.session_state:
        st.session_state.ingesting = False

    if col_btn.button("⚡ Run Ingestion", width="stretch", type="primary",
                      disabled=st.session_state.ingesting):
        st.session_state.ingesting = True
        st.rerun()

    if st.session_state.ingesting:
        from app.ingestion.pipeline import ingest
        with st.spinner("Ingesting documents… please wait."):
            try:
                result = ingest(chunk_size=chunk_size, chunk_overlap=chunk_overlap, reset=reset)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Documents loaded", result.documents_loaded)
                m2.metric("Chunks indexed", result.chunks_indexed)
                m3.metric("Chunk size", result.chunk_size)
                m4.metric("Overlap", result.chunk_overlap)
                st.success(f"✅ Indexed into collection **'{result.collection}'**")
            except Exception as e:
                st.error(f"Ingestion failed: {e}")
            finally:
                st.session_state.ingesting = False

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
    active_tags = []
    if use_hybrid: active_tags.append("🔀 Hybrid")
    if use_hyde: active_tags.append("🧠 HyDE")
    elif use_rewriting: active_tags.append("✏️ Rewriting")
    if use_mmr: active_tags.append(f"🎯 MMR λ={mmr_lambda}")
    if active_tags:
        st.info("Active: " + " · ".join(active_tags))

    question = st.text_area("Your question", placeholder="e.g. How soon must I report a theft claim?", height=80)

    if st.button("🔍 Ask", type="primary"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Retrieving and generating…"):
                try:
                    service = load_service(use_hybrid)
                    resp = service.ask(
                        question.strip(),
                        top_k=top_k,
                        rerank_top_n=rerank_top_n,
                        use_query_rewriting=use_rewriting,
                        use_mmr=use_mmr,
                        mmr_lambda=mmr_lambda,
                        use_hyde=use_hyde,
                    )

                    if use_hyde:
                        st.caption("🧠 HyDE: retrieved using a hypothetical document embedding.")
                    elif resp.rewritten_question and resp.rewritten_question != question.strip():
                        st.caption(f"✏️ Rewritten query: *{resp.rewritten_question}*")
                    if use_mmr:
                        st.caption(f"🎯 MMR applied (λ={mmr_lambda}) — chunks diversified.")

                    if resp.retrieval_only:
                        st.warning("⚠️ LLM unavailable — showing retrieved chunks directly.")
                        if resp.sources:
                            st.markdown("**Sources:** " + ", ".join(f"`{s}`" for s in resp.sources))
                        for block in resp.answer.split("\n\n---\n\n"):
                            st.markdown(block)
                            st.divider()
                    elif resp.can_answer:
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
                        "retrieved": resp.retrieved_chunks,
                        "rewritten": resp.rewritten_question,
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
                if item.get("sources"):
                    st.caption("Sources: " + ", ".join(item["sources"]))


with tab_inspect:
    st.header("🔍 Inspection View")
    st.markdown(
        "Diagnose failures by examining **what was retrieved** alongside the answer. "
        "Label each result as a retrieval failure, generation failure, or correct."
    )

    history = st.session_state.get("history", [])
    if not history:
        st.info("Ask a question first in the **Ask Questions** tab — the inspection will appear here.")
    else:
        options = [f"{i+1}. {h['q'][:70]}" for i, h in enumerate(history)]
        selected = st.selectbox("Select a question to inspect", options)
        idx = int(selected.split(".")[0]) - 1
        item = history[idx]

        st.subheader("Question")
        st.markdown(f"> {item['q']}")
        if item.get("rewritten") and item["rewritten"] != item["q"]:
            st.caption(f"Rewritten as: *{item['rewritten']}*")

        col_ret, col_ans = st.columns([1, 1])

        with col_ret:
            st.subheader("Retrieved Chunks")
            chunks = item.get("retrieved", [])
            if chunks:
                for i, c in enumerate(chunks, 1):
                    score_color = "green" if c.score > 0.6 else "orange" if c.score > 0.4 else "red"
                    st.markdown(
                        f"**[{i}]** `{c.source}` — chunk {c.chunk_index} "
                        f"| score: :{score_color}[**{c.score:.3f}**]"
                    )
                    with st.expander("View chunk text"):
                        st.text(c.text)
            else:
                st.info("No chunk data. Re-ask the question with the current version.")

        with col_ans:
            st.subheader("Final Answer")
            if item["can"]:
                st.success(item["a"])
            else:
                st.warning(item["a"])

        st.divider()
        st.subheader("🏷️ Label This Result")
        st.markdown(
            "**Retrieval failure** — the fetched documents don't contain the answer to this question.\n\n"
            "**Generation failure** — the right document was fetched but the answer is wrong or incomplete."
        )
        label = st.radio(
            "Failure type",
            ["✅ Correct", "🔴 Retrieval failure", "🟡 Generation failure"],
            horizontal=True,
        )
        if st.button("Save label"):
            history[idx]["label"] = label
            st.session_state.history = history
            st.success(f"Labelled as: **{label}**")

        st.divider()
        labelled = [h for h in history if h.get("label")]
        if labelled:
            st.subheader("📋 All Labels")
            for h in labelled:
                st.markdown(f"- {h['label']} — *{h['q'][:70]}*")


with tab_eval:
    st.header("📊 Retrieval Evaluation")
    st.markdown(
        "Runs a fixed set of test questions and measures **hit-rate@k** and **MRR** "
        "for dense-only vs hybrid retrieval — the before/after number the mentor checks."
    )

    K = st.slider("k for hit-rate@k", 1, 10, 3)

    TEST_QUERIES = [
        {"question": "How soon must I report a theft claim?",             "expected_source": "claims_faq.md"},
        {"question": "What documents are needed for a motor claim?",      "expected_source": "claims_process.md"},
        {"question": "Is earthquake damage covered by default?",          "expected_source": "endorsements_and_riders.md"},
        {"question": "What is Zero Dep IMT-28 endorsement?",             "expected_source": "endorsements_and_riders.md"},
        {"question": "What is IDV depreciation for a 3-year-old car?",   "expected_source": "claims_faq.md"},
        {"question": "Compulsory deductible for property claim?",         "expected_source": "insurance_policy_overview.md"},
        {"question": "RTI return to invoice cover vehicles",              "expected_source": "endorsements_and_riders.md"},
        {"question": "cashless garage network settlement",                "expected_source": "claims_process.md"},
        {"question": "total loss repair cost exceeds IDV",                "expected_source": "claims_faq.md"},
        {"question": "personal accident death disability sum insured",    "expected_source": "insurance_policy_overview.md"},
    ]

    if st.button("▶ Run Evaluation", type="primary"):
        from app.evaluation.metrics import evaluate, hit_rate_at_k, reciprocal_rank
        from app.retrieval.hybrid_retriever import HybridRetriever
        from app.retrieval.retriever import Retriever as DenseRetriever

        with st.spinner("Running evaluation on all test queries…"):
            try:
                store = get_store()
                dense = DenseRetriever(store=store)
                hybrid = HybridRetriever(store=store)

                rows = []
                for item in TEST_QUERIES:
                    q, exp = item["question"], item["expected_source"]
                    d_chunks = dense.retrieve(q, top_k=K)
                    h_chunks = hybrid.retrieve(q, top_k=K)
                    d_hit = hit_rate_at_k(d_chunks, exp, K)
                    h_hit = hit_rate_at_k(h_chunks, exp, K)
                    d_rr = reciprocal_rank(d_chunks, exp)
                    h_rr = reciprocal_rank(h_chunks, exp)

                    failure = "✅ Correct" if d_hit else "🔴 Retrieval failure"
                    rows.append({
                        "Question": q,
                        "Expected": exp,
                        f"Dense hit@{K}": "✅" if d_hit else "❌",
                        f"Hybrid hit@{K}": "✅" if h_hit else "❌",
                        "Dense RR": f"{d_rr:.2f}",
                        "Hybrid RR": f"{h_rr:.2f}",
                        "Failure type": failure,
                    })

                import pandas as pd
                df = pd.DataFrame(rows)
                st.dataframe(df, width="stretch")

                dense_hr = sum(1 for r in rows if r[f"Dense hit@{K}"] == "✅") / len(rows)
                hybrid_hr = sum(1 for r in rows if r[f"Hybrid hit@{K}"] == "✅") / len(rows)
                dense_mrr = sum(float(r["Dense RR"]) for r in rows) / len(rows)
                hybrid_mrr = sum(float(r["Hybrid RR"]) for r in rows) / len(rows)
                delta_hr = hybrid_hr - dense_hr

                st.divider()
                st.subheader("Before / After Summary")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(f"Dense hit-rate@{K}", f"{dense_hr:.3f}")
                m2.metric(f"Hybrid hit-rate@{K}", f"{hybrid_hr:.3f}",
                          delta=f"{delta_hr:+.3f}", delta_color="normal")
                m3.metric("Dense MRR", f"{dense_mrr:.3f}")
                m4.metric("Hybrid MRR", f"{hybrid_mrr:.3f}",
                          delta=f"{hybrid_mrr - dense_mrr:+.3f}", delta_color="normal")

                if delta_hr > 0:
                    st.success(f"✅ Hybrid search improved hit-rate@{K} by **{delta_hr:.3f}** ({delta_hr*100:.1f} pp)")
                elif delta_hr == 0:
                    st.info("No change in hit-rate@k between dense and hybrid.")
                else:
                    st.warning(f"Hybrid did not improve hit-rate@{K} on this corpus.")

                failures = [r for r in rows if r[f"Dense hit@{K}"] == "❌"]
                if failures:
                    st.subheader("❌ Failures not fixed by hybrid search")
                    still_failing = [r for r in failures if r[f"Hybrid hit@{K}"] == "❌"]
                    if still_failing:
                        for r in still_failing:
                            st.markdown(f"- *{r['Question']}* → expected `{r['Expected']}`")
                        st.caption(
                            "These are likely **generation failures** (right doc retrieved, wrong answer) "
                            "or require a better chunking strategy."
                        )

            except Exception as e:
                st.error(f"Evaluation failed: {e}")


with tab_agent:
    st.header("🤖 Agent vs Workflow — Week 7")
    st.markdown(
        "Triage one claim with the **hand-built agent loop**, the **fixed 4-step workflow**, "
        "or both side by side. Both use the same tools, same model, same output contract — "
        "the agent decides what to call next; the workflow's steps are hard-coded."
    )

    from app.agent.tools import load_claims

    claims = load_claims()
    claim_options = {f"{c['claim_number']} — {c['adjuster_notes'][:60]}...": c for c in claims}
    selected_label = st.selectbox("Claim", list(claim_options.keys()))
    selected_claim = claim_options[selected_label]

    with st.expander("📄 Claim record & ground truth"):
        c1, c2 = st.columns(2)
        c1.json({
            "claim_number": selected_claim["claim_number"],
            "policy_id": selected_claim["policy_id"],
            "sum_insured": selected_claim["sum_insured"],
            "excess_amount": selected_claim["excess_amount"],
            "claimed_amount": selected_claim["claimed_amount"],
        })
        c2.markdown(f"**Adjuster notes:**\n\n{selected_claim['adjuster_notes']}")
        st.caption(
            f"Expected (ground truth, not shown to either system): "
            f"**{selected_claim['expected_status']}**, payout ₹{selected_claim['expected_payout']:,.0f}"
        )

    mode = st.radio(
        "Mode",
        ["Agent only", "Workflow only", "Both (side by side)"],
        horizontal=True,
    )

    with st.expander("⚙️ Agent budgets"):
        b1, b2, b3, b4 = st.columns(4)
        max_iterations = b1.number_input("Max iterations", 1, 30, 8)
        max_tokens = b2.number_input("Max tokens", 1000, 200_000, 30_000, step=1000)
        max_cost = b3.number_input("Max cost (USD)", 0.001, 1.0, 0.05, step=0.001, format="%.3f")
        max_wall_clock = b4.number_input("Max wall-clock (s)", 5, 600, 90)

    def _run_agent():
        from app.agent.claims_agent import ClaimsAgent
        from app.agent.budgets import Budgets
        budgets = Budgets(
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            max_cost_usd=max_cost,
            max_wall_clock_seconds=max_wall_clock,
        )
        return ClaimsAgent(budgets=budgets).run(selected_claim["claim_number"])

    def _run_workflow():
        from app.agent.claims_workflow import ClaimsWorkflow
        return ClaimsWorkflow().run(selected_claim["claim_number"])

    def _grade(status, payout) -> bool | None:
        if status is None:
            return None
        if payout is None:
            return False
        return status == selected_claim["expected_status"] and abs(payout - selected_claim["expected_payout"]) < 1.0

    def _render_agent_result(result) -> None:
        passed = _grade(result.status, result.payout)
        if result.terminated_by_budget:
            st.warning(f"⏱️ Budget terminated the run: **{result.terminated_by_budget}** — no decision reached.")
        elif passed:
            st.success(f"✅ {result.status} — payout ₹{result.payout:,.0f}" if result.payout is not None else f"✅ {result.status}")
        elif result.flagged_for_review:
            st.info(f"🚩 Flagged for human review: {result.rationale}")
        else:
            st.error(f"❌ {result.status} — payout {result.payout} (expected {selected_claim['expected_status']} / ₹{selected_claim['expected_payout']:,.0f})")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Iterations", result.iterations)
        m2.metric("Tokens", result.total_tokens)
        m3.metric("Cost (USD)", f"${result.total_cost_usd:.6f}")
        m4.metric("Latency (s)", f"{result.elapsed_seconds:.1f}")

        if result.rationale and not result.flagged_for_review:
            st.caption(result.rationale)

        with st.expander(f"🪜 Step-by-step log ({len(result.tool_calls)} tool call(s))"):
            for line in result.log:
                st.text(line)

    def _render_workflow_result(result: dict) -> None:
        passed = _grade(result["status"], result["payout"])
        if passed:
            st.success(f"✅ {result['status']} — payout ₹{result['payout']:,.0f}")
        else:
            st.error(
                f"❌ {result['status']} — payout ₹{result['payout']:,.0f} "
                f"(expected {selected_claim['expected_status']} / ₹{selected_claim['expected_payout']:,.0f})"
            )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Steps", len(result["tool_calls"]))
        m2.metric("Tokens", result["total_tokens"])
        m3.metric("Cost (USD)", f"${result['total_cost_usd']:.6f}")
        m4.metric("Latency (s)", f"{result['elapsed_seconds']:.1f}")

        st.caption(result["rationale"])
        with st.expander("🪜 Fixed steps"):
            for i, step in enumerate(result["tool_calls"], 1):
                st.text(f"{i}. {step}")

    if st.button("▶ Run", type="primary"):
        try:
            if mode == "Agent only":
                with st.spinner("Agent looping…"):
                    agent_result = _run_agent()
                st.subheader("🤖 Agent")
                _render_agent_result(agent_result)

            elif mode == "Workflow only":
                with st.spinner("Running fixed workflow…"):
                    workflow_result = _run_workflow()
                st.subheader("📋 Workflow")
                _render_workflow_result(workflow_result)

            else:
                col_wf, col_ag = st.columns(2)
                with st.spinner("Running workflow, then agent…"):
                    workflow_result = _run_workflow()
                    agent_result = _run_agent()
                with col_wf:
                    st.subheader("📋 Workflow")
                    _render_workflow_result(workflow_result)
                with col_ag:
                    st.subheader("🤖 Agent")
                    _render_agent_result(agent_result)

                st.divider()
                st.subheader("Comparison")
                import pandas as pd
                agent_passed = _grade(agent_result.status, agent_result.payout)
                workflow_passed = _grade(workflow_result["status"], workflow_result["payout"])
                st.dataframe(
                    pd.DataFrame([
                        {"System": "workflow", "Status": workflow_result["status"], "Payout": workflow_result["payout"],
                         "Pass": "✅" if workflow_passed else "❌", "Tokens": workflow_result["total_tokens"],
                         "Cost (USD)": f"${workflow_result['total_cost_usd']:.6f}", "Latency (s)": round(workflow_result["elapsed_seconds"], 1)},
                        {"System": "agent", "Status": agent_result.status, "Payout": agent_result.payout,
                         "Pass": "✅" if agent_passed else ("🚩" if agent_result.flagged_for_review else "❌"),
                         "Tokens": agent_result.total_tokens, "Cost (USD)": f"${agent_result.total_cost_usd:.6f}",
                         "Latency (s)": round(agent_result.elapsed_seconds, 1)},
                    ]),
                    width="stretch",
                )
                if agent_result.status != workflow_result["status"]:
                    st.info("⚡ The two systems disagreed on this claim's status — a real signal worth reading the rationale for.")

        except Exception as e:
            st.error(f"Run failed: {e}")

    st.divider()
    st.subheader("📈 Last full race (analysis/week7/race.csv)")
    race_csv = ROOT / "analysis" / "week7" / "race.csv"
    if race_csv.exists():
        import pandas as pd
        st.dataframe(pd.read_csv(race_csv), width="stretch")
        st.caption("From the last `python -m scripts.run_week7_race race` run over all 10 claims.")
    else:
        st.info("No race results yet — run `python -m scripts.run_week7_race race` from the CLI.")
