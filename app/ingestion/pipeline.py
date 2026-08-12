from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.embedder import get_embedder
from app.ingestion.chunker import chunk_documents
from app.ingestion.loaders import load_directory
from app.models.schemas import IngestResponse
from app.vectorstore.chroma_store import get_store

logger = get_logger(__name__)


def ingest(
    data_dir: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    reset: bool = False,
) -> IngestResponse:
    data_dir = data_dir or settings.data_raw_dir
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    documents = load_directory(data_dir)
    if not documents:
        raise ValueError(f"No supported documents found in {data_dir}")

    chunks = chunk_documents(documents, chunk_size, chunk_overlap)
    embeddings = get_embedder().embed_documents([c.text for c in chunks])

    store = get_store()
    if reset:
        store.reset()
    store.add(chunks, embeddings)

    logger.info("Ingestion complete — %d chunk(s) in store", store.count())
    return IngestResponse(
        documents_loaded=len(documents),
        chunks_indexed=len(chunks),
        collection=store.collection_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
