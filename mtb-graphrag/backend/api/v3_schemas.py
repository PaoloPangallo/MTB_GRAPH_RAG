"""
Schemi Pydantic per le API V3 di Retrieval e Rendering.
Non usa dict[str, Any] come contratto principale: tutti i campi del retriever nativo
sono esposti con i loro tipi e nomi originali.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class V3RetrievalRequest(BaseModel):
    """Richiesta di retrieval V3."""

    domain: str = Field(
        default="therapeutic",
        description="Dominio della claim: therapeutic, diagnostic, prognostic, untyped",
    )
    biomarker: str = Field(
        ...,
        description="Biomarcatore (variante singola o espressione booleana AND/OR)",
        example="EGFR L858R",
    )
    disease: str = Field(
        ...,
        description="Malattia / indicazione clinica",
        example="Non-Small Cell Lung Cancer",
    )
    intervention: str | None = Field(
        default=None,
        description="Intervento / farmaco opzionale",
        example="Osimertinib",
    )
    policy_mode: str = Field(
        default="strict_verified",
        description="Policy mode del gate V3: strict_verified, ontology_aware_warning, audit_all",
    )
    result_limit: int | None = Field(
        default=None,
        description="Limite di rendering per bucket (opzionale)",
    )
    query_id: str | None = Field(
        default=None,
        description="Identificatore della query",
    )
    include_warning: bool = Field(default=True)
    include_audit: bool = Field(default=True)
    include_rejected: bool = Field(default=True)


class V3MetadataResponse(BaseModel):
    """Metadati sullo stato e sulle versioni del backend V3."""

    backend_identifier: str = Field(default="qualified_claim_v3")
    corpus_version: str = Field(default="qualified_claim_repository/1.4")
    corpus_digest: str = Field(default="")
    gate_version: str = Field(default="qualified_claim_structural_gate/1.3")
    scoring_version: str = Field(default="v3_operational_scoring/1.0")
    retriever_version: str = Field(default="qualified_claim_retriever/1.0")
    rendering_model_identifier: str = Field(default="google/gemma-2-9b-it")
    rendering_enabled: bool = Field(default=True)
    service_status: str = Field(default="healthy")
    promoted_at: str = Field(default="")
    policy_mode: str = Field(default="strict_verified")


class V3BucketSummary(BaseModel):
    """Conteggio candidati esaminati e suddivisi nei 4 bucket."""

    total: int = Field(default=0)
    primary: int = Field(default=0)
    warning: int = Field(default=0)
    audit: int = Field(default=0)
    rejected: int = Field(default=0)


class V3ClaimResult(BaseModel):
    """Singola claim qualificata e classificata in un bucket."""

    claim_id: str = Field(...)
    parent_id: str = Field(default="")
    graph_evidence_id: str = Field(default="")
    claim_domain: str = Field(default="therapeutic")
    claim_type: str = Field(default="therapeutic_responsiveness_claim")
    bucket: str = Field(default="primary")
    section: str = Field(default="")
    rank: int = Field(default=0)
    biomarker: str = Field(default="")
    disease_scope: str = Field(default="")
    canonical_intervention: str = Field(default="")
    intervention_members: list[str] = Field(default_factory=list)
    source_literal_members: list[str] = Field(default_factory=list)
    gate: dict[str, Any] = Field(default_factory=dict)
    score: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    explanation_codes: list[str] = Field(default_factory=list)
    gate_trace: Any = Field(default=None)
    schema_version: str = Field(default="qualified_claim_result/1.4")


class V3Metadata(BaseModel):
    """Metadati runtime e di osservabilità restituiti nella risposta."""

    corpus_version: str = Field(default="qualified_claim_repository/1.4")
    corpus_digest: str = Field(default="")
    gate_version: str = Field(default="qualified_claim_structural_gate/1.3")
    retriever_version: str = Field(default="qualified_claim_retriever/1.0")
    run_id: str = Field(default="")
    policy_mode: str = Field(default="strict_verified")
    elapsed_ms: int = Field(default=0)
    latency_ms: dict[str, int] = Field(default_factory=dict)
    gate_decisions: dict[str, Any] = Field(default_factory=dict)


class V3RetrievalResponse(BaseModel):
    """Risposta del retrieval V3 reale."""

    query_id: str = Field(default="")
    query: dict[str, Any] = Field(default_factory=dict)
    summary: V3BucketSummary = Field(default_factory=V3BucketSummary)
    buckets: dict[str, list[V3ClaimResult]] = Field(
        default_factory=lambda: {
            "primary": [],
            "warning": [],
            "audit": [],
            "rejected": [],
        }
    )
    metadata: V3Metadata = Field(default_factory=V3Metadata)
    warnings: list[str] = Field(default_factory=list)


class V3RenderRequest(BaseModel):
    """Richiesta di rendering narrativo opzionale."""

    query_id: str = Field(default="")
    claims: list[V3ClaimResult] = Field(
        ...,
        description="Elenco di claim strutturate provenienti dal retrieval V3",
    )
    include_disclaimer: bool = Field(default=True)


class V3RenderResponse(BaseModel):
    """Risposta del rendering narrativo opzionale."""

    query_id: str = Field(default="")
    rendered_report: str = Field(..., description="Testo del report narrativo generato")
    claim_ids_used: list[str] = Field(default_factory=list)
    cited_pmids: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default="Il modello genera il testo dalle claim già qualificate. Non determina retrieval, bucket o ranking."
    )
    model_identifier: str = Field(default="google/gemma-2-9b-it")
