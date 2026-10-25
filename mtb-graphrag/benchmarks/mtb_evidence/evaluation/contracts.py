"""Oggetti immutabili della catena di valutazione.

La catena separa cinque cose che vengono comunemente confuse:

    clinical gold -> snapshot gold -> retrieval -> report strutturato -> report verificato

Ogni passaggio puo' perdere informazione, e la perdita va attribuita al passaggio
giusto. Una fonte clinica assente dal grafo abbassa la copertura del Knowledge
Graph, **non** il recall del retriever: il retriever non puo' recuperare cio' che non
c'e', e contarglielo contro renderebbe la metrica insensibile alla sua vera qualita'.

Tutte le strutture sono `frozen`. Il gold non e' scrivibile da nessun runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# ── Stati di presenza nello snapshot ───────────────────────────────────────────

PRESENT = "present"
PARTIALLY_PRESENT = "partially_present"
ABSENT = "absent"
AMBIGUOUS = "ambiguous"

PRESENCE_STATUSES = (PRESENT, PARTIALLY_PRESENT, ABSENT, AMBIGUOUS)

# ── Stati della loss decomposition ─────────────────────────────────────────────
# Mutuamente esclusivi e collettivamente esaustivi: ogni clinical claim ne riceve
# esattamente uno.

PRESENT_AND_CORRECT = "present_and_correct"
MISSING_FROM_KG = "missing_from_kg"
PARTIALLY_MODELLED_IN_KG = "partially_modelled_in_kg"
MISSED_BY_RETRIEVAL = "missed_by_retrieval"
LOST_IN_REPORT = "lost_in_report"
MISREPRESENTED_IN_REPORT = "misrepresented_in_report"
CITATION_ERROR = "citation_error"
QUALIFIER_OMISSION = "qualifier_omission"
APPLICABILITY_ERROR = "applicability_error"
CORRECTLY_ABSTAINED = "correctly_abstained"
UNRESOLVED = "unresolved"

LOSS_STATES = (
    PRESENT_AND_CORRECT,
    MISSING_FROM_KG,
    PARTIALLY_MODELLED_IN_KG,
    MISSED_BY_RETRIEVAL,
    LOST_IN_REPORT,
    MISREPRESENTED_IN_REPORT,
    CITATION_ERROR,
    QUALIFIER_OMISSION,
    APPLICABILITY_ERROR,
    CORRECTLY_ABSTAINED,
    UNRESOLVED,
)

# ── Stati di revisione di un profilo di fonte ──────────────────────────────────

UNREVIEWED = "unreviewed"
MACHINE_EXTRACTED = "machine_extracted"
HUMAN_REVIEWED = "human_reviewed"
ADJUDICATED = "adjudicated"
FROZEN = "frozen"

REVIEW_STATUSES = (UNREVIEWED, MACHINE_EXTRACTED, HUMAN_REVIEWED, ADJUDICATED, FROZEN)

ARCHITECTURE_DETERMINISTIC = "deterministic"
ARCHITECTURE_AGENTIC = "agentic"

BRANCH_RAW = "raw_records"
BRANCH_FREE = "free_llm_summary"
BRANCH_STRUCTURED = "structured_report_unverified"
BRANCH_VERIFIED = "structured_report_verified"

REPORTING_BRANCHES = (BRANCH_RAW, BRANCH_FREE, BRANCH_STRUCTURED, BRANCH_VERIFIED)


# ── Clinical gold ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClinicalGoldClaim:
    """Cio' che dovrebbe essere ricostruito secondo le fonti primarie.

    Non dipende dal grafo: descrive la letteratura, non lo snapshot.
    """

    claim_id: str
    case_id: str
    subject: str
    relation: str
    object: str
    disease: str
    direction: str
    mandatory_qualifiers: str
    pmid: str
    nct_id: str
    documentary_status: str
    applicability: str
    rationale: str = ""
    prohibited_overclaim: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ClinicalGoldCase:
    case_id: str
    question: str
    case_context: str
    category: str
    gene: str
    variant: str
    disease: str
    required_context: str
    expected_entities: tuple[str, ...]
    expected_claims: tuple[ClinicalGoldClaim, ...]
    expected_sources: tuple[str, ...]
    expected_qualifiers: tuple[str, ...]
    expected_documentary_status: tuple[str, ...]
    expected_applicability: str
    expected_abstention: bool
    expected_human_review: bool
    expected_therapies: tuple[str, ...]
    expected_pmids: tuple[str, ...]
    expected_nct_ids: tuple[str, ...]
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    unnecessary_tools: tuple[str, ...]
    gold_sources: tuple[Mapping[str, Any], ...]
    annotation_status: str
    annotators: tuple[str, ...]
    adjudication: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "question": self.question,
            "case_context": self.case_context,
            "category": self.category,
            "gene": self.gene,
            "variant": self.variant,
            "disease": self.disease,
            "required_context": self.required_context,
            "expected_entities": list(self.expected_entities),
            "expected_claims": [claim.as_dict() for claim in self.expected_claims],
            "expected_sources": list(self.expected_sources),
            "expected_qualifiers": list(self.expected_qualifiers),
            "expected_documentary_status": list(self.expected_documentary_status),
            "expected_applicability": self.expected_applicability,
            "expected_abstention": self.expected_abstention,
            "expected_human_review": self.expected_human_review,
            "expected_therapies": list(self.expected_therapies),
            "expected_pmids": list(self.expected_pmids),
            "expected_nct_ids": list(self.expected_nct_ids),
            "required_tools": list(self.required_tools),
            "optional_tools": list(self.optional_tools),
            "unnecessary_tools": list(self.unnecessary_tools),
            "gold_sources": [dict(source) for source in self.gold_sources],
            "annotation_status": self.annotation_status,
            "annotators": list(self.annotators),
            "adjudication": self.adjudication,
        }


# ── Snapshot gold ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SnapshotGoldClaim:
    """Cio' che di una clinical claim e' presente e raggiungibile nello snapshot."""

    clinical_item_id: str
    case_id: str
    item_kind: str
    presence_status: str
    graph_record_ids: tuple[str, ...] = ()
    graph_source_ids: tuple[str, ...] = ()
    reachable_by_fixed_plan: bool = False
    reachable_by_agentic_tools: bool = False
    missing_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    coverage_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.presence_status not in PRESENCE_STATUSES:
            raise ValueError(
                f"presence_status non ammesso: {self.presence_status!r}. "
                f"Ammessi: {list(PRESENCE_STATUSES)}"
            )

    @property
    def is_retrievable(self) -> bool:
        """Solo cio' che e' presente e raggiungibile puo' essere preteso dal retriever."""
        return self.presence_status in {PRESENT, PARTIALLY_PRESENT} and (
            self.reachable_by_fixed_plan or self.reachable_by_agentic_tools
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "clinical_item_id": self.clinical_item_id,
            "case_id": self.case_id,
            "item_kind": self.item_kind,
            "presence_status": self.presence_status,
            "graph_record_ids": list(self.graph_record_ids),
            "graph_source_ids": list(self.graph_source_ids),
            "reachable_by_fixed_plan": self.reachable_by_fixed_plan,
            "reachable_by_agentic_tools": self.reachable_by_agentic_tools,
            "missing_fields": list(self.missing_fields),
            "conflicting_fields": list(self.conflicting_fields),
            "coverage_notes": list(self.coverage_notes),
            "is_retrievable": self.is_retrievable,
        }


@dataclass(frozen=True)
class SnapshotGoldCase:
    case_id: str
    snapshot_fingerprint: str
    items: tuple[SnapshotGoldClaim, ...]
    retrievable_therapies: tuple[str, ...] = ()
    retrievable_pmids: tuple[str, ...] = ()
    retrievable_nct_ids: tuple[str, ...] = ()
    expected_abstention: bool = False
    notes: tuple[str, ...] = ()

    def by_kind(self, kind: str) -> tuple[SnapshotGoldClaim, ...]:
        return tuple(item for item in self.items if item.item_kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "items": [item.as_dict() for item in self.items],
            "retrievable_therapies": list(self.retrievable_therapies),
            "retrievable_pmids": list(self.retrievable_pmids),
            "retrievable_nct_ids": list(self.retrievable_nct_ids),
            "expected_abstention": self.expected_abstention,
            "notes": list(self.notes),
        }


# ── Profili clinici delle fonti ────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceClinicalProfile:
    """Qualificatori clinici di una fonte, che il grafo non modella.

    Il grafo non rappresenta linea di terapia, setting, stadio, resezione, terapie
    precedenti, popolazione, completezza del regime ne' prerequisiti di biomarcatore.
    Questi profili sono il luogo dove quei qualificatori vivono, e provengono da
    annotazione umana: non vanno generati da un modello.
    """

    source_id: str
    pmid: str = ""
    nct_ids: tuple[str, ...] = ()
    title: str = ""
    disease: str = ""
    population: str = ""
    stage: str = ""
    setting: str = ""
    therapy_line: str = ""
    prior_therapies: tuple[str, ...] = ()
    biomarker_requirements: tuple[str, ...] = ()
    regimen: str = ""
    interventions: tuple[str, ...] = ()
    inclusion_criteria_summary: str = ""
    exclusion_criteria_summary: str = ""
    source_spans: tuple[str, ...] = ()
    extraction_method: str = "human_annotation"
    extractor_version: str = "human_reviewed_v1"
    review_status: str = HUMAN_REVIEWED
    reviewer: str = ""
    confidence: str = "medium"
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.review_status not in REVIEW_STATUSES:
            raise ValueError(
                f"review_status non ammesso: {self.review_status!r}. "
                f"Ammessi: {list(REVIEW_STATUSES)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "pmid": self.pmid,
            "nct_ids": list(self.nct_ids),
            "title": self.title,
            "disease": self.disease,
            "population": self.population,
            "stage": self.stage,
            "setting": self.setting,
            "therapy_line": self.therapy_line,
            "prior_therapies": list(self.prior_therapies),
            "biomarker_requirements": list(self.biomarker_requirements),
            "regimen": self.regimen,
            "interventions": list(self.interventions),
            "inclusion_criteria_summary": self.inclusion_criteria_summary,
            "exclusion_criteria_summary": self.exclusion_criteria_summary,
            "source_spans": list(self.source_spans),
            "extraction_method": self.extraction_method,
            "extractor_version": self.extractor_version,
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


# ── Predizioni ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RetrievalPrediction:
    """Cio' che una run ha effettivamente recuperato dal grafo."""

    case_id: str
    architecture: str
    therapies: tuple[str, ...] = ()
    pmids: tuple[str, ...] = ()
    nct_ids: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    claims: tuple[Mapping[str, Any], ...] = ()
    tools_called: tuple[str, ...] = ()
    planner_calls: int = 0
    abstained: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "architecture": self.architecture,
            "therapies": list(self.therapies),
            "pmids": list(self.pmids),
            "nct_ids": list(self.nct_ids),
            "entities": list(self.entities),
            "record_ids": list(self.record_ids),
            "claims": [dict(claim) for claim in self.claims],
            "tools_called": list(self.tools_called),
            "planner_calls": self.planner_calls,
            "abstained": self.abstained,
        }


@dataclass(frozen=True)
class ReportPrediction:
    """Cio' che un braccio di reporting ha conservato dei record recuperati."""

    case_id: str
    branch: str
    text: str = ""
    claims: tuple[Mapping[str, Any], ...] = ()
    cited_pmids: tuple[str, ...] = ()
    cited_nct_ids: tuple[str, ...] = ()
    mentioned_therapies: tuple[str, ...] = ()
    qualifiers_present: tuple[str, ...] = ()
    abstained: bool = False
    requested_human_review: bool = False
    applicability_by_claim: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "branch": self.branch,
            "text": self.text,
            "claims": [dict(claim) for claim in self.claims],
            "cited_pmids": list(self.cited_pmids),
            "cited_nct_ids": list(self.cited_nct_ids),
            "mentioned_therapies": list(self.mentioned_therapies),
            "qualifiers_present": list(self.qualifiers_present),
            "abstained": self.abstained,
            "requested_human_review": self.requested_human_review,
            "applicability_by_claim": dict(self.applicability_by_claim),
        }


@dataclass(frozen=True)
class ModelRunMetadata:
    """Tutto cio' che serve a riprodurre una run."""

    run_id: str
    case_id: str
    architecture: str
    role_models: Mapping[str, Mapping[str, Any]]
    seed: int | None
    snapshot_fingerprint: str
    prompt_version: str = "v1"
    schema_version: str = "v1"
    started_at: str = ""
    latency_by_stage: Mapping[str, float] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "architecture": self.architecture,
            "role_models": {k: dict(v) for k, v in self.role_models.items()},
            "seed": self.seed,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "started_at": self.started_at,
            "latency_by_stage": dict(self.latency_by_stage),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "errors": list(self.errors),
        }


# ── Esiti della valutazione ────────────────────────────────────────────────────


@dataclass(frozen=True)
class LossDecomposition:
    """Stato finale di una clinical claim lungo la catena."""

    claim_id: str
    case_id: str
    state: str
    stage: str
    explanation: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in LOSS_STATES:
            raise ValueError(
                f"stato non ammesso: {self.state!r}. Ammessi: {list(LOSS_STATES)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "case_id": self.case_id,
            "state": self.state,
            "stage": self.stage,
            "explanation": self.explanation,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class MetricResult:
    """Una metrica con i suoi termini, non solo il valore.

    Numeratore e denominatore restano visibili: su quattro casi un valore come 0.67
    senza il `2/3` che lo genera invita a conclusioni che il campione non regge.
    """

    name: str
    numerator: float
    denominator: float
    covered_items: tuple[str, ...] = ()
    missing_items: tuple[str, ...] = ()
    partial_items: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def value(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "covered_items": list(self.covered_items),
            "missing_items": list(self.missing_items),
            "partial_items": list(self.partial_items),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    category: str
    architecture: str
    metrics: Mapping[str, MetricResult]
    loss: tuple[LossDecomposition, ...] = ()
    run_metadata: ModelRunMetadata | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "architecture": self.architecture,
            "metrics": {name: metric.as_dict() for name, metric in self.metrics.items()},
            "loss_decomposition": [item.as_dict() for item in self.loss],
            "run_metadata": self.run_metadata.as_dict() if self.run_metadata else None,
        }


@dataclass(frozen=True)
class AggregateEvaluation:
    scope: str
    case_count: int
    metrics: Mapping[str, MetricResult]
    by_category: Mapping[str, Mapping[str, MetricResult]] = field(default_factory=dict)
    caveats: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "case_count": self.case_count,
            "metrics": {name: metric.as_dict() for name, metric in self.metrics.items()},
            "by_category": {
                category: {name: metric.as_dict() for name, metric in metrics.items()}
                for category, metrics in self.by_category.items()
            },
            "caveats": list(self.caveats),
        }


def ensure_exhaustive_loss(
    claims: Sequence[str], decomposition: Sequence[LossDecomposition]
) -> None:
    """Verifica che ogni claim riceva esattamente uno stato.

    Gli stati devono essere mutuamente esclusivi e collettivamente esaustivi: se una
    claim ne riceve due, o nessuno, la decomposizione non e' una partizione e le
    somme per stato non tornano.
    """
    seen: dict[str, int] = {}
    for item in decomposition:
        seen[item.claim_id] = seen.get(item.claim_id, 0) + 1
    missing = [claim for claim in claims if claim not in seen]
    duplicated = [claim for claim, count in seen.items() if count > 1]
    extra = [claim for claim in seen if claim not in set(claims)]
    if missing or duplicated or extra:
        raise ValueError(
            "la loss decomposition non e' una partizione delle claim: "
            f"mancanti={missing}, duplicate={duplicated}, estranee={extra}"
        )
