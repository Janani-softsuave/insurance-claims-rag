from __future__ import annotations

import json
import time

import typer
from rich.console import Console
from rich.table import Table

from app.core.config import ROOT_DIR
from app.evaluation.assertions import run_assertions
from app.evaluation.judge import Judge
from app.models.schemas import Chunk, ClaimSummary, RetrievedChunk
from app.services.claim_summary_service import ClaimSummaryService

app = typer.Typer(help="Week 6 claim-summary eval — one command, mode-tagged pass rates.")
console = Console()

WEEK6_DIR = ROOT_DIR / "analysis" / "week6"
CASES_PATH = WEEK6_DIR / "eval_cases.json"
CACHE_PATH = WEEK6_DIR / "summaries_cache.json"
LABELS_PATH = WEEK6_DIR / "labels_25.json"


def _load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _chunk_to_dict(rc: RetrievedChunk) -> dict:
    return {
        "chunk_id": rc.chunk.id,
        "source": rc.chunk.source,
        "chunk_index": rc.chunk.chunk_index,
        "text": rc.chunk.text,
        "score": rc.score,
    }


def _chunk_from_dict(d: dict) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(id=d["chunk_id"], text=d["text"], source=d["source"], source_path="", chunk_index=d["chunk_index"]),
        score=d["score"],
    )


def _generate_cache() -> list[dict]:
    cases = _load_cases()
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else []
    done_ids = {entry["id"] for entry in cache}
    pending = [c for c in cases if c["id"] not in done_ids]

    if not pending:
        console.print(f"[green]All {len(cases)} summaries already cached in {CACHE_PATH}[/green]")
        return cache

    console.print(f"[dim]{len(done_ids)} cached, {len(pending)} to generate[/dim]")
    service = ClaimSummaryService()
    for case in pending:
        console.print(f"[dim]generating[/dim] {case['id']} ({case['mode']}) — {case['adjuster_notes'][:60]}...")
        try:
            summary, chunks = service.summarize(case["adjuster_notes"])
        except Exception as exc:
            console.print(f"[red]{case['id']} failed ({exc.__class__.__name__}) — stopping, {len(cache)} cached so far.[/red]")
            CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            raise
        cache.append(
            {
                **case,
                "summary": summary.model_dump(),
                "chunks": [_chunk_to_dict(rc) for rc in chunks],
            }
        )
        CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    console.print(f"[green]Wrote {len(cache)} summaries to {CACHE_PATH}[/green]")
    return cache


@app.command()
def generate(force: bool = typer.Option(False, help="Discard the existing cache and regenerate everything.")) -> None:
    """Generate claim summaries for all eval cases (one LLM call per case, resumable)."""
    if force and CACHE_PATH.exists():
        CACHE_PATH.unlink()
    _generate_cache()


@app.command()
def run(
    judge_version: str = typer.Option("v1", help="Judge prompt version: v1 or v2."),
    regenerate: bool = typer.Option(False, help="Regenerate summaries even if a cache exists."),
    delay: float = typer.Option(13.0, help="Seconds to sleep between judge calls (stays under free-tier RPM caps)."),
) -> None:
    """Run the full Week 6 eval: assertions + judge, pass rate by mode."""
    if not CACHE_PATH.exists() or regenerate:
        cache = _generate_cache()
    else:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    judge = Judge(prompt_version=judge_version)
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"] if LABELS_PATH.exists() else {}

    results_path = WEEK6_DIR / f"judge_results_{judge_version}.json"
    judge_results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else {}

    for entry in cache:
        if entry["id"] in judge_results:
            continue
        summary = ClaimSummary.model_validate(entry["summary"])
        chunks = [_chunk_from_dict(d) for d in entry["chunks"]]
        console.print(f"[dim]judging[/dim] {entry['id']} ({judge_version})...")
        try:
            verdict = None
            for backoff_attempt in range(3):
                try:
                    verdict = judge.judge(entry["adjuster_notes"], chunks, summary)
                    break
                except Exception as exc:
                    if "UNAVAILABLE" not in str(exc) or backoff_attempt == 2:
                        raise
                    wait_s = 15 * (backoff_attempt + 1)
                    console.print(f"[yellow]{entry['id']} hit a transient 503 — retrying in {wait_s}s...[/yellow]")
                    time.sleep(wait_s)
        except Exception as exc:
            console.print(f"[red]{entry['id']} failed ({exc.__class__.__name__}) — stopping, {len(judge_results)} judged so far.[/red]")
            results_path.write_text(json.dumps(judge_results, indent=2), encoding="utf-8")
            raise
        judge_results[entry["id"]] = {"faithful": verdict.faithful, "rationale": verdict.rationale}
        results_path.write_text(json.dumps(judge_results, indent=2), encoding="utf-8")
        time.sleep(delay)

    rows = []
    for entry in cache:
        summary = ClaimSummary.model_validate(entry["summary"])
        assertion_results = run_assertions(summary)
        assertions_pass = all(assertion_results.values())
        verdict_dict = judge_results[entry["id"]]
        overall_pass = assertions_pass and verdict_dict["faithful"]
        rows.append(
            {
                "id": entry["id"],
                "mode": entry["mode"],
                "is_regression": entry["is_regression"],
                "assertions_pass": assertions_pass,
                "judge_faithful": verdict_dict["faithful"],
                "overall_pass": overall_pass,
            }
        )

    table = Table(title=f"Week 6 Eval — judge {judge_version}", show_lines=False)
    table.add_column("Mode")
    table.add_column("Cases", justify="right")
    table.add_column("Assertions pass", justify="right")
    table.add_column("Judge faithful", justify="right")
    table.add_column("Overall pass", justify="right")

    for mode in sorted({r["mode"] for r in rows}):
        mode_rows = [r for r in rows if r["mode"] == mode]
        n = len(mode_rows)
        a = sum(r["assertions_pass"] for r in mode_rows)
        j = sum(r["judge_faithful"] for r in mode_rows)
        o = sum(r["overall_pass"] for r in mode_rows)
        table.add_row(mode, str(n), f"{a}/{n}", f"{j}/{n}", f"{o}/{n}")

    total = len(rows)
    a_total = sum(r["assertions_pass"] for r in rows)
    j_total = sum(r["judge_faithful"] for r in rows)
    o_total = sum(r["overall_pass"] for r in rows)
    table.add_row("TOTAL", str(total), f"{a_total}/{total}", f"{j_total}/{total}", f"{o_total}/{total}")

    console.print(table)

    if labels:
        agree = sum(1 for r in rows if r["id"] in labels and labels[r["id"]]["faithful"] == r["judge_faithful"])
        labeled = sum(1 for r in rows if r["id"] in labels)
        console.print(
            f"\n[bold]Agreement with labels_25.json ({judge_version}): {agree}/{labeled} = {agree / labeled:.1%}[/bold]"
        )


if __name__ == "__main__":
    app()
