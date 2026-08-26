from __future__ import annotations

import json
import random
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.core.config import settings
from app.core.tracing import find_trace, read_traces
from app.generation.generator import Generator
from app.guardrails.guards import InputValidationError
from app.ingestion.pipeline import ingest as run_ingest
from app.models.schemas import RetrievedChunk
from app.services.rag_service import RagService
from app.vectorstore.chroma_store import get_store

app = typer.Typer(help="Insurance Claims RAG — ask your policy documents.")
trace_app = typer.Typer(help="Inspect, sample, and replay logged traces.")
app.add_typer(trace_app, name="trace")
console = Console()


@app.command()
def ingest(
    reset: bool = typer.Option(False, help="Clear the collection before ingesting."),
    chunk_size: int = typer.Option(settings.chunk_size, help="Chunk size (characters)."),
    chunk_overlap: int = typer.Option(settings.chunk_overlap, help="Overlap (characters)."),
    data_dir: str = typer.Option(settings.data_raw_dir, help="Folder of source documents."),
) -> None:
    """Load, chunk, embed and index documents."""
    result = run_ingest(data_dir=data_dir, chunk_size=chunk_size, chunk_overlap=chunk_overlap, reset=reset)
    console.print(
        Panel.fit(
            f"[green]Ingestion complete[/green]\n"
            f"Documents loaded  : {result.documents_loaded}\n"
            f"Chunks indexed    : {result.chunks_indexed}\n"
            f"Collection        : {result.collection}\n"
            f"Chunk size/overlap: {result.chunk_size}/{result.chunk_overlap}",
            title="ingest",
        )
    )


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question."),
    top_k: int = typer.Option(settings.top_k, help="Dense candidates to retrieve."),
    rerank_top_n: int = typer.Option(settings.rerank_top_n, help="Chunks kept after rerank."),
) -> None:
    """Ask a question and get a grounded, cited answer."""
    service = RagService()
    try:
        response = service.ask(question, top_k=top_k, rerank_top_n=rerank_top_n)
    except InputValidationError as exc:
        console.print(f"[red]Refused:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(Panel(response.answer, title="Answer", border_style="green" if response.can_answer else "yellow"))

    if response.citations:
        table = Table(title="Citations", show_lines=True)
        table.add_column("Source", style="cyan", no_wrap=True)
        table.add_column("Snippet")
        for c in response.citations:
            table.add_row(c.source, c.snippet)
        console.print(table)

    if response.sources:
        console.print(f"[dim]Retrieved from: {', '.join(response.sources)}[/dim]")
    console.print(f"[dim]trace_id: {response.trace_id}[/dim]")


@app.command()
def stats() -> None:
    """Show index stats."""
    store = get_store()
    console.print(
        Panel.fit(
            f"Collection : {store.collection_name}\n"
            f"Chunks     : {store.count()}\n"
            f"Storage    : {store.path}",
            title="stats",
        )
    )


@trace_app.command("sample")
def trace_sample(
    n: int = typer.Option(20, help="Sample size."),
    seed: int = typer.Option(..., help="Random seed — paste this in the write-up."),
    out: str = typer.Option("analysis/week5/sample_trace_ids.json", help="Where to write the sample."),
) -> None:
    """Draw a seeded random sample of trace_ids from the trace log."""
    traces = read_traces()
    population = [t.trace_id for t in traces]
    if len(population) < n:
        console.print(
            f"[red]Only {len(population)} trace(s) logged — need at least {n}. Run more queries first.[/red]"
        )
        raise typer.Exit(code=1)

    sample = random.Random(seed).sample(population, n)
    payload = {"seed": seed, "population_size": len(population), "sample_size": n, "trace_ids": sample}

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    console.print(Panel.fit(
        f"Seed              : {seed}\n"
        f"Population size   : {len(population)}\n"
        f"Sample size       : {n}\n"
        f"Written to        : {out_path}",
        title="trace sample",
    ))
    for trace_id in sample:
        console.print(f"  • {trace_id}")


@trace_app.command("replay")
def trace_replay(trace_id: str = typer.Argument(..., help="trace_id to replay.")) -> None:
    """Replay a trace's generation step from the trace alone and compare to the original."""
    trace = find_trace(trace_id)
    if trace is None:
        console.print(f"[red]No trace found with id '{trace_id}'.[/red]")
        raise typer.Exit(code=1)
    if trace.model is None:
        console.print(
            f"[yellow]Trace '{trace_id}' never reached generation (can_answer={trace.can_answer}, "
            "no model was called) — nothing to replay.[/yellow]"
        )
        raise typer.Exit(code=1)

    store = get_store()
    chunk_ids = [rc.chunk_id for rc in trace.retrieved_chunks]
    fetched = {c.id: c for c in store.get_by_ids(chunk_ids)}

    missing_ids = [cid for cid in chunk_ids if cid not in fetched]
    ordered_chunks = [
        RetrievedChunk(chunk=fetched[rc.chunk_id], score=rc.score)
        for rc in trace.retrieved_chunks
        if rc.chunk_id in fetched
    ]

    generator = Generator(model=trace.model)
    replayed = generator.generate(trace.question_redacted, ordered_chunks)

    console.print(Panel.fit(
        f"trace_id          : {trace.trace_id}\n"
        f"prompt_version    : {trace.prompt_version}\n"
        f"model             : {trace.model}\n"
        f"chunk_ids used    : {len(ordered_chunks)}/{len(chunk_ids)}"
        + (f" ({len(missing_ids)} missing from the store)" if missing_ids else ""),
        title="replay setup",
    ))
    console.print(Panel(trace.answer_redacted, title="ORIGINAL answer", border_style="cyan"))
    console.print(Panel(replayed.answer.answer, title="REPLAYED answer", border_style="magenta"))

    if missing_ids:
        console.print(f"[yellow]Could not reconstruct chunk(s): {missing_ids} — not found in the vector store.[/yellow]")
    if trace.pii_redacted:
        console.print(
            "[yellow]The original question contained PII that was redacted before the trace was written — "
            "replay uses the redacted text, so it is not byte-for-byte the original input.[/yellow]"
        )


if __name__ == "__main__":
    app()
