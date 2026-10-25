"""Coda prioritaria di curation delle fonti.

Il corpus precedente ha 102 unita' e sei annotate. Annotarle tutte non e'
realistico a breve, quindi la domanda diventa **quali sei annotare prima**, e la
risposta non e' «quelle che migliorano le metriche» — sarebbe la selezione
opportunistica che il censimento aveva eliminato.

Il criterio e' il **rischio di propagazione errata**: quanto danno farebbe un
qualificatore sbagliato su quella fonte. Una fonte a coorte irrisolta che
sostiene otto statement puo' propagare il setting del braccio sbagliato su otto
proposizioni; una fonte a statement singolo e coorte unica ne puo' sbagliare
una. L'ordine segue il danno potenziale, non il guadagno atteso.

Un fatto strutturale da tenere presente leggendo i gruppi: il gruppo A (coorte
irrisolta) e' **contenuto** nel gruppo B (multi-statement), e non per caso.
`requires_cohort_split` confronta interventi e malattie *fra gli statement* di
una fonte, quindi non puo' accendersi su una fonte con un solo statement. La
molteplicita' di coorti dentro un singolo statement resta invisibile a questo
rilevatore: e' un limite del metodo, non una proprieta' del corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

PRIORITY_SCOPE_VERSION = "priority_curation_scope/1.0"

# Classi di priorita'.
A_UNRESOLVED_COHORT = "A_UNRESOLVED_COHORT"
B_MULTI_STATEMENT = "B_MULTI_STATEMENT"
AB_BOTH = "AB_BOTH"
CONFLICT_PRIORITY = "CONFLICT_PRIORITY"

PRIORITY_CLASSES = (AB_BOTH, A_UNRESOLVED_COHORT, B_MULTI_STATEMENT, CONFLICT_PRIORITY)

# Ordine di lavorazione richiesto dal protocollo.
WORK_ORDER = {
    "ab_with_conflict": 0,
    "ab_multi_intervention": 1,
    "ab_other": 2,
    "a_only": 3,
    "b_with_conflict": 4,
    "conflict_only": 5,
    "b_multi_intervention": 6,
    "b_other": 7,
}

# Disponibilita' della fonte.
LOCAL_METADATA_ONLY = "local_metadata_only"
LOCAL_ABSTRACT = "local_abstract"
REQUIRES_EXTERNAL_ACCESS = "requires_external_access"


@dataclass
class PriorityUnit:
    """Una unita' nella coda, con la ragione per cui ci si trova."""

    profile_unit_id: str
    canonical_source_id: str
    priority_class: str
    work_bucket: str
    pmids: tuple[str, ...] = ()
    dois: tuple[str, ...] = ()
    ncts: tuple[str, ...] = ()
    title: str = ""
    statement_ids: tuple[str, ...] = ()
    diseases: tuple[str, ...] = ()
    biomarkers: tuple[str, ...] = ()
    interventions: tuple[str, ...] = ()
    directions: tuple[str, ...] = ()
    polarities: tuple[str, ...] = ()
    candidate_cohort_count: int = 1
    candidate_intervention_count: int = 1
    known_conflicts: tuple[Mapping[str, Any], ...] = ()
    propagation_risk: int = 0
    risk_band: str = "low"
    priority_rank: int = 0
    rationale: str = ""
    current_cohort_state: str = ""
    current_review_status: str = ""
    source_availability: str = REQUIRES_EXTERNAL_ACCESS
    needs_external_access: bool = True
    blind_annotation_id: str = ""

    @property
    def statement_count(self) -> int:
        return len(self.statement_ids)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_unit_id": self.profile_unit_id,
            "canonical_source_id": self.canonical_source_id,
            "priority_class": self.priority_class,
            "work_bucket": self.work_bucket,
            "pmids": list(self.pmids),
            "dois": list(self.dois),
            "ncts": list(self.ncts),
            "title": self.title,
            "statement_ids": list(self.statement_ids),
            "statement_count": self.statement_count,
            "diseases": list(self.diseases),
            "biomarkers": list(self.biomarkers),
            "interventions": list(self.interventions),
            "directions": list(self.directions),
            "assertion_polarities": list(self.polarities),
            "candidate_cohort_count": self.candidate_cohort_count,
            "candidate_intervention_count": self.candidate_intervention_count,
            "known_conflicts": [dict(item) for item in self.known_conflicts],
            "propagation_risk": self.propagation_risk,
            "risk_band": self.risk_band,
            "priority_rank": self.priority_rank,
            "rationale": self.rationale,
            "current_cohort_state": self.current_cohort_state,
            "current_review_status": self.current_review_status,
            "source_availability": self.source_availability,
            "needs_external_access": self.needs_external_access,
            "blind_annotation_id": self.blind_annotation_id,
            "scope_version": PRIORITY_SCOPE_VERSION,
        }


def propagation_risk(
    *,
    statement_count: int,
    cohort_unresolved: bool,
    intervention_count: int,
    disease_count: int,
    conflict_count: int,
) -> tuple[int, str]:
    """Quanto danno farebbe qui un qualificatore sbagliato.

    Il numero di statement e' il **moltiplicatore**: e' su quante proposizioni
    l'errore si propaga. Coorte irrisolta, piu' interventi e conflitti sono i
    fattori che rendono l'errore probabile. Il prodotto dei due e' cio' che
    conta, ed e' il motivo per cui una fonte con otto statement e coorte
    ambigua viene prima di una con venti statement e coorte unica.
    """
    likelihood = 1
    if cohort_unresolved:
        likelihood += 2
    if intervention_count > 1:
        likelihood += 1
    if disease_count > 1:
        likelihood += 1
    if conflict_count:
        likelihood += 3

    score = likelihood * max(statement_count, 1)
    if score >= 20:
        band = "critical"
    elif score >= 10:
        band = "high"
    elif score >= 4:
        band = "medium"
    else:
        band = "low"
    return score, band


def _work_bucket(
    *, in_a: bool, in_b: bool, has_conflict: bool, multi_intervention: bool
) -> str:
    if in_a and in_b:
        if has_conflict:
            return "ab_with_conflict"
        return "ab_multi_intervention" if multi_intervention else "ab_other"
    if in_a:
        return "a_only"
    if not in_b:
        return "conflict_only"
    # Un conflitto su una fonte multi-statement va comunque anticipato: senza
    # questo ramo finirebbe fra le unita' ordinarie e verrebbe lavorato per
    # ultimo, che e' l'opposto di cio' che il rischio suggerisce.
    if has_conflict:
        return "b_with_conflict"
    return "b_multi_intervention" if multi_intervention else "b_other"


def _priority_class(*, in_a: bool, in_b: bool, has_conflict: bool) -> str:
    if in_a and in_b:
        return AB_BOTH
    if in_a:
        return A_UNRESOLVED_COHORT
    if in_b:
        return B_MULTI_STATEMENT
    if has_conflict:
        return CONFLICT_PRIORITY
    return B_MULTI_STATEMENT


def build_priority_queue(
    units: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
    *,
    abstracts_available: Iterable[str] = (),
    metadata_available: Iterable[str] = (),
) -> list[PriorityUnit]:
    """Costruisce la coda a partire dagli artefatti congelati del corpus.

    Le unita' conflittuali fuori da A e B vengono **incluse** anche se
    l'obiettivo le richiedeva solo dentro A o B. Un conflitto e' il caso di
    propagazione piu' pericoloso che il corpus conosca gia': escluderlo per
    rispettare il perimetro sarebbe la scelta rischiosa, includerlo costa
    soltanto lavoro.
    """
    conflicts_by_statement: dict[str, list[Mapping[str, Any]]] = {}
    for conflict in conflicts:
        conflicts_by_statement.setdefault(str(conflict.get("statement_id")), []).append(conflict)

    # Distinzione voluta fra le due cache. Quella dei metadati contiene titolo,
    # rivista e tipi di pubblicazione; l'abstract e' un'altra cosa e vive in un
    # file separato. Confonderle segnalerebbe come «fonte disponibile» una fonte
    # di cui conosciamo soltanto il titolo.
    with_abstract = set(abstracts_available)
    with_metadata = set(metadata_available)
    queue: list[PriorityUnit] = []

    for unit in units:
        statement_ids = tuple(unit.get("statement_ids") or ())
        in_a = unit.get("cohort_state") == "unresolved_cohort"
        in_b = len(statement_ids) > 1
        unit_conflicts = [
            conflict
            for statement_id in statement_ids
            for conflict in conflicts_by_statement.get(statement_id, ())
        ]
        has_conflict = bool(unit_conflicts)
        if not (in_a or in_b or has_conflict):
            continue

        entry = inventory.get(str(unit.get("canonical_source_id")), {})
        interventions = tuple(entry.get("interventions") or ())
        diseases = tuple(entry.get("diseases") or ())
        multi_intervention = len(interventions) > 1

        score, band = propagation_risk(
            statement_count=len(statement_ids),
            cohort_unresolved=in_a,
            intervention_count=len(interventions),
            disease_count=len(diseases),
            conflict_count=len(unit_conflicts),
        )

        pmids = tuple(unit.get("pmids") or ())
        keys = [f"pmid:{pmid}" for pmid in pmids]
        if any(key in with_abstract for key in keys):
            availability = LOCAL_ABSTRACT
        elif any(key in with_metadata for key in keys):
            availability = LOCAL_METADATA_ONLY
        else:
            availability = REQUIRES_EXTERNAL_ACCESS

        queue.append(
            PriorityUnit(
                profile_unit_id=str(unit.get("profile_unit_id")),
                canonical_source_id=str(unit.get("canonical_source_id")),
                priority_class=_priority_class(
                    in_a=in_a, in_b=in_b, has_conflict=has_conflict
                ),
                work_bucket=_work_bucket(
                    in_a=in_a,
                    in_b=in_b,
                    has_conflict=has_conflict,
                    multi_intervention=multi_intervention,
                ),
                pmids=pmids,
                dois=tuple(unit.get("dois") or ()),
                ncts=tuple(unit.get("ncts") or ()),
                title=str(unit.get("title") or ""),
                statement_ids=statement_ids,
                diseases=diseases,
                biomarkers=tuple(entry.get("biomarkers") or ()),
                interventions=interventions,
                directions=tuple(entry.get("directions") or ()),
                polarities=tuple(entry.get("assertion_polarities") or ()),
                candidate_cohort_count=max(len(interventions), 1) if in_a else 1,
                candidate_intervention_count=max(len(interventions), 1),
                known_conflicts=tuple(unit_conflicts),
                propagation_risk=score,
                risk_band=band,
                rationale=_rationale(in_a, in_b, has_conflict, len(statement_ids)),
                current_cohort_state=str(unit.get("cohort_state") or ""),
                current_review_status=str(unit.get("review_status") or ""),
                source_availability=availability,
                needs_external_access=availability != LOCAL_ABSTRACT,
                blind_annotation_id=str(unit.get("blind_annotation_id") or ""),
            )
        )

    # L'ordinamento e' totale e deterministico: bucket, poi rischio decrescente,
    # poi id. Senza l'ultimo criterio due unita' a pari rischio potrebbero
    # scambiarsi di posto fra esecuzioni.
    queue.sort(
        key=lambda item: (
            WORK_ORDER.get(item.work_bucket, 99),
            -item.propagation_risk,
            item.profile_unit_id,
        )
    )
    for rank, item in enumerate(queue, start=1):
        item.priority_rank = rank
    return queue


def _rationale(in_a: bool, in_b: bool, has_conflict: bool, statement_count: int) -> str:
    reasons: list[str] = []
    if has_conflict:
        reasons.append("conflitto gia' rilevato fra fonte e proposizione")
    if in_a:
        reasons.append("coorte non risolta: rischio di propagare il braccio sbagliato")
    if in_b:
        reasons.append(f"una annotazione ricade su {statement_count} statement")
    return "; ".join(reasons)


def group_overlap(queue: Sequence[PriorityUnit]) -> dict[str, Any]:
    """Composizione dei gruppi, con la nota sul perche' A e' contenuto in B."""
    in_a = {item.profile_unit_id for item in queue if item.priority_class in (AB_BOTH, A_UNRESOLVED_COHORT)}
    in_b = {
        item.profile_unit_id
        for item in queue
        if item.priority_class in (AB_BOTH, B_MULTI_STATEMENT)
    }
    conflict_only = {
        item.profile_unit_id for item in queue if item.priority_class == CONFLICT_PRIORITY
    }
    return {
        "group_a_unresolved_cohort": len(in_a),
        "group_b_multi_statement": len(in_b),
        "overlap_ab": len(in_a & in_b),
        "a_only": len(in_a - in_b),
        "b_only": len(in_b - in_a),
        "conflict_only": len(conflict_only),
        "union_total": len(in_a | in_b | conflict_only),
        "overlap_note": (
            "A e' interamente contenuto in B, e la relazione e' strutturale, non "
            "empirica: requires_cohort_split confronta interventi e malattie fra gli "
            "statement di una fonte, quindi non puo' accendersi su una fonte con un "
            "solo statement. Una fonte a statement singolo che descrive due coorti "
            "resta invisibile a questo rilevatore."
        ),
    }
