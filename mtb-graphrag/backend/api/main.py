"""
FastAPI app — entry point per il backend MTB GraphRAG.
Avvio: uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(
    title="MTB GraphRAG API",
    description="Pipeline Agentica GraphRAG per Molecular Tumor Board",
    version="3.0.0",
)

# CORS — permetti il frontend locale
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
