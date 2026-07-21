"""Fedelta' del retrieval rispetto allo **snapshot gold**.

Il riferimento non e' il clinical gold: e' cio' che nello snapshot esiste ed e'
raggiungibile. Un elemento assente dal grafo non entra nel denominatore del recall,
perche' pretenderlo misurerebbe la copertura del dato e non la qualita' del
retriever, e i due numeri devono restare separabili.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..contracts import (
    ClinicalGoldCase,
    MetricResult,
    RetrievalPrediction,
    SnapshotGoldCase,
)
from ..matching import (
    normalize_ncts,
    normalize_pmids,
    normalize_therapies,
    score_claims,
    score_sets,
)
from ..snapshot_gold import KIND_NCT, KIND_PMID, KIND_THERAPY


def _unreachable(snapshot: SnapshotGoldCase, kind: str) -> set[str]:
    return {
        item.clinical_item_id.rsplit("::", 1)[-1]
        for item in snapshot.by_kind(kind)
        if not item.is_retrievable
    }


def retrieval_metrics(
    case: ClinicalGoldCase,
    snapshot: SnapshotGoldCase,
    prediction: RetrievalPrediction,
    *,
    expected_claims: Sequence[Mapping[str, object]] = (),
) -> dict[str, MetricResult]:
    metrics: dict[str, MetricResult] = {}

    therapy = score_sets(
        "therapy",
        normalize_therapies(prediction.therapies),
        normalize_therapies(snapshot.retrievable_therapies),
        unreachable=normalize_therapies(_unreachable(snapshot, KIND_THERAPY)),
    )
    pmid = score_sets(
        "pmid",
        normalize_pmids(prediction.pmids),
        normalize_pmids(snapshot.retrievable_pmids),
        unreachable=normalize_pmids(_unreachable(snapshot, KIND_PMID)),
    )
    nct = score_sets(
        "nct",
        normalize_ncts(prediction.nct_ids),
        normalize_ncts(snapshot.retrievable_nct_ids),
        unreachable=normalize_ncts(_unreachable(snapshot, KIND_NCT)),
    )
    for score in (therapy, pmid, nct):
        metrics.update(score.as_metrics())

    if expected_claims:
        metrics.update(score_claims(list(prediction.claims), list(expected_claims)).as_metrics())

    metrics.update(tool_metrics(case, prediction))
    metrics["negative_case_accuracy"] = negative_case_accuracy(case, prediction)
    return metrics


def tool_metrics(
    case: ClinicalGoldCase, prediction: RetrievalPrediction
) -> dict[str, MetricResult]:
    """Strumenti obbligatori richiamati e strumenti inutili invocati.

    Il tasso di strumenti inutili non e' un dettaglio di efficienza: un percorso che
    invoca strumenti non pertinenti sta esplorando a caso, e su un caso noto e'
    proprio cio' che il traversal deterministico dovrebbe evitare.
    """
    called = set(prediction.tools_called)
    required = set(case.required_tools)
    unnecessary = set(case.unnecessary_tools)
    return {
        "required_tool_recall": MetricResult(
            name="required_tool_recall",
            numerator=len(called & required),
            denominator=len(required),
            covered_items=tuple(sorted(called & required)),
            missing_items=tuple(sorted(required - called)),
        ),
        "unnecessary_tool_rate": MetricResult(
            name="unnecessary_tool_rate",
            numerator=len(called & unnecessary),
            denominator=max(len(called), 1),
            covered_items=tuple(sorted(called & unnecessary)),
            notes=("denominatore: strumenti effettivamente invocati",),
        ),
    }


def negative_case_accuracy(
    case: ClinicalGoldCase, prediction: RetrievalPrediction
) -> MetricResult:
    """Correttezza sui casi che richiedono astensione.

    Per un caso no-answer la risposta giusta e' non produrre nulla. Qualunque
    terapia, PMID o NCT emesso e' un falso positivo, non una copertura parziale.
    """
    if not case.expected_abstention:
        return MetricResult(
            name="negative_case_accuracy",
            numerator=0.0,
            denominator=0.0,
            notes=("caso non negativo: metrica non applicabile",),
        )
    emitted = (
        list(prediction.therapies) + list(prediction.pmids) + list(prediction.nct_ids)
    )
    correct = prediction.abstained and not emitted
    return MetricResult(
        name="negative_case_accuracy",
        numerator=1.0 if correct else 0.0,
        denominator=1.0,
        missing_items=tuple(sorted(str(item) for item in emitted)),
        notes=(
            "astensione corretta"
            if correct
            else f"emessi {len(emitted)} elementi dove il gold richiede astensione",
        ),
    )
