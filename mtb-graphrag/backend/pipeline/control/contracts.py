"""Vocabolario dello strato di controllo condiviso dalle due architetture.

Questo modulo non contiene logica: definisce soltanto i tipi che ogni fase
della pipeline verificabile si scambia. È la radice del grafo delle dipendenze
del package ``control`` e non importa nulla dai suoi fratelli.

Tutte le strutture sono immutabili (``frozen=True``, campi tuple): ogni fase
restituisce un oggetto nuovo e non muta il proprio input, così la vista
canonica di uno stadio non può essere alterata a valle da uno stadio
successivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

ArchitectureId = Literal["deterministic", "agentic"]
OrchestrationMode = Literal["deterministic", "agentic"]

#: Stati di completezza di un'azione di raccolta e, per propagazione
#: pessimistica, dei record che ne derivano.
CompletenessStatus = Literal["complete", "truncated", "partial", "unknown"]

#: Fedeltà del replay. ``degraded_v1_events`` segnala che il run contiene
#: eventi con lo schema v1, privi dei record strutturati necessari a
#: ricostruire integralmente la vista.
ReplayFidelity = Literal["full", "degraded_v1_events", "partial"]

RecordKind = Literal["evidence", "drug", "trial", "resistance", "oncokb"]

Severity = Literal["blocking", "repairable", "advisory"]

#: Le fasi cronometrate, identiche per entrambe le architetture. Una fase che
#: non fa nulla riporta 0, mai una chiave assente: le metriche devono essere
#: confrontabili senza sapere quale architettura le ha prodotte.
STAGE_NAMES: tuple[str, ...] = (
    "orchestration",
    "collection",
    "replay",
    "canonicalization",
    "projection",
    "candidate_rendering",
    "structural_verification",
    "source_verification",
    "applicability",
    "repair",
    "final_rendering",
    "dossier",
)


@dataclass(frozen=True)
class CaseContext:
    """Proiezione immutabile della richiesta clinica.

    Sostituisce il passaggio di ``dict`` grezzi fra le fasi: il caso è letto
    una volta al bordo del sistema e poi non cambia più.
    """

    gene: str
    variant: str
    tumor_type: str
    alteration_type: str
    therapy_line: str
    driver_variant: str = ""
    disease_stage: str | None = None
    disease_setting: str | None = None
    prior_therapies: tuple[str, ...] = ()
    prior_response: str | None = None
    ecog_status: int | None = None
    cns_metastases: bool | None = None
    co_alterations: tuple[str, ...] = ()
    jurisdiction: str | None = None
    mtb_goal: str | None = None
    enrich_with_oncokb: bool = False

    @classmethod
    def from_request(cls, req: Any) -> "CaseContext":
        return cls(
            gene=(req.gene or "").strip(),
            variant=(req.variant or "").strip(),
            tumor_type=(req.tumor_type or "").strip(),
            alteration_type=req.alteration_type,
            therapy_line=req.therapy_line,
            driver_variant=(getattr(req, "driver_variant", None) or "").strip(),
            disease_stage=getattr(req, "disease_stage", None),
            disease_setting=getattr(req, "disease_setting", None),
            prior_therapies=tuple(getattr(req, "prior_therapies", ()) or ()),
            prior_response=getattr(req, "prior_response", None),
            ecog_status=getattr(req, "ecog_status", None),
            cns_metastases=getattr(req, "cns_metastases", None),
            co_alterations=tuple(getattr(req, "co_alterations", ()) or ()),
            jurisdiction=getattr(req, "jurisdiction", None),
            mtb_goal=getattr(req, "mtb_goal", None),
            enrich_with_oncokb=bool(getattr(req, "enrich_with_oncokb", False)),
        )

    def label(self) -> str:
        gene = self.gene or "N/D"
        return f"{gene} {self.variant} — {self.tumor_type}".strip()

    def to_state(self) -> dict[str, Any]:
        """Stato iniziale per gli strumenti KG, che lavorano ancora su dict."""
        return {
            "gene": self.gene,
            "variant": self.variant,
            "tumor_type": self.tumor_type,
            "alteration_type": self.alteration_type,
            "therapy_line": self.therapy_line,
            "driver_variant": self.driver_variant,
            "disease_stage": self.disease_stage,
            "disease_setting": self.disease_setting,
            "prior_therapies": list(self.prior_therapies),
            "prior_response": self.prior_response,
            "ecog_status": self.ecog_status,
            "cns_metastases": self.cns_metastases,
            "co_alterations": list(self.co_alterations),
            "jurisdiction": self.jurisdiction,
            "mtb_goal": self.mtb_goal,
            "enrich_with_oncokb": self.enrich_with_oncokb,
            "complexity": "moderate",
            "variant_data": {},
            "drug_candidates": [],
            "trial_candidates": [],
            "resistance_data": [],
            "oncokb_enrichment": [],
            "report": "",
            "cited_pmids": [],
            "escat_tier": "",
        }


@dataclass(frozen=True)
class ProvenanceRef:
    """Puntatore da un record all'evento di ledger che lo ha prodotto."""

    event_id: str
    sequence: int
    action_id: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    observed_at: str = ""


@dataclass(frozen=True)
class ConflictAnnotation:
    """Disaccordo fra osservazioni dello stesso record canonico.

    I conflitti sono annotati, non risolti: scegliere silenziosamente un valore
    nasconderebbe al MTB un'informazione che gli serve.
    """

    field_name: str
    values: tuple[str, ...]
    provenance: tuple[ProvenanceRef, ...] = ()


@dataclass(frozen=True)
class OriginalClaim:
    """La claim come osservata la prima volta. Non viene mai riscritta.

    La claim contestualizzata prodotta dal source verifier è un artefatto
    derivato e vive altrove: il ledger e la claim originale restano immutati.
    """

    subject: str
    relation: str
    object: str
    context: str = ""
    source_id: str | None = None
    evidence_statement: str | None = None
    citation_text: str | None = None
    evidence_level: str | None = None


@dataclass(frozen=True)
class RecordObservation:
    """Una singola occorrenza di un record, con la sua provenienza."""

    provenance: ProvenanceRef
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class CanonicalRecord:
    """Record deduplicato che conserva l'intera genealogia delle occorrenze."""

    canonical_record_id: str
    record_kind: RecordKind
    identity_key: tuple[str, ...]
    original_claim: OriginalClaim
    observations: tuple[RecordObservation, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    source_action_ids: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRef, ...] = ()
    conflict_annotations: tuple[ConflictAnnotation, ...] = ()
    completeness_status: CompletenessStatus = "unknown"

    @property
    def occurrence_count(self) -> int:
        return len(self.observations)


@dataclass(frozen=True)
class CanonicalView:
    """Vista canonica ricostruita per replay dagli eventi del ledger."""

    run_id: str
    records: tuple[CanonicalRecord, ...] = ()
    records_in: int = 0
    replay_fidelity: ReplayFidelity = "full"
    unreplayable_event_ids: tuple[str, ...] = ()
    completeness_status: CompletenessStatus = "unknown"

    @property
    def records_out(self) -> int:
        return len(self.records)

    def by_kind(self, kind: RecordKind) -> tuple[CanonicalRecord, ...]:
        return tuple(record for record in self.records if record.record_kind == kind)


@dataclass(frozen=True)
class ProjectedRecord:
    """Record della vista canonica valutato rispetto al caso e all'obiettivo."""

    canonical_record_id: str
    record_kind: RecordKind
    claim: OriginalClaim
    admitted: bool
    exclusion_reason: str | None = None
    required_citation: str | None = None
    #: Token che il renderer è autorizzato a emettere per questo record.
    #: Trasforma "il renderer ha inventato qualcosa?" in una domanda decidibile.
    lexicon: frozenset[str] = frozenset()
    entities: frozenset[str] = frozenset()
    conflict_annotations: tuple[ConflictAnnotation, ...] = ()
    provenance: tuple[ProvenanceRef, ...] = ()


@dataclass(frozen=True)
class Projection:
    """Selezione pertinente al caso, derivata solo dalla vista canonica."""

    run_id: str
    case_label: str
    records: tuple[ProjectedRecord, ...] = ()
    criteria: tuple[str, ...] = ()
    completeness_status: CompletenessStatus = "unknown"

    @property
    def admitted(self) -> tuple[ProjectedRecord, ...]:
        return tuple(record for record in self.records if record.admitted)

    @property
    def excluded(self) -> tuple[ProjectedRecord, ...]:
        return tuple(record for record in self.records if not record.admitted)

    @property
    def admitted_ids(self) -> frozenset[str]:
        return frozenset(record.canonical_record_id for record in self.admitted)

    @property
    def excluded_ids(self) -> frozenset[str]:
        return frozenset(record.canonical_record_id for record in self.excluded)


@dataclass(frozen=True)
class Violation:
    """Singolo esito negativo di una verifica strutturale."""

    code: str
    severity: Severity
    detail: str
    canonical_record_id: str | None = None
    excerpt: str | None = None


@dataclass(frozen=True)
class StructuralVerdict:
    """Esito strutturato della verifica. Mai un semplice booleano."""

    stage: Literal["candidate", "final", "dossier", "narration"]
    violations: tuple[Violation, ...] = ()
    warnings: tuple[Violation, ...] = ()
    missing_claims: tuple[str, ...] = ()
    unsupported_claims: tuple[str, ...] = ()
    spurious_citations: tuple[str, ...] = ()
    coverage: float = 1.0

    @property
    def status(self) -> str:
        if any(v.severity == "blocking" for v in self.violations):
            return "violations_blocking"
        if self.violations:
            return "violations_repairable"
        return "pass"

    @property
    def requires_repair(self) -> bool:
        return any(v.severity == "repairable" for v in self.violations) and not any(
            v.severity == "blocking" for v in self.violations
        )

    @property
    def requires_human_review(self) -> bool:
        return any(v.severity == "blocking" for v in self.violations) or self.coverage < 1.0

    def merged_with(self, other: "StructuralVerdict") -> "StructuralVerdict":
        """Combina due verdetti dello stesso stadio (es. testo + dossier)."""
        return StructuralVerdict(
            stage=self.stage,
            violations=self.violations + other.violations,
            warnings=self.warnings + other.warnings,
            missing_claims=self.missing_claims + other.missing_claims,
            unsupported_claims=self.unsupported_claims + other.unsupported_claims,
            spurious_citations=self.spurious_citations + other.spurious_citations,
            coverage=min(self.coverage, other.coverage),
        )


@dataclass(frozen=True)
class RepairAction:
    """Azione di riparazione pianificata deterministicamente.

    ``kind`` separa i due regimi: una riparazione di rendering non può
    richiamare strumenti, perché un difetto di formattazione non giustifica
    una nuova interrogazione del grafo.
    """

    kind: Literal["rendering", "collection"]
    rationale: str
    triggered_by: tuple[str, ...] = ()
    tool_name: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    target_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Escalation:
    """Rinvio alla revisione umana quando la riparazione non è possibile."""

    reason_category: str
    detail: str
    triggered_by: tuple[str, ...] = ()
    requires_human_review: bool = True


@dataclass(frozen=True)
class StageTiming:
    stage: str
    elapsed_ms: int


class RepairNotPermitted(RuntimeError):
    """Sollevata quando una riparazione tenta uno strumento non autorizzato."""


def stage_timings_dict(timings: Sequence[StageTiming]) -> dict[str, int]:
    """Somma i tempi per fase, garantendo tutte le chiavi di ``STAGE_NAMES``."""
    totals = {name: 0 for name in STAGE_NAMES}
    for timing in timings:
        totals[timing.stage] = totals.get(timing.stage, 0) + timing.elapsed_ms
    return totals
