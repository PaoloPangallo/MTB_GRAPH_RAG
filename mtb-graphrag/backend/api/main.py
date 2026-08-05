"""
FastAPI app — entry point per il backend MTB GraphRAG.
Avvio: uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(
    title="MTB GraphRAG API",
    description="Pipeline Agentica GraphRAG per Molecular Tumor Board",
    version="3.0.0",
)

# CORS — origini esplicite, configurabili da .env/ambiente
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

# Research runtime verificabile — namespace separato, disattivo di default.
# Il router è sempre montato ma ogni rotta risponde 404 finché
# VERIFIABLE_PIPELINE_RESEARCH_ENABLED non è attivo: montarlo condizionalmente
# renderebbe il flag leggibile dalla forma di OpenAPI, e comunque impedirebbe di
# attivarlo senza riavviare il processo.
from backend.api.research_routes import router as research_router  # noqa: E402

app.include_router(research_router, prefix="/api/v1/research/pipeline")


@app.get("/health")
def health():
    return {"status": "ok"}
