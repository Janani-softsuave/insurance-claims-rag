"""Compare chunk sizes — directly answers the mentor's check:
"Did they try more than one chunk size and notice the difference?"

For each chunk size we: load -> chunk -> embed -> retrieve (no LLM needed) a set
of probe questions against the insurance claims corpus, and report the best
retrieved chunk + its similarity. This shows how chunk size changes what retrieval
surfaces.

Run:  python -m scripts.evaluate_chunking
"""
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from app.embeddings.embedder import get_embedder
from app.ingestion.chunker import chunk_documents
from app.ingestion.loaders import load_directory
from app.core.config import settings

console = Console()

# Chunk sizes to compare (characters).
CHUNK_SIZES = [300, 800, 1500]
OVERLAP_RATIO = 0.15

# Probe questions whose answers live in the insurance corpus.
PROBES = [
    "How soon must I report a theft claim?",
    "What documents are needed to file a motor claim?",
    "What is a total loss in insurance?",
    "Is earthquake damage covered under a standard property policy?",
]


def _cosine(a: list[float], b: list[float]) -> float:
    # Vectors are already L2-normalized by the embedder, so dot == cosine.
    return sum(x * y for x, y in zip(a, b))


def main() -> None:
    documents = load_directory(settings.data_raw_dir)
    if not documents:
        console.print("[red]No documents found in data/raw. Add the sample corpus first.[/red]")
        return

    embedder = get_embedder()
    query_vectors = {q: embedder.embed_query(q) for q in PROBES}

    for size in CHUNK_SIZES:
        overlap = int(size * OVERLAP_RATIO)
        chunks = chunk_documents(documents, chunk_size=size, chunk_overlap=overlap)
        chunk_vectors = embedder.embed_documents([c.text for c in chunks])

        table = Table(
            title=f"chunk_size={size}  overlap={overlap}  ->  {len(chunks)} chunks",
            show_lines=True,
        )
        table.add_column("Question", style="cyan")
        table.add_column("Best score", justify="right")
        table.add_column("Source", style="magenta")
        table.add_column("Top chunk (truncated)")

        for q in PROBES:
            qv = query_vectors[q]
            scored = [(_cosine(qv, cv), c) for cv, c in zip(chunk_vectors, chunks)]
            best_score, best_chunk = max(scored, key=lambda t: t[0])
            snippet = best_chunk.text.replace("\n", " ")[:90] + "..."
            table.add_row(q, f"{best_score:.3f}", best_chunk.source, snippet)

        console.print(table)
        console.print()

    console.print(
        "[dim]Notice how smaller chunks give sharper, more focused matches while "
        "larger chunks pull in more surrounding context (and can dilute the score).[/dim]"
    )


if __name__ == "__main__":
    main()
