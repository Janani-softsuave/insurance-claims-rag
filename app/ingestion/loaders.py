"""Document loaders — turn files on disk into `Document` objects.

Supports the formats the Week-3 brief calls out ("PDFs, web pages") plus plain
text / markdown, which is what our Recipes & Food corpus uses.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.core.logging import get_logger
from app.models.schemas import Document

logger = get_logger(__name__)

# File extensions we know how to read.
TEXT_SUFFIXES = {".md", ".txt"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES


def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_pdf_file(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)


def load_file(path: Path) -> Document | None:
    """Load a single supported file into a Document, or None if unsupported."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        text = _load_text_file(path)
    elif suffix in PDF_SUFFIXES:
        text = _load_pdf_file(path)
    else:
        logger.warning("Skipping unsupported file: %s", path.name)
        return None

    text = text.strip()
    if not text:
        logger.warning("No extractable text in: %s", path.name)
        return None

    return Document(
        text=text,
        source=path.name,
        source_path=str(path.resolve()),
        metadata={"suffix": suffix},
    )


def load_directory(directory: str | Path) -> list[Document]:
    """Load every supported document in a directory (recursively)."""
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Data directory not found: {directory}")

    documents: list[Document] = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            doc = load_file(path)
            if doc is not None:
                documents.append(doc)

    logger.info("Loaded %d document(s) from %s", len(documents), directory)
    return documents
