"""Explicit request/response models for the direct V3 endpoint."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class V3RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    query_id: str
    claim_domain: Literal["therapeutic", "diagnostic", "prognostic", "untyped"] = "untyped"
    gene: str = ""
    alteration: str = ""
    biomarker: str = ""
    disease: str = ""
    interventions: list[str] = Field(default_factory=list)
    intervention_class: str = ""
    intervention_combination: bool = False
    direction: str = ""
    polarity: str = ""
    policy_mode: Literal["strict_verified", "ontology_aware_warning", "audit_all"] = "strict_verified"
    include_warning: bool = True
    include_audit: bool = True
    include_rejected: bool = True
    result_limit: int = Field(default=50, ge=1, le=500)
    limit: int | None = Field(default=None, ge=1, le=500)

    def to_query(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True, by_alias=True)
        if self.limit is not None:
            payload["result_limit"] = self.limit
        payload.pop("limit", None)
        return payload


class PipelineStage(BaseModel):
    id: str
    label: str
    status: str
    input_count: int | None = None
    output_count: int | None = None
    latency_ms: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class GateSummary(BaseModel):
    gate: str
    label: str
    pass_count: int | None = None
    fail_count: int | None = None
    not_applicable_count: int | None = None
    warning_count: int | None = None
    counts_available: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    note: str | None = None


class PipelineObservability(BaseModel):
    stages: list[PipelineStage] = Field(default_factory=list)
    gate_summary: list[GateSummary] = Field(default_factory=list)
    bucket_summary: dict[str, Any] = Field(default_factory=dict)
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    dossier_summary: dict[str, Any] = Field(default_factory=dict)


class V3ClaimProjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_text: str | None = None
    subject: str | None = None
    relation: str | None = None
    object: str | None = None
    biomarker: str | None = None
    disease: str | None = None
    intervention: str | None = None
    direction: str | None = None
    evidence_type: str | None = None
    structured_tuple_complete: bool = False


class V3Decision(BaseModel):
    model_config = ConfigDict(extra="allow")

    bucket: str | None = None
    applicability: str | None = None
    structural_score: float | None = None
    structural_score_eligible: bool | None = None


class V3CaseComparisonValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    query_value_original: Any = None
    query_value_normalized: Any = None
    claim_value: Any = None
    comparison_result: Any = None
    not_applicable_reason: str | None = None
    availability: str | None = None


class V3CaseComparison(BaseModel):
    model_config = ConfigDict(extra="allow")

    biomarker: V3CaseComparisonValue | None = None
    disease: V3CaseComparisonValue | None = None
    intervention: V3CaseComparisonValue | None = None
    formulation: V3CaseComparisonValue | None = None
    direction: V3CaseComparisonValue | None = None
    claim_status: V3CaseComparisonValue | None = None
    domain: V3CaseComparisonValue | None = None


class V3EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim: V3ClaimProjection | None = None
    decision: V3Decision | None = None
    case_comparison: V3CaseComparison | None = None


class V3RetrieveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_context: dict[str, Any]
    summary: dict[str, int]
    evidence: dict[str, list[V3EvidenceRecord]]
    technical_records: dict[str, list[V3EvidenceRecord]]
    abstention: bool
    metadata: dict[str, Any]
    pipeline: PipelineObservability
