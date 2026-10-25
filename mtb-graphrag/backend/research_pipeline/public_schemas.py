"""Public research API schemas; extension data is retained for historical ledgers.

Known evidence states are closed vocabularies. Provider metadata, audit fields,
and stage previews stay extensible because their shape depends on the producer.
Use ``exclude_unset=True`` when serializing to preserve legacy field absence.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import RUN_STATUSES, STAGE_STATUSES, STOP_REASONS

RunStatus = Literal[*RUN_STATUSES]
DossierStatus = Literal[*RUN_STATUSES, "INSUFFICIENT_CASE_CONTEXT", "NEEDS_CLARIFICATION", "NO_RELEVANT_KG_EVIDENCE"]
StageStatus = Literal[*STAGE_STATUSES]
StopReason = Literal[*STOP_REASONS]
SupportLevel = Literal["FULL_SUPPORT", "PARTIAL_SUPPORT", "NO_SUPPORT", "CONTRADICTORY",
                       "UNVERIFIABLE", "INSUFFICIENT_INFORMATION"]
SupportFieldState = Literal["CONFIRMED", "NOT_CONFIRMED", "CONTRADICTORY", "NOT_APPLICABLE", "UNKNOWN", "OPPOSITE"]
RelationFamily = Literal["PAPER_EVIDENCE", "CLINICAL_TRIAL", "KG_ONLY"]
ExecutionMode = Literal["LIVE", "REPLAY", "HYBRID"]
ArtifactOrigin = Literal["GENERATED_NOW", "RECORDED_REAL_RUN", "DETERMINISTIC_CACHE", "NOT_APPLICABLE", "NOT_EXECUTED"]


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class GraphEntity(PublicModel):
    id: str | None = None
    label: str | None = None
    type: str | None = None


class CaseSummary(PublicModel):
    case_id: str | None = None
    disease: str | None = None
    gene: str | None = None
    variant: str | None = None
    intervention: str | None = None
    intent: str | None = None
    molecular_resolution: list[dict[str, Any]] | None = None


class RetrievalSummary(PublicModel):
    total_candidates: int | None = Field(default=None, ge=0)
    paper_candidates: int | None = Field(default=None, ge=0)
    trial_candidates: int | None = Field(default=None, ge=0)
    kg_only_candidates: int | None = Field(default=None, ge=0)
    selected_total: int | None = Field(default=None, ge=0)
    per_family_counts: dict[str, int] | None = None
    snapshot_metadata: dict[str, Any] | None = None


class GraphProvenance(PublicModel):
    node_ids: list[str] | None = None
    edge_ids: list[str] | None = None
    graph_path: list[Any] | None = None
    materialization_rule_id: str | None = None


class SupportPredicates(PublicModel):
    observation_valid: bool | None = None
    relation_anchored: bool | None = None
    relation_compatible: bool | None = None
    relation_full_specificity: bool | None = None


class CandidateSupport(PublicModel):
    """Deterministic support result and the dimensions behind the decision."""
    fields: dict[str, SupportFieldState] | None = None
    applicable: list[str] | None = None
    central: list[str] | None = None
    required: list[str] | None = None
    predicates: SupportPredicates | None = None
    disease_policy: Literal["REQUIRED", "OPTIONAL", "NOT_APPLICABLE"] | None = None
    policy_version: str | None = None
    relation_assertion: str | None = None
    text_assertion: str | None = None
    text_assertion_reason: str | None = None
    relation_text_state: str | None = None
    reason: str | None = None
    result: SupportLevel | None = None


class EvidenceRecord(PublicModel):
    model_config = ConfigDict(extra="allow", strict=True, json_schema_extra={"x-provenance-rule": "evidence"})
    evidence_id: str | None = None
    paper_id: str | None = None
    document_id: str | None = None
    public_source_identity: str | None = None
    source_unit_id: str | None = None
    quote: str | None = None
    author_claim_quote: str | None = None
    quote_valid: bool | None = None
    presentation_state: Literal["VALIDATED_QUOTE", "REJECTED_QUOTE", "ABSTAINED", "PROPOSED_QUOTE_NOT_VALIDATED"] | None = None
    support_level: SupportLevel | None = None
    candidate_support: CandidateSupport | None = None
    document_verification: dict[str, Any] | None = None
    validation_outcome: str | None = None
    reason_codes: list[str] | None = None
    observed_relation: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validated_quote_has_provenance(self):
        if (self.quote_valid is True or self.presentation_state == "VALIDATED_QUOTE") and (self.quote or self.author_claim_quote):
            if not (self.document_id or self.paper_id):
                raise ValueError("validated quote requires document_id or paper_id")
            if not self.source_unit_id:
                raise ValueError("validated quote requires source_unit_id")
        return self


class GeneVariantPair(PublicModel):
    gene: str
    alteration: str


class Claim(PublicModel):
    claim_id: str
    candidate_id: str | None = None
    relation_family: RelationFamily | None = None
    status: SupportLevel | Literal["KG_ONLY", "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"] | None = None
    relation: str | None = None
    subject: GraphEntity | None = None
    object: GraphEntity | None = None
    representative_evidence_id: str | None = None
    supporting_evidence_ids: list[str] | None = None
    partial_evidence_ids: list[str] | None = None
    contradicting_evidence_ids: list[str] | None = None
    rejected_evidence_ids: list[str] | None = None
    source_record_ids: list[str] | None = None
    source_datasets: list[str] | None = None
    document_ids: list[str] | None = None
    source_unit_ids: list[str] | None = None
    quotes: list[str] | None = None
    gene_variant_pairings: list[GeneVariantPair] | None = None
    caveats: list[str] | None = None
    uncertainty: list[str] | None = None
    conflict_markers: list[str] | None = None


class RelationEntry(PublicModel):
    candidate_id: str
    subject: GraphEntity | None = None
    object: GraphEntity | None = None
    relation: str | None = None
    direction: str | None = None
    evidence_type: str | None = None
    disease_context: list[str] | None = None
    graph_provenance: GraphProvenance | None = None
    claim_id: str | None = None
    claim: Claim | None = None
    declared_source_identity: str | None = None
    resolved_source_identity: str | None = None


class DocumentaryFinding(PublicModel):
    evidence_id: str | None = None
    candidate_id: str | None = None
    relation_family: str | None = None
    requested_target: dict[str, Any] | None = None
    disposition: Literal["RETAINED_RECORD", "EXCLUDED_RECORD"]
    source: dict[str, Any]
    quotation: str | None = None
    observed: dict[str, Any]
    observed_origin: Literal["READER_EXTRACTION_NOT_INDEPENDENT_GOLD"]
    checks: dict[str, Any]
    limitations: dict[str, Any]
    scientific_correctness: Literal["NOT_INDEPENDENTLY_EVALUATED"]
    clinical_applicability: Literal["NOT_EVALUATED"]
    legacy_classification: dict[str, Any] | None = None


class PaperEvidence(RelationEntry):
    model_config = ConfigDict(extra="allow", strict=True, json_schema_extra={"x-provenance-rule": "paper"})
    relation_family: Literal["PAPER_EVIDENCE"] | None = None
    document_id: str | None = None
    pmcid: str | None = None
    document_resolution_status: str | None = None
    selected_source_units: list[str] | None = None
    selected_source_unit_ids: list[str] | None = None
    reader_status: Literal["QUOTE", "ABSTAIN"] | None = None
    reader_decision: Literal["QUOTE", "ABSTAIN"] | None = None
    quote: str | None = None
    quote_source_unit_id: str | None = None
    quote_valid: bool | None = None
    quote_validation: str | None = None
    support_level: SupportLevel | None = None
    # Historical baseline support_status is deliberately separate from support_level.
    support_status: str | None = None
    support_fields: dict[str, SupportFieldState] | None = None
    support_reason: str | None = None
    evidence_records: list[EvidenceRecord] | None = None
    accepted_evidence_records: list[EvidenceRecord] | None = None
    rejected_evidence: list[EvidenceRecord] | None = None
    accepted_evidence_ids: list[str] | None = None
    full_evidence_ids: list[str] | None = None
    partial_evidence_ids: list[str] | None = None
    contradicting_evidence_ids: list[str] | None = None
    contradiction_present: bool | None = None
    documentary_target: dict[str, Any] | None = None
    documentary_findings: list[DocumentaryFinding] | None = None
    documentary_attempts: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def validated_quote_has_provenance(self):
        if self.quote_valid is True and self.quote:
            if not self.document_id:
                raise ValueError("validated quote requires document_id")
            if not self.quote_source_unit_id:
                raise ValueError("validated quote requires quote_source_unit_id")
            selected = self.selected_source_unit_ids or self.selected_source_units
            if selected and self.quote_source_unit_id not in selected:
                raise ValueError("validated quote must reference a selected source unit")
        return self


class ClinicalTrial(RelationEntry):
    relation_family: Literal["CLINICAL_TRIAL"] | None = None
    nct_id: str | None = None
    declared_nct_id: str | None = None
    resolved_nct_id: str | None = None
    title: str | None = None
    status: str | None = None
    phase: str | list[str] | None = None
    conditions: list[Any] | None = None
    interventions: list[Any] | None = None
    arm_groups: list[dict[str, Any]] | None = None
    arm_group_status: str | None = None
    trial_structure_provenance: dict[str, Any] | None = None
    biomarker_gene: str | list[str] | None = None
    source: str | None = None
    provenance_status: str | None = None
    eligibility_status: str | None = None
    trial_resolution_status: str | None = None
    evidence_interpretation: Literal["TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"] | None = None
    reader_attempts: list[EvidenceRecord] | None = None


class KGOnlyRelation(RelationEntry):
    relation_family: Literal["KG_ONLY"] | None = None
    document_id: None = None
    source_database: str | None = None
    verification_status: Literal["KG_ONLY"] | None = None
    document_provenance: Literal["NOT_AVAILABLE"] | None = None
    diagnostic_scope: str | None = None


class ProvenanceSummary(PublicModel):
    candidate_ids: list[str] | None = None
    paper_document_ids: list[str] | None = None
    trial_ids: list[str] | None = None
    graph_only_candidate_ids: list[str] | None = None


class ReadingNotice(PublicModel):
    code: str
    message: str


class ReadingFinding(PublicModel):
    paper_index: int = Field(ge=0)
    finding_index: int = Field(ge=0)
    candidate_id: str | None = None
    evidence_id: str | None = None
    requested_disease: str | None = None
    observed_disease: str | None = None
    requested_intervention: str | None = None
    observed_intervention: str | None = None
    disease_text_comparison: Literal['SAME_RECORDED_TEXT', 'DIFFERENT_RECORDED_TEXT', 'NOT_RECORDED']
    intervention_text_comparison: Literal['SAME_RECORDED_TEXT', 'DIFFERENT_RECORDED_TEXT', 'NOT_RECORDED']
    notices: list[ReadingNotice]


class ReadingTrialGroup(PublicModel):
    nct_id: str | None = None
    entry_indexes: list[int]
    snapshot_indexes: list[int]
    conflicting_snapshots: bool


class DossierReadingGuide(PublicModel):
    version: Literal['dossier-reading/1.0']
    clinical_applicability: Literal['NOT_EVALUATED']
    verification_note: str
    findings: list[ReadingFinding]
    trial_groups: list[ReadingTrialGroup]
    trial_association_count: int = Field(ge=0)
    identified_study_count: int = Field(ge=0)
    unidentified_trial_association_count: int = Field(ge=0)


class CanonicalDossier(PublicModel):
    run_status: DossierStatus
    case_summary: CaseSummary
    retrieval_summary: RetrievalSummary
    paper_evidence: list[PaperEvidence]
    clinical_trials: list[ClinicalTrial]
    kg_only_relations: list[KGOnlyRelation]
    limitations: list[str]
    # Older archived reports predate the explicit summary and claim aggregation.
    provenance_summary: ProvenanceSummary | None = None
    claims: list[Claim] | None = None
    aggregation_reconciliation: dict[str, int] | None = None
    pipeline_accounting: dict[str, Any] | None = None
    documentary_contract_version: Literal["documentary-findings/1.0", "documentary-findings/1.1"] | None = None
    documentary_summary: dict[str, Any] | None = None


class StageProducer(PublicModel):
    kind: Literal["DETERMINISTIC", "LLM", "HYBRID"]
    component: str
    version: str
    model: str | None = None
    prompt_version: str | None = None
    transport_version: str | None = None


class PublicPipelineStage(PublicModel):
    stage_id: str
    stage_type: str
    sequence: int = Field(ge=0)
    status: StageStatus
    producer: StageProducer
    input_preview: dict[str, Any] | None = None
    output_preview: dict[str, Any] | None = None
    reason_codes: list[str] | None = None
    warnings: list[str] | None = None
    errors: list[str] | None = None
    metrics: dict[str, Any] | None = None
    lineage: dict[str, Any] | None = None
    execution_mode: ExecutionMode | None = None
    artifact_origin: ArtifactOrigin | None = None


class PublicPipelineRun(PublicModel):
    run_id: str
    case_id: str
    status: RunStatus
    stages: list[PublicPipelineStage]
    stopped_at: StopReason | None = None
    relation_aware_report: CanonicalDossier | None = None
    execution_mode: ExecutionMode | None = None
    requested_mode: ExecutionMode | None = None


class PublicEvent(PublicModel):
    event_id: str
    sequence: int = Field(ge=1)
    event_type: str
    created_at: str
    actor: str
    stage_id: str | None = None
    stage_type: str | None = None
    producer: StageProducer | None = None
    payload_hash: str | None = None
    # Event-specific producer artifacts are open data, not canonical dossier states.
    payload: dict[str, Any]


class EventPage(PublicModel):
    run_id: str
    append_only: bool
    hash_chain_valid: bool
    events: list[PublicEvent]
    next_after_sequence: int = Field(ge=0)
    has_more: bool


class CreatedRunResponse(PublicModel):
    run_id: str
    case_id: str
    status: RunStatus
    execution_mode: ExecutionMode
    stream_url: str
    research_notice: dict[str, Any]


class StageResponse(PublicModel):
    stage: PublicPipelineStage
    run_id: str | None = None
    events: list[PublicEvent] | None = None


class TraceDocument(PublicModel):
    document_id: str
    source_unit_id: str
    validated_quote: str
    quote_valid: bool
    document_resolution_status: str
    quote_validation: str | dict[str, Any]


class TraceSupport(PublicModel):
    support_level: SupportLevel | Literal[""]
    support_status: str
    support_reason: str
    support_fields: dict[str, SupportFieldState]
    reader_decision: str
    reader_status: str
    reason: str


class PaperTrace(PublicModel):
    candidate_id: str
    branch: Literal["PAPER"]
    relation: str
    document: TraceDocument
    support: TraceSupport
    graph_provenance: GraphProvenance


class TraceTrialRecord(PublicModel):
    nct_id: str | None = None
    title: str | None = None
    conditions: list[Any] | None = None
    interventions: list[Any] | None = None
    phase: str | list[str] | None = None
    status: str | None = None
    trial_resolution_status: str | None = None
    eligibility_status: str | None = None
    evidence_interpretation: Literal["TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"] | None = None
    provenance_status: str | None = None
    source: str | None = None


class TrialTrace(PublicModel):
    candidate_id: str
    branch: Literal["TRIAL"]
    relation: str
    trial: TraceTrialRecord
    graph_provenance: GraphProvenance


class KGTrace(PublicModel):
    candidate_id: str
    branch: Literal["KG_ONLY"]
    graph: dict[str, Any]
    graph_provenance: GraphProvenance


class NarrativeTrace(PublicModel):
    contract_version: str
    case_id: str
    candidates: list[PaperTrace | TrialTrace | KGTrace]
    trace_hash: str


class LegacyDossier(PublicModel):
    """An archived pre-canonical dossier must not swallow malformed canonical data."""
    model_config = ConfigDict(extra="allow", strict=True, json_schema_extra={"x-legacy-dossier": True})

    @model_validator(mode="before")
    @classmethod
    def exclude_canonical_payload(cls, value):
        if isinstance(value, dict) and any(key in value for key in ("run_status", "paper_evidence", "clinical_trials", "kg_only_relations")):
            raise ValueError("canonical dossier fields require the canonical contract")
        return value


class DossierResponse(PublicModel):
    run_id: str
    dossier: CanonicalDossier | LegacyDossier
    reading_guide: DossierReadingGuide | None = None
    status: RunStatus
    technical_run_status: RunStatus | None = None
    publication_status: Literal["COMPLETE", "INCOMPLETE"] | None = None
    dossier_markdown: str | None = None
    candidate_count: int | None = None
    narrative: dict[str, Any] | None = None
    narrative_trace: NarrativeTrace | None = None
    presentation: dict[str, Any] | None = None
    presentation_mode: Literal["STRUCTURED_DOSSIER_FALLBACK", "VERIFIED_NARRATIVE", "DETERMINISTIC_NARRATIVE_FALLBACK"] | None = None
    narrative_verification: dict[str, Any] | None = None


PUBLIC_MODELS = (CanonicalDossier, PublicPipelineRun, EventPage, PublicEvent, CreatedRunResponse, StageResponse, DossierResponse)
