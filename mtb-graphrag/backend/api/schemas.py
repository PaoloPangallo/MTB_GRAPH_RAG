"""
Pydantic I/O models — Contratto tra frontend e backend.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class MTBRequest(BaseModel):
    """Input della pipeline MTB."""
    gene:               Optional[str] = None    # HUGO symbol (null per biomarker)
    variant:            str                      # protein change, Fusion, MSI-High
    tumor_type:         str                      # nome tumore o codice OncoTree
    alteration_type:    Literal[
        "point_mutation", "fusion", "cna", "itd", "atypical", "biomarker"
    ]
    therapy_line:       str = "first-line"       # first-line | second-line | later-line
    enrich_with_oncokb: bool = False             # attiva OncoKB Enricher
    report:             Optional[str] = None     # report base da arricchire
    driver_variant:     Optional[str] = None     # variante driver originale da cui si è sviluppata la resistenza




class ReportResponse(BaseModel):
    """Output della pipeline MTB."""
    complexity:         str
    escat_tier:         str
    report:             str
    cited_pmids:        list[int]
    drug_candidates:    list[dict[str, Any]]
    resistance_data:    list[dict[str, Any]]
    trial_candidates:   list[dict[str, Any]]
    oncokb_enrichment:  Optional[list[dict[str, Any]]] = None


class JudgeRequest(BaseModel):
    """Input per la valutazione LLM-as-judge."""
    report:     str
    gene:       Optional[str] = None
    variant:    str
    tumor_type: str


class JudgeResponse(BaseModel):
    """Output della valutazione LLM-as-judge."""
    completezza:         Optional[float] = None
    utilita_clinica:     Optional[float] = None
    fedelta_evidenze:    Optional[float] = None
    accuratezza_clinica: Optional[float] = None
    score_totale:        Optional[float] = None
    motivazione:         Optional[str] = None
    raw_response:        Optional[str] = None
    error:               Optional[str] = None


class ArchitectureComparisonRequest(MTBRequest):
    """Caso condiviso dalle due architetture nella vista comparativa."""
    execution_mode: Literal["demo", "live"] = "demo"


class TraceStep(BaseModel):
    order: int
    stage: str
    actor: str
    detail: str
    status: Literal["completed", "warning", "blocked"] = "completed"


class EvidenceItem(BaseModel):
    subject: str
    relation: str
    object: str
    context: str
    source_id: Optional[str] = None
    provenance: str
    evidence_statement: Optional[str] = None
    citation_text: Optional[str] = None
    evidence_level: Optional[str] = None


class ClaimCheck(BaseModel):
    claim: str
    status: Literal["supported", "insufficient", "blocked", "not_checked"]
    reason: str
    source_id: Optional[str] = None
    verification_level: Optional[str] = None
    requires_human_review: bool = False


class ArchitectureMetrics(BaseModel):
    elapsed_ms: int
    tool_calls: int
    evidence_count: int
    verified_claims: int
    blocked_claims: int
    review_claims: int = 0
    ledger_events: int = 0


class ArchitectureRun(BaseModel):
    architecture_id: Literal["deterministic", "agentic"]
    title: str
    subtitle: str
    llm_roles: list[str]
    trace: list[TraceStep]
    evidence: list[EvidenceItem]
    report: str
    claim_checks: list[ClaimCheck]
    metrics: ArchitectureMetrics
    limitations: list[str]
    run_id: Optional[str] = None
    ledger_valid: Optional[bool] = None
    planning_mode: Optional[str] = None


class ComparisonSummary(BaseModel):
    shared_sources: list[str]
    deterministic_only_sources: list[str]
    agentic_only_sources: list[str]
    explanation: str


class ArchitectureComparisonResponse(BaseModel):
    execution_mode: Literal["demo", "live"]
    case_label: str
    disclaimer: str
    deterministic: ArchitectureRun
    agentic: ArchitectureRun
    summary: ComparisonSummary
