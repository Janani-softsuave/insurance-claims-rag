"""Command-line interface.

Examples:
    python -m app.cli ingest --reset
    python -m app.cli ingest --chunk-size 400 --chunk-overlap 60
    python -m app.cli ask "What temperature do I bake chocolate chip cookies at?"
    python -m app.cli stats
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.config import settings
from app.guardrails.guards import InputValidationError
from app.ingestion.pipeline import ingest as run_ingest
from app.services.rag_service import RagService
from app.vectorstore.chroma_store import get_store

app = typer.Typer(help="Week 3 AI POC — Insurance Claims RAG (ask your policy documents).")
console = Console()


@app.command()
def ingest(
    reset: bool = typer.Option(False, help="Clear the collection before ingesting."),
    chunk_size: int = typer.Option(settings.chunk_size, help="Chunk size (characters)."),
    chunk_overlap: int = typer.Option(settings.chunk_overlap, help="Overlap (characters)."),
    data_dir: str = typer.Option(settings.data_raw_dir, help="Folder of source documents."),
) -> None:
    """Load, chunk, embed and index the documents."""
    result = run_ingest(
        data_dir=data_dir,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        reset=reset,
    )
    console.print(
        Panel.fit(
            f"[green]Ingestion complete[/green]\n"
            f"Documents loaded : {result.documents_loaded}\n"
            f"Chunks indexed   : {result.chunks_indexed}\n"
            f"Collection       : {result.collection}\n"
            f"Chunk size/overlap: {result.chunk_size}/{result.chunk_overlap}",
            title="ingest",
        )
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question about the documents."),
    top_k: int = typer.Option(settings.top_k, help="Dense candidates to retrieve."),
    rerank_top_n: int = typer.Option(settings.rerank_top_n, help="Chunks kept after rerank."),
) -> None:
    """Ask a question and get a grounded, cited answer (or 'I don't know')."""
    service = RagService()
    try:
        response = service.ask(question, top_k=top_k, rerank_top_n=rerank_top_n)
    except InputValidationError as exc:
        console.print(f"[red]Refused:[/red] {exc}")
        raise typer.Exit(code=1)

    color = "green" if response.can_answer else "yellow"
    console.print(Panel(response.answer, title="Answer", border_style=color))

    if response.citations:
        table = Table(title="Citations", show_lines=True)
        table.add_column("Source", style="cyan", no_wrap=True)
        table.add_column("Snippet")
        for c in response.citations:
            table.add_row(c.source, c.snippet)
        console.print(table)

    if response.sources:
        console.print(f"[dim]Retrieved from: {', '.join(response.sources)}[/dim]")


@app.command()
def stats() -> None:
    """Show how many chunks are currently indexed."""
    store = get_store()
    console.print(
        Panel.fit(
            f"Collection : {store.collection_name}\n"
            f"Chunks     : {store.count()}\n"
            f"Storage    : {store.path}",
            title="stats",
        )
    )


if __name__ == "__main__":
    app()
