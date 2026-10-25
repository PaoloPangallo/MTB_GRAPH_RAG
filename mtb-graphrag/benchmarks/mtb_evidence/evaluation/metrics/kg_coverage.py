"""Copertura del Knowledge Graph rispetto al clinical gold.

Risponde a una sola domanda: **quanto di cio' che dovrebbe essere ricostruito esiste
in questo grafo?** Non misura alcun sistema; misura il dato. Un valore basso qui
significa che nessuna architettura, per quanto buona, potrebbe fare meglio.
"""

from __future__ import annotations

from typing import Mapping

from ..contracts import (
    PARTIALLY_PRESENT,
    PRESENT,
    ClinicalGoldCase,
    MetricResult,
    SnapshotGoldCase,
)
from ..snapshot_gold import (
    KIND_CLAIM,
    KIND_NCT,
    KIND_PMID,
    KIND_QUALIFIER,
    KIND_THERAPY,
)


def _coverage(name: str, snapshot: SnapshotGoldCase, kind: str) -> MetricResult:
    items = snapshot.by_kind(kind)
    covered = [item for item in items if item.presence_status == PRESENT]
    partial = [item for item in items if item.presence_status == PARTIALLY_PRESENT]
    missing = [
        item
        for item in items
        if item.presence_status not in {PRESENT, PARTIALLY_PRESENT}
    ]
    # Un elemento parzialmente presente conta a meta': e' recuperabile ma incompleto,
    # e appiattirlo su "presente" o "assente" nasconderebbe la differenza.
    numerator = len(covered) + 0.5 * len(partial)
    return MetricResult(
        name=name,
        numerator=numerator,
        denominator=len(items),
        covered_items=tuple(item.clinical_item_id for item in covered),
        partial_items=tuple(item.clinical_item_id for item in partial),
        missing_items=tuple(item.clinical_item_id for item in missing),
        notes=("gli elementi parzialmente presenti contano 0.5",) if partial else (),
    )


def entity_coverage(case: ClinicalGoldCase, snapshot: SnapshotGoldCase) -> MetricResult:
    """Entita' cliniche del caso presenti nel grafo.

    Le entita' sono gene, variante e malattia: il grafo le contiene quasi sempre,
    ed e' proprio il contrasto con la copertura delle fonti a essere informativo.
    """
    present = [
        item.clinical_item_id
        for item in snapshot.items
        if item.item_kind in {KIND_THERAPY, KIND_CLAIM} and item.presence_status == PRESENT
    ]
    return MetricResult(
        name="entity_coverage",
        numerator=len(present),
        denominator=max(len(case.expected_entities), 1),
        covered_items=tuple(present),
        notes=("approssimata dalle entita' raggiunte dal traversal",),
    )


def therapy_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    return _coverage("therapy_coverage", snapshot, KIND_THERAPY)


def pmid_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    return _coverage("pmid_coverage", snapshot, KIND_PMID)


def nct_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    return _coverage("nct_coverage", snapshot, KIND_NCT)


def claim_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    return _coverage("claim_coverage", snapshot, KIND_CLAIM)


def qualifier_schema_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    """Quota di qualificatori che lo schema e' in grado di rappresentare.

    Distinta dalla copertura per record: un qualificatore che lo schema non modella
    non e' un dato mancante, e' una capacita' assente. Nessun modello puo' colmarlo.
    """
    items = snapshot.by_kind(KIND_QUALIFIER)
    modelled = [
        item
        for item in items
        if not any("non modellato" in note for note in item.coverage_notes)
    ]
    return MetricResult(
        name="qualifier_schema_coverage",
        numerator=len(modelled),
        denominator=len(items),
        covered_items=tuple(item.clinical_item_id for item in modelled),
        missing_items=tuple(
            item.clinical_item_id for item in items if item not in modelled
        ),
        notes=("denominatore: qualificatori richiesti dalle claim del caso",),
    )


def qualifier_record_coverage(snapshot: SnapshotGoldCase) -> MetricResult:
    """Quota di qualificatori effettivamente presenti in almeno un record."""
    items = snapshot.by_kind(KIND_QUALIFIER)
    present = [item for item in items if item.presence_status == PRESENT]
    return MetricResult(
        name="qualifier_record_coverage",
        numerator=len(present),
        denominator=len(items),
        covered_items=tuple(item.clinical_item_id for item in present),
        missing_items=tuple(
            item.clinical_item_id for item in items if item.presence_status != PRESENT
        ),
    )


def all_coverage_metrics(
    case: ClinicalGoldCase, snapshot: SnapshotGoldCase
) -> Mapping[str, MetricResult]:
    return {
        metric.name: metric
        for metric in (
            entity_coverage(case, snapshot),
            therapy_coverage(snapshot),
            pmid_coverage(snapshot),
            nct_coverage(snapshot),
            claim_coverage(snapshot),
            qualifier_schema_coverage(snapshot),
            qualifier_record_coverage(snapshot),
        )
    }
