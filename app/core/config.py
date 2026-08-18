from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    reranker_model: str = "BAAI/bge-reranker-base"

    chunk_size: int = 800
    chunk_overlap: int = 120

    top_k: int = 8
    rerank_top_n: int = 4
    score_threshold: float = 0.52
    max_retries: int = 3

    # Week 4: hybrid search + query rewriting
    use_hybrid_search: bool = False
    use_query_rewriting: bool = False
    rrf_k: int = 60
    bm25_top_k: int = 8

    chroma_path: str = str(ROOT_DIR / "storage" / "chroma")
    collection_name: str = "insurance_claims"
    data_raw_dir: str = str(ROOT_DIR / "data" / "raw")

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
