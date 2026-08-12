"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload
Then open: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Week 3 AI POC — Insurance Claims RAG",
    description="Retrieval-Augmented Generation over an Insurance Claims corpus. "
    "Answers come only from the policy documents, with citations, or 'I don't know'.",
    version="0.1.0",
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"message": "Week 3 AI POC. See /docs for the API."}
