from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Insurance Claims RAG",
    description="RAG over Insurance Claims documents. Answers with citations or 'I don't know'.",
    version="0.1.0",
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"message": "Insurance Claims RAG API. See /docs."}
