"""FastAPI routes — the REST interface over the RAG service."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.config import settings
from app.core.logging import get_logger
from app.guardrails.guards import InputValidationError
from app.ingestion.loaders import SUPPORTED_SUFFIXES
from app.ingestion.pipeline import ingest
from app.models.schemas import AskRequest, AskResponse, IngestResponse, UploadResponse
from app.services.rag_service import RagService

logger = get_logger(__name__)
router = APIRouter()

# The service loads the embedding + reranker models, so build it once at import.
_service = RagService()

# Supported MIME types mapped to their extensions.
# We rely on the file extension for type validation (checked above).
# Content-type is browser/client-controlled and unreliable for non-standard
# types (e.g. curl sends .md as application/octet-stream), so we skip it.
_ALLOWED_CONTENT_TYPES: set[str] = set()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/upload", response_model=UploadResponse)
def upload_endpoint(file: UploadFile = File(...)) -> UploadResponse:
    """Upload a document (PDF, TXT, or MD), save it to data/raw/, and index it.

    The file is appended to the existing collection — existing chunks are kept.
    To rebuild from scratch, call POST /ingest?reset=true after uploading.
    """
    # Validate file type by both extension and content-type.
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(SUPPORTED_SUFFIXES)}",
        )
    # Save to data/raw/
    raw_dir = Path(settings.data_raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / file.filename

    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        file.file.close()

    logger.info("Uploaded file saved: %s", dest)

    # Ingest only the newly saved directory (picks up any new/changed files).
    try:
        result = ingest(data_dir=str(raw_dir), reset=False)
    except Exception as exc:
        # Remove the bad file so it doesn't pollute future ingestions.
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return UploadResponse(
        filename=file.filename,
        saved_path=str(dest),
        chunks_indexed=result.chunks_indexed,
        collection=result.collection,
        message=f"'{file.filename}' uploaded and indexed successfully. "
                f"Collection now has {result.chunks_indexed} chunk(s).",
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest_endpoint(reset: bool = False) -> IngestResponse:
    """(Re)build the index from all documents currently in data/raw/."""
    try:
        return ingest(reset=reset)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest) -> AskResponse:
    """Ask a question against the ingested documents."""
    try:
        return _service.ask(
            request.question,
            top_k=request.top_k,
            rerank_top_n=request.rerank_top_n,
        )
    except InputValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
