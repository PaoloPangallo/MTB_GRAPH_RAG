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
from typing import Any, Iterable, Literal, Mapping

from backend.research_pipeline.eligibility.gate import (
    ELIGIBILITY_STATES,
    ELIGIBLE_FOR_RETRIEVAL,
)
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

#: Esiti del Pre-Retrieval Eligibility Gate che terminano la run.
#:
#: Devono comparire in ``STOP_REASONS``: ``orchestrator.run_case`` li passa a
#: ``_finalize`` come ``stopped_at``, e senza di essi ``PipelineRun.__post_init__``
#: sollevava ``ValueError``. Un input fuori dominio, non azionabile, contraddittorio
#: o avversariale terminava così con un guasto software invece che con lo stop
#: controllato che la policy aveva correttamente deciso.
#:
#: Sono importati da ``eligibility.gate`` invece di essere riscritti: due elenchi
#: paralleli divergerebbero al primo stato nuovo, e la divergenza si manifesterebbe
#: di nuovo come eccezione a runtime.
ELIGIBILITY_STOP_REASONS: tuple[str, ...] = tuple(
    state for state in ELIGIBILITY_STATES if state != ELIGIBLE_FOR_RETRIEVAL
)

#: I punti in cui la run termina prima del dossier. Estratti da
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
    "PARSER_FAILED",
    "SOURCEUNIT_SELECTION_FAILED",
    "LIVE_STAGE_FAILED",
    # Esiti del gate deterministico pre-retrieval.
    *ELIGIBILITY_STOP_REASONS,
)

#: Stop **previsti dalla policy**: la pipeline si è fermata perché doveva.
#: Non vanno resi come guasti.
#:
#: Tutti gli esiti del gate sono stop controllati: sono la decisione che il gate
#: esiste per prendere. ``PARSER_TRANSPORT_FAILED`` resta fuori — è un guasto di
#: trasporto, e il runtime non sa distinguere il rifiuto deliberato del modello
#: dall'errore di rete.
CORRECT_STOP_REASONS: frozenset[str] = frozenset({
    "CASECONTEXT_MISMATCH", "RETRIEVAL_NO_MATCH", *ELIGIBILITY_STOP_REASONS,
})

#: Stop che sono **guasti**, non esiti. Elencati esplicitamente perché
#: l'insieme complementare sia leggibile senza calcolarlo.
FAILURE_STOP_REASONS: frozenset[str] = frozenset(
    set(STOP_REASONS) - CORRECT_STOP_REASONS
)


def is_controlled_stop(stopped_at: str | None) -> bool:
    """Vero se la run si è fermata per decisione della policy, non per guasto."""
    return stopped_at is not None and stopped_at in CORRECT_STOP_REASONS

PRODUCER_KINDS: tuple[str, ...] = ("DETERMINISTIC", "LLM", "HYBRID")

# --- Identità degli stage ---------------------------------------------------

#: ``stage_id -> stage_type``, nell'ordine di esecuzione. L'ordine è parte del
#: contratto: la UI lo usa per la timeline e non deve riordinarlo.
STAGE_TYPES: tuple[tuple[str, str], ...] = (
    ("stage_1_case_input", "CASE_INPUT"),
    ("stage_2_casecontext_parser", "CASECONTEXT_PARSER"),
    ("stage_3_casecontext_match", "CASECONTEXT_MATCH_VERIFIER"),
    # Il gate è deterministico e sta **prima** del retrieval: è il punto in cui
    # un input vuoto, fuori dominio, non azionabile o contraddittorio si ferma.
    # Prima esistevano due soli esiti di routing e la categoria dell'input non
    # li determinava.
    ("stage_3b_pre_retrieval_eligibility_gate", "PRE_RETRIEVAL_ELIGIBILITY_GATE"),
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

#: I soli **tre** stage che un LLM può produrre. Ogni altro stage è
#: deterministico: è ciò che impedisce a Gemma di comparire come autore di gate,
#: status, direction, contraddizione, score o bucket.
#:
#: ``stage_14_narrator`` è il terzo uso del modello e il solo che opera **dopo**
#: che lo stato canonico è già stato deciso. Non aggiunge autorità: produce una
#: vista, e ``stage_15_narrative_verifier`` — deterministico — decide se quella
#: vista può essere mostrata.
LLM_STAGE_IDS: frozenset[str] = frozenset({
    "stage_2_casecontext_parser",
    "stage_9_paper_context_enricher",
    "stage_14_narrator",
})

#: Nessuno stage resta privo di implementazione: 14 e 15 sono ora eseguiti.
NOT_IMPLEMENTED_STAGE_IDS: frozenset[str] = frozenset()

#: Stage che producono la **vista di presentazione**, non lo stato canonico.
#: Un loro fallimento non invalida il dossier: attiva il fallback strutturato.
PRESENTATION_STAGE_IDS: frozenset[str] = frozenset({
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


# --- Acquisizione documentale ------------------------------------------------

#: Lo stage da cui si legge come i documenti sono entrati nella run. Uno solo:
#: se la sintesi accettasse più fonti, due di esse potrebbero contraddirsi e non
#: ci sarebbe modo di sapere quale credere.
_DOCUMENT_STAGE_ID = "stage_6_document_resolution"

#: Motivo per cui un documento è degradato dal full text all'abstract.
_DEGRADATION_REASON = "PMC_RESOLUTION_FAILED"


def document_acquisition_summary(stages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Come i documenti di questa run sono stati ottenuti.

    Esiste perché la console deve poter mostrare cache hit, acquisizioni via API
    e degradazioni **senza calcolarle nel browser**: sono le informazioni che il
    clinico legge al posto della vecchia modalità di esecuzione, e derivarle nel
    frontend creerebbe una seconda definizione di "il documento è stato preso da
    qui" accanto a quella dello stage che l'ha davvero preso.

    Accetta stage in forma di dizionario — la stessa di ``PipelineStage.to_dict``
    — così la run in memoria e quella reidratata dal ledger producono lo stesso
    risultato dallo stesso codice. Che le due proiezioni non divergano è un
    invariante già dichiarato in ``rehydration``; qui va rispettato, non ripetuto.

    Restituisce ``None`` sui conteggi quando lo stage non è stato eseguito: uno
    zero al loro posto direbbe "nessun documento acquisito" invece di "non
    misurato", e sono due cose diverse.
    """
    stage = next(
        (s for s in stages if s.get("stage_id") == _DOCUMENT_STAGE_ID), None
    )
    if stage is None or stage.get("status") in (None, "SKIPPED"):
        return {
            "executed": False,
            "cache_hits": None, "cache_misses": None, "network_fetches": None,
            "degraded_to_abstract": None, "documents_unavailable": None,
            "sources": [], "reason_codes": list((stage or {}).get("reason_codes") or []),
        }

    preview = stage.get("output_preview") or {}
    documents = preview.get("documents") or []

    def _count(predicate) -> int:
        return sum(1 for document in documents if predicate(document))

    return {
        "executed": True,
        "cache_hits": preview.get("cache_hits", _count(lambda d: d.get("cache_hit"))),
        "cache_misses": preview.get("cache_misses", _count(lambda d: not d.get("cache_hit"))),
        "network_fetches": preview.get("network_fetch_count", 0),
        # Un documento degradato **è** stato acquisito: la degradazione dice
        # quanto se ne è ottenuto, non se l'acquisizione sia riuscita.
        "degraded_to_abstract": _count(
            lambda d: _DEGRADATION_REASON in (d.get("reason_codes") or [])
        ),
        "documents_unavailable": _count(lambda d: not d.get("resolved")),
        "sources": sorted({
            str(d["source"]) for d in documents if d.get("source")
        }),
        "reason_codes": list(stage.get("reason_codes") or []),
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
        stages = [stage.to_dict() for stage in self.stages]
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_stage": self.current_stage,
            "stopped_at": self.stopped_at,
            "input_text": self.input_text,
            "stages": stages,
            "dossier_id": self.dossier_id,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "versions": dict(self.versions),
            "metrics": dict(self.metrics),
            "research_notice": self.research_notice(),
            "document_cache": dict(self.document_cache),
            "document_acquisition": document_acquisition_summary(stages),
            "llm_calls": self.llm_calls,
            **self.mode_summary(),
        }
