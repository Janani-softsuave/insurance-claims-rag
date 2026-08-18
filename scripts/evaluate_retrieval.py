from __future__ import annotations

from rich.console import Console
from rich.table import Table

from app.evaluation.metrics import evaluate, hit_rate_at_k, reciprocal_rank
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.retriever import Retriever
from app.vectorstore.chroma_store import get_store

console = Console()

K = 3

TEST_QUERIES = [
    {"question": "How soon must I report a theft claim?",             "expected_source": "claims_faq.md"},
    {"question": "What documents are needed for a motor claim?",      "expected_source": "claims_process.md"},
    {"question": "Is earthquake damage covered by default?",          "expected_source": "endorsements_and_riders.md"},
    {"question": "What is Zero Dep IMT-28 endorsement?",             "expected_source": "endorsements_and_riders.md"},
    {"question": "What is IDV depreciation for a 3-year-old car?",   "expected_source": "claims_faq.md"},
    {"question": "What is the compulsory deductible property claim?", "expected_source": "insurance_policy_overview.md"},
    {"question": "RTI return to invoice cover vehicles",              "expected_source": "endorsements_and_riders.md"},
    {"question": "cashless garage network settlement",                "expected_source": "claims_process.md"},
    {"question": "total loss repair cost exceeds IDV",                "expected_source": "claims_faq.md"},
    {"question": "personal accident death disability cover",          "expected_source": "insurance_policy_overview.md"},
]


def main() -> None:
    store = get_store()

    dense = Retriever(store=store)
    hybrid = HybridRetriever(store=store)

    def dense_retrieve(q: str):
        return dense.retrieve(q, top_k=K)

    def hybrid_retrieve(q: str):
        return hybrid.retrieve(q, top_k=K)

    dense_result = evaluate(TEST_QUERIES, dense_retrieve, k=K)
    hybrid_result = evaluate(TEST_QUERIES, hybrid_retrieve, k=K)

    # Per-query breakdown
    table = Table(title=f"Per-query retrieval results  (k={K})", show_lines=True)
    table.add_column("Question", style="cyan")
    table.add_column("Expected source", style="magenta")
    table.add_column(f"Dense hit@{K}", justify="center")
    table.add_column(f"Hybrid hit@{K}", justify="center")
    table.add_column("Failure type")

    for item in TEST_QUERIES:
        q, exp = item["question"], item["expected_source"]
        d_chunks = dense.retrieve(q, top_k=K)
        h_chunks = hybrid.retrieve(q, top_k=K)
        d_hit = hit_rate_at_k(d_chunks, exp, K)
        h_hit = hit_rate_at_k(h_chunks, exp, K)

        # Failure labelling
        if d_hit:
            failure = "✅ Correct"
        elif not d_hit and d_chunks:
            failure = "🔴 Retrieval failure"
        else:
            failure = "⚪ No results"

        table.add_row(
            q[:55] + ("…" if len(q) > 55 else ""),
            exp,
            "✅" if d_hit else "❌",
            "✅" if h_hit else "❌",
            failure,
        )

    console.print(table)

    # Summary
    summary = Table(title="Before / After Summary", show_lines=True)
    summary.add_column("Method")
    summary.add_column(f"hit-rate@{K}", justify="right")
    summary.add_column("MRR", justify="right")
    summary.add_column(f"Hits / {len(TEST_QUERIES)}", justify="right")

    delta_hr = hybrid_result.hit_rate_at_k - dense_result.hit_rate_at_k
    delta_mrr = hybrid_result.mrr - dense_result.mrr

    summary.add_row("Dense (before)", f"{dense_result.hit_rate_at_k:.3f}", f"{dense_result.mrr:.3f}", str(dense_result.hits))
    summary.add_row(
        "Hybrid BM25+Dense (after)",
        f"{hybrid_result.hit_rate_at_k:.3f}  ({'+' if delta_hr >= 0 else ''}{delta_hr:.3f})",
        f"{hybrid_result.mrr:.3f}  ({'+' if delta_mrr >= 0 else ''}{delta_mrr:.3f})",
        str(hybrid_result.hits),
    )
    console.print(summary)

    if delta_hr > 0:
        console.print(f"\n[green]Hybrid search improved hit-rate@{K} by {delta_hr:.3f} (+{delta_hr*100:.1f}pp)[/green]")
    elif delta_hr == 0:
        console.print(f"\n[yellow]No change in hit-rate@{K}[/yellow]")
    else:
        console.print(f"\n[red]Hybrid search did not improve hit-rate@{K}[/red]")


if __name__ == "__main__":
    main()
