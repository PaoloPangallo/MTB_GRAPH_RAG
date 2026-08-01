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


class V3RetrieveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_context: dict[str, Any]
    summary: dict[str, int]
    evidence: dict[str, list[dict[str, Any]]]
    technical_records: dict[str, list[dict[str, Any]]]
    abstention: bool
    metadata: dict[str, Any]
