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
    disease_stage:      Optional[str] = None
    disease_setting:    Optional[Literal["resected", "locally-advanced", "metastatic"]] = None
    prior_therapies:    list[str] = Field(default_factory=list)
    prior_response:     Optional[str] = None
    ecog_status:        Optional[int] = Field(default=None, ge=0, le=4)
    cns_metastases:     Optional[bool] = None
    co_alterations:     list[str] = Field(default_factory=list)
    jurisdiction:       Optional[str] = None
    mtb_goal:           Optional[Literal[
        "general-review", "treatment-evidence", "resistance", "clinical-trials"
    ]] = None




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
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)
    # Conteggi distinti sui due assi di verifica — non sommati fra loro,
    # né con i conteggi legacy sopra (verified_claims/blocked_claims/review_claims
    # restano derivati dalla sola vista tecnica ClaimCheck).
    source_supported_count: int = 0
    source_uncertain_count: int = 0
    source_unsupported_count: int = 0
    applicability_compatible_count: int = 0
    applicability_indeterminate_count: int = 0
    applicability_not_compatible_count: int = 0
    # Metriche diagnostiche del verificatore (batching + recupero bounded via
    # retry) — puramente tecniche, non cliniche: da non mischiare con i
    # conteggi sopra nel rendering.
    verifier_batches: int = 0
    verifier_failed_batches: int = 0
    verifier_retry_items: int = 0
    verifier_recovered_items: int = 0
    verifier_failed_items: int = 0
    verifier_elapsed_ms: int = 0


class DossierCaseField(BaseModel):
    key: str
    label: str
    value: Optional[str] = None
    confirmed: bool


class DossierEvidence(BaseModel):
    evidence_id: str
    claim: str
    therapy: str
    setting: str
    source_id: Optional[str] = None
    evidence_level: Optional[str] = None
    source_support_status: Literal["supported", "uncertain", "unsupported"]
    source_support_reason: str
    source_population: Optional[str] = None
    source_line: Optional[str] = None
    source_setting: Optional[str] = None
    source_prerequisites: Optional[str] = None
    applicability_status: Literal["compatible", "indeterminate", "not_compatible"]
    applicability_reason: str
    requires_source_review: bool
    requires_clinical_review: bool
    dossier_section: Literal[
        "supported_compatible",
        "supported_indeterminate",
        "supported_not_compatible",
        "review",
        "excluded",
    ]


class DossierFinding(BaseModel):
    title: str
    detail: str
    source_id: Optional[str] = None


class ClinicalDossier(BaseModel):
    case_summary: list[DossierCaseField]
    missing_data: list[str]
    # Vista canonica unica: ogni evidenza compare una sola volta, con
    # entrambi gli assi di verifica e la sezione derivata (dossier_section).
    # Le 5 sezioni cliniche si ottengono raggruppando per quel campo,
    # sia lato backend (report testuale) sia lato frontend (rendering).
    evidence: list[DossierEvidence]
    resistance_findings: list[DossierFinding]
    trial_findings: list[DossierFinding]
    mtb_questions: list[str]


class ArchitectureRun(BaseModel):
    architecture_id: Literal["deterministic", "agentic"]
    title: str
    subtitle: str
    llm_roles: list[str]
    trace: list[TraceStep]
    evidence: list[EvidenceItem]
    report: str
    dossier: ClinicalDossier
    claim_checks: list[ClaimCheck]
    metrics: ArchitectureMetrics
    limitations: list[str]
    run_id: Optional[str] = None
    ledger_valid: Optional[bool] = None
    planning_mode: Optional[str] = None
    fallback_reason: Optional[str] = None
    planner_attempts: Optional[int] = None
    planner_elapsed_ms: Optional[int] = None
    tool_call_timings: list[dict[str, Any]] = Field(default_factory=list)


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
