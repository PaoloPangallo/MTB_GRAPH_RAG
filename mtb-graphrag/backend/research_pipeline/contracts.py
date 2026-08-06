"""Contratti di run e stage del research runtime verificabile.

Congelati in Fase B: vedi ``docs/verifiable_pipeline/backend_pipeline_contract.md``.

Due scelte meritano una motivazione esplicita.

**Immutabilità.** ``PipelineRun`` e ``PipelineStage`` sono ``frozen``: un
avanzamento produce un nuovo oggetto. La sequenza autorevole degli stati resta
comunque il ledger append-only, e un oggetto mutabile in memoria potrebbe
divergere silenziosamente da esso.

**Validazione nel costruttore.** Le invarianti architetturali — quali stage
possono avere un producer LLM, quali stage non esistono, uno stage saltato deve
dire perché — sono verificate alla costruzione. Una violazione è un difetto di
programmazione, non un dato da rendere: fallire subito impedisce che raggiunga
la UI e venga letta dal relatore come un fatto della pipeline.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

from backend.research_pipeline.execution_mode import (
    ARTIFACT_ORIGINS,
    EXECUTION_MODES,
    NOT_EXECUTED,
    RECORDED_REAL_RUN,
    classify_run_mode,
    summarize,
)

# --- Vocabolari -------------------------------------------------------------

RUN_STATUSES: tuple[str, ...] = (
    "CREATED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "STOPPED",
)

STAGE_STATUSES: tuple[str, ...] = (
    "PENDING", "RUNNING", "SUCCEEDED", "WARNING", "FAILED", "SKIPPED",
)

#: I quattro punti in cui la run termina prima del dossier. Estratti da
#: ``pipeline.py::run_case`` del pilot: non sono un'invenzione di questo modulo.
STOP_REASONS: tuple[str, ...] = (
    "PARSER_TRANSPORT_FAILED",
    "CASECONTEXT_MISMATCH",
    "RETRIEVAL_NO_MATCH",
    "CALL_BUDGET_EXCEEDED",
    # Introdotti con l'esecuzione LIVE degli stage documentali. Sono guasti, non
    # esiti: una run che li riporta non ha una risposta, e non deve poterne
    # mostrare una presa altrove.
    "DOCUMENT_CACHE_UNAVAILABLE",
    "NO_DOCUMENT_RESOLVED",
    "LIVE_STAGE_FAILED",
)

#: ``CASECONTEXT_MISMATCH`` e ``RETRIEVAL_NO_MATCH`` sono esiti corretti: la
#: pipeline si è fermata perché doveva. Non vanno resi come guasti.
CORRECT_STOP_REASONS: frozenset[str] = frozenset({
    "CASECONTEXT_MISMATCH", "RETRIEVAL_NO_MATCH",
})

PRODUCER_KINDS: tuple[str, ...] = ("DETERMINISTIC", "LLM", "HYBRID")

# --- Identità degli stage ---------------------------------------------------

#: ``stage_id -> stage_type``, nell'ordine di esecuzione. L'ordine è parte del
#: contratto: la UI lo usa per la timeline e non deve riordinarlo.
STAGE_TYPES: tuple[tuple[str, str], ...] = (
    ("stage_1_case_input", "CASE_INPUT"),
    ("stage_2_casecontext_parser", "CASECONTEXT_PARSER"),
    ("stage_3_casecontext_match", "CASECONTEXT_MATCH_VERIFIER"),
    ("stage_4_retrieval_plan", "RETRIEVAL_PLAN"),
    ("stage_5_kg_retrieval", "KG_RETRIEVAL"),
    ("stage_6_document_resolution", "DOCUMENT_RESOLUTION"),
    ("stage_7_source_units", "SOURCE_UNIT"),
    ("stage_8_paper_selection", "PAPER_SELECTION"),
    ("stage_9_paper_context_enricher", "PAPER_CONTEXT_ENRICHER"),
    ("stage_10_enrichment_validation", "ENRICHMENT_VALIDATION"),
    ("stage_11_deterministic_gates", "DETERMINISTIC_GATES"),
    ("stage_12_status", "STATUS_CLASSIFICATION"),
    ("stage_13_dossier", "DOSSIER_BUILDER"),
    ("stage_14_narrator", "DOSSIER_NARRATOR"),
    ("stage_15_narrative_verifier", "NARRATIVE_VERIFIER"),
)

STAGE_SEQUENCE: tuple[str, ...] = tuple(stage_id for stage_id, _ in STAGE_TYPES)

_STAGE_TYPE_BY_ID: dict[str, str] = dict(STAGE_TYPES)

#: I soli due stage che un LLM può produrre. Ogni altro stage è deterministico:
#: è ciò che impedisce a Gemma di comparire come autore di gate, status,
#: direction, contraddizione, score o bucket.
LLM_STAGE_IDS: frozenset[str] = frozenset({
    "stage_2_casecontext_parser",
    "stage_9_paper_context_enricher",
})

#: Stage presenti nel contratto ma privi di implementazione. Restano visibili
#: come ``SKIPPED`` permanenti: dichiararli eseguiti sarebbe simulazione.
NOT_IMPLEMENTED_STAGE_IDS: frozenset[str] = frozenset({
    "stage_14_narrator",
    "stage_15_narrative_verifier",
})


def stage_type_for(stage_id: str) -> str:
    """``stage_type`` corrispondente. Solleva ``KeyError`` su id sconosciuti."""
    return _STAGE_TYPE_BY_ID[stage_id]


# --- Producer ---------------------------------------------------------------


@dataclass(frozen=True)
class StageProducer:
    """Chi ha prodotto il risultato di uno stage.

    È il campo che il relatore legge per distinguere un esito calcolato da un
    esito proposto da un modello.
    """

    kind: Literal["DETERMINISTIC", "LLM", "HYBRID"]
    component: str
    version: str
    model: str | None = None
    prompt_version: str | None = None
    transport_version: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in PRODUCER_KINDS:
            raise ValueError(f"producer kind sconosciuto: {self.kind!r}")
        if not self.component:
            raise ValueError("producer senza component")
        if not self.version:
            raise ValueError("producer senza version")

        model_fields = (self.model, self.prompt_version, self.transport_version)
        if self.kind == "DETERMINISTIC" and any(model_fields):
            raise ValueError(
                "un producer DETERMINISTIC non può dichiarare model, prompt_version "
                "o transport_version: nessun modello ha contribuito al risultato"
            )
        if self.kind == "LLM" and (not self.model or not self.prompt_version):
            raise ValueError(
                "un producer LLM deve dichiarare model e prompt_version: senza, "
                "l'output non è attribuibile né riproducibile"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# --- Stage ------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineStage:
    stage_id: str
    stage_type: str
    sequence: int
    status: str
    producer: StageProducer
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    input_preview: Mapping[str, Any] = field(default_factory=dict)
    output_preview: Mapping[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    lineage: Mapping[str, Any] = field(default_factory=dict)
    #: Modalità della run a cui questo stage appartiene.
    execution_mode: str = "LIVE"
    #: Da dove viene il risultato di *questo* stage. Il default è il valore più
    #: cauto: uno stage che non dichiara la propria origine non è stato eseguito.
    artifact_origin: str = NOT_EXECUTED

    def __post_init__(self) -> None:
        if self.stage_id not in _STAGE_TYPE_BY_ID:
            raise ValueError(f"stage_id sconosciuto: {self.stage_id!r}")
        if self.execution_mode not in EXECUTION_MODES:
            raise ValueError(f"execution_mode sconosciuto: {self.execution_mode!r}")
        if self.artifact_origin not in ARTIFACT_ORIGINS:
            raise ValueError(f"artifact_origin sconosciuto: {self.artifact_origin!r}")
        if self.execution_mode == "LIVE" and self.artifact_origin == RECORDED_REAL_RUN:
            raise ValueError(
                f"{self.stage_id}: uno stage che rigioca un artefatto registrato non "
                "può dichiararsi LIVE. La run va classificata HYBRID."
            )
        if self.stage_type != _STAGE_TYPE_BY_ID[self.stage_id]:
            raise ValueError(
                f"stage_type {self.stage_type!r} non corrisponde a {self.stage_id!r}"
            )
        if self.status not in STAGE_STATUSES:
            raise ValueError(f"stage status sconosciuto: {self.status!r}")

        if self.producer.kind == "LLM" and self.stage_id not in LLM_STAGE_IDS:
            raise ValueError(
                f"{self.stage_id} non può avere un producer LLM: solo "
                f"{sorted(LLM_STAGE_IDS)} sono prodotti da un modello. "
                "Gli stage deterministici non possono essere attribuiti a Gemma."
            )

        if self.stage_id in NOT_IMPLEMENTED_STAGE_IDS and self.status != "SKIPPED":
            raise ValueError(
                f"{self.stage_id} non è implementato e può solo essere SKIPPED: "
                "dichiararlo eseguito sarebbe simulazione"
            )

        if self.status == "SKIPPED" and not self.reason_codes:
            raise ValueError(
                f"{self.stage_id} è SKIPPED senza reason code: uno stage saltato "
                "senza spiegazione è indistinguibile da un difetto"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_type": self.stage_type,
            "sequence": self.sequence,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "input_preview": dict(self.input_preview),
            "output_preview": dict(self.output_preview),
            "reason_codes": list(self.reason_codes),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "producer": self.producer.to_dict(),
            "metrics": dict(self.metrics),
            "lineage": dict(self.lineage),
            "execution_mode": self.execution_mode,
            "artifact_origin": self.artifact_origin,
        }


# --- Run --------------------------------------------------------------------


@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    case_id: str
    status: str
    started_at: str
    input_text: str
    completed_at: str | None = None
    current_stage: str | None = None
    stopped_at: str | None = None
    stages: tuple[PipelineStage, ...] = ()
    dossier_id: str | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    versions: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    #: Modalità **richiesta** all'avvio. Quella effettiva è derivata dagli stage.
    requested_mode: str = "LIVE"
    document_cache: Mapping[str, Any] = field(default_factory=dict)
    llm_calls: int = 0

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise ValueError(f"run status sconosciuto: {self.status!r}")
        if self.stopped_at is not None and self.stopped_at not in STOP_REASONS:
            raise ValueError(f"stop reason sconosciuta: {self.stopped_at!r}")
        if self.requested_mode not in EXECUTION_MODES:
            raise ValueError(f"requested_mode sconosciuto: {self.requested_mode!r}")

    @property
    def execution_mode(self) -> str:
        """Modalità **effettiva**, dedotta dalle origini degli stage.

        Non è un campo memorizzabile: se lo fosse, potrebbe divergere dagli stage
        che dovrebbe riassumere. Un solo artefatto registrato in una run avviata
        LIVE la rende HYBRID, e non c'è modo di sovrascriverlo.
        """
        return classify_run_mode(self.requested_mode, (s.artifact_origin for s in self.stages))

    def mode_summary(self) -> dict[str, Any]:
        return summarize(self.requested_mode, [s.artifact_origin for s in self.stages])

    def with_status(self, status: str, **changes: Any) -> "PipelineRun":
        """Nuova run con lo stato aggiornato. L'originale resta invariata."""
        return replace(self, status=status, **changes)

    def with_stage(self, stage: PipelineStage) -> "PipelineRun":
        """Nuova run con lo stage aggiunto o sostituito a parità di ``stage_id``."""
        kept = tuple(s for s in self.stages if s.stage_id != stage.stage_id)
        ordered = sorted((*kept, stage), key=lambda s: s.sequence)
        return replace(self, stages=ordered)

    @staticmethod
    def research_notice() -> dict[str, Any]:
        """Marcatura non disattivabile, presente in ogni risposta di run.

        Il pilot ha dimostrato meccanica e sicurezza architetturale su un
        campione minuscolo, non resa clinica: la distinzione deve restare
        leggibile ovunque il risultato venga mostrato.
        """
        return {
            "runtime": "VERIFIABLE_RESEARCH_RUNTIME",
            "clinically_validated": False,
            "not_for_clinical_decision_making": True,
            "experimental_component": True,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_stage": self.current_stage,
            "stopped_at": self.stopped_at,
            "input_text": self.input_text,
            "stages": [stage.to_dict() for stage in self.stages],
            "dossier_id": self.dossier_id,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "versions": dict(self.versions),
            "metrics": dict(self.metrics),
            "research_notice": self.research_notice(),
            "document_cache": dict(self.document_cache),
            "llm_calls": self.llm_calls,
            **self.mode_summary(),
        }
