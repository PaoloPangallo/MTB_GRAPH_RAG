"""Data model for this pilot only. Independent of backend/pipeline/control/contracts.py's
production `CaseContext` (different shape: that one is built from a structured API
request, this one is built by an LLM parser from free clinical text and must carry
literal source spans for every field)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CASE_CONTEXT_SCHEMA_VERSION = "end-to-end-pilot-casecontext/1.0"
QUERY_INTENTS = ("THERAPY_EVALUATION", "THERAPY_DISCOVERY")

MATCH_STATUSES = ("MATCH", "MISMATCH", "UNCERTAIN", "MISSING_IN_TEXT")
MATCH_FIELDS = ("disease", "biomarker", "alteration", "previous_intervention", "target_intervention", "query_intent")

ENRICHMENT_EVIDENCE_KINDS = ("RESPONSE", "BENEFIT", "RESISTANCE", "DIAGNOSTIC", "MECHANISTIC", "OTHER")
ENRICHMENT_OUTCOMES = (
    "ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING", "ENRICHMENT_ABSTAINED",
    "REJECTED_QUOTE", "REJECTED_SOURCE_UNIT", "REJECTED_DOCUMENT", "REJECTED_CONTEXT_MISMATCH",
    "REJECTED_SUMMARY_UNGROUNDED", "REJECTED_SCHEMA", "REJECTED_TRANSPORT",
)


@dataclass
class SourceSpan:
    quote: str
    start_offset: int | None = None
    end_offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BiomarkerContext:
    gene: str | None
    alteration: str | None
    raw_value: str
    normalized_value: str
    source_spans: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"gene": self.gene, "alteration": self.alteration, "raw_value": self.raw_value, "normalized_value": self.normalized_value, "source_spans": self.source_spans}


@dataclass
class FieldContext:
    raw_value: str | None
    normalized_value: str | None
    source_spans: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"raw_value": self.raw_value, "normalized_value": self.normalized_value, "source_spans": self.source_spans}


@dataclass
class CaseContext:
    case_id: str
    disease: dict[str, Any]
    biomarkers: list[dict[str, Any]]
    previous_interventions: list[dict[str, Any]]
    target_intervention: dict[str, Any] | None
    query_intent: str
    clinical_question: str
    uncertainties: list[str] = field(default_factory=list)
    schema_version: str = CASE_CONTEXT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id, "schema_version": self.schema_version,
            "disease": self.disease, "biomarkers": self.biomarkers,
            "previous_interventions": self.previous_interventions,
            "target_intervention": self.target_intervention,
            "query_intent": self.query_intent, "clinical_question": self.clinical_question,
            "uncertainties": self.uncertainties,
        }


def case_context_schema_errors(value: Any) -> list[str]:
    """Structural validation only (shape/enum), no semantic judgement."""
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["NOT_AN_OBJECT"]
    required = {"case_id", "disease", "biomarkers", "previous_interventions", "target_intervention", "query_intent", "clinical_question", "uncertainties"}
    missing = required - set(value)
    if missing:
        errors.append(f"MISSING_KEYS:{sorted(missing)}")
        return errors
    if value["query_intent"] not in QUERY_INTENTS:
        errors.append("QUERY_INTENT_INVALID")
    if value["query_intent"] == "THERAPY_DISCOVERY" and value["target_intervention"] is not None:
        errors.append("THERAPY_DISCOVERY_MUST_HAVE_NULL_TARGET_INTERVENTION")
    if not isinstance(value["biomarkers"], list):
        errors.append("BIOMARKERS_NOT_LIST")
    if not isinstance(value["previous_interventions"], list):
        errors.append("PREVIOUS_INTERVENTIONS_NOT_LIST")
    if not isinstance(value["uncertainties"], list):
        errors.append("UNCERTAINTIES_NOT_LIST")
    return errors


@dataclass
class MatchVerificationRecord:
    field: str
    casecontext_value: str | None
    status: str
    supporting_text: str | None
    start_offset: int | None
    end_offset: int | None
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperContextEnrichment:
    enrichment_id: str
    case_id: str
    candidate_id: str
    paper_id: str
    source_unit_id: str | None
    drug: str
    author_claim_quote: str | None
    author_context_summary: str | None
    evidence_kind: str | None
    abstain: bool
    abstention_reason: str | None
    model: str
    prompt_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
