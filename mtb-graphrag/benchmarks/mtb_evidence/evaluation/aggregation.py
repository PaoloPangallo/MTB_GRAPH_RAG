"""Aggregazione delle metriche fra casi, categorie e architetture.

Aggregare somma numeratori e denominatori invece di mediare i valori: su quattro
casi, mediare rapporti calcolati su denominatori diversi da' un numero che non
corrisponde a nessun conteggio reale.

Ogni aggregato porta con se' i propri caveat. Con quattro casi development non si
possono trarre conclusioni sulla popolazione dei casi clinici, e il documento che
li riporta deve dirlo insieme al numero, non in una nota a fondo pagina.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .contracts import AggregateEvaluation, CaseEvaluation, MetricResult

SMALL_SAMPLE_CAVEATS = (
    "Quattro casi development: i valori descrivono questo campione e non stimano "
    "una popolazione.",
    "Nessun intervallo di confidenza e' riportato: con questo n sarebbe piu' ampio "
    "dell'intervallo dei valori possibili.",
    "I casi sono stati usati per selezionare il modello: non costituiscono una "
    "valutazione indipendente di quel modello.",
)


def combine(name: str, metrics: Iterable[MetricResult]) -> MetricResult:
    """Somma numeratori e denominatori, conservando gli elementi."""
    items = list(metrics)
    return MetricResult(
        name=name,
        numerator=sum(metric.numerator for metric in items),
        denominator=sum(metric.denominator for metric in items),
        covered_items=tuple(item for metric in items for item in metric.covered_items),
        missing_items=tuple(item for metric in items for item in metric.missing_items),
        partial_items=tuple(item for metric in items for item in metric.partial_items),
        notes=(f"aggregato su {len(items)} casi",),
    )


def aggregate(
    evaluations: Sequence[CaseEvaluation], *, scope: str = "all"
) -> AggregateEvaluation:
    by_name: dict[str, list[MetricResult]] = {}
    for evaluation in evaluations:
        for name, metric in evaluation.metrics.items():
            by_name.setdefault(name, []).append(metric)

    by_category: dict[str, dict[str, MetricResult]] = {}
    categories = {evaluation.category for evaluation in evaluations}
    for category in sorted(categories):
        subset = [e for e in evaluations if e.category == category]
        collected: dict[str, list[MetricResult]] = {}
        for evaluation in subset:
            for name, metric in evaluation.metrics.items():
                collected.setdefault(name, []).append(metric)
        by_category[category] = {
            name: combine(name, metrics) for name, metrics in collected.items()
        }

    return AggregateEvaluation(
        scope=scope,
        case_count=len(evaluations),
        metrics={name: combine(name, metrics) for name, metrics in by_name.items()},
        by_category=by_category,
        caveats=SMALL_SAMPLE_CAVEATS,
    )


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, object]]) -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")
    return path


CASE_METRIC_COLUMNS = (
    "case_id",
    "category",
    "architecture",
    "metric",
    "numerator",
    "denominator",
    "value",
    "missing_items",
)


def case_metric_rows(evaluations: Sequence[CaseEvaluation]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for evaluation in evaluations:
        for name, metric in sorted(evaluation.metrics.items()):
            rows.append(
                {
                    "case_id": evaluation.case_id,
                    "category": evaluation.category,
                    "architecture": evaluation.architecture,
                    "metric": name,
                    "numerator": metric.numerator,
                    "denominator": metric.denominator,
                    "value": "" if metric.value is None else round(metric.value, 4),
                    "missing_items": "; ".join(metric.missing_items[:10]),
                }
            )
    return rows


def write_case_metrics(path: Path, evaluations: Sequence[CaseEvaluation]) -> Path:
    return _write_csv(path, CASE_METRIC_COLUMNS, case_metric_rows(evaluations))


AGGREGATE_COLUMNS = (
    "scope",
    "category",
    "metric",
    "numerator",
    "denominator",
    "value",
    "case_count",
)


def write_aggregate_metrics(
    path: Path, aggregates: Mapping[str, AggregateEvaluation]
) -> Path:
    rows: list[dict[str, object]] = []
    for scope, aggregate_result in aggregates.items():
        for name, metric in sorted(aggregate_result.metrics.items()):
            rows.append(
                {
                    "scope": scope,
                    "category": "ALL",
                    "metric": name,
                    "numerator": metric.numerator,
                    "denominator": metric.denominator,
                    "value": "" if metric.value is None else round(metric.value, 4),
                    "case_count": aggregate_result.case_count,
                }
            )
        for category, metrics in aggregate_result.by_category.items():
            for name, metric in sorted(metrics.items()):
                rows.append(
                    {
                        "scope": scope,
                        "category": category,
                        "metric": name,
                        "numerator": metric.numerator,
                        "denominator": metric.denominator,
                        "value": "" if metric.value is None else round(metric.value, 4),
                        "case_count": aggregate_result.case_count,
                    }
                )
    return _write_csv(path, AGGREGATE_COLUMNS, rows)


LOSS_COLUMNS = ("case_id", "claim_id", "state", "stage", "explanation")


def write_loss_decomposition(path: Path, evaluations: Sequence[CaseEvaluation]) -> Path:
    rows = [
        {
            "case_id": item.case_id,
            "claim_id": item.claim_id,
            "state": item.state,
            "stage": item.stage,
            "explanation": item.explanation,
        }
        for evaluation in evaluations
        for item in evaluation.loss
    ]
    return _write_csv(path, LOSS_COLUMNS, rows)


def write_metric_family(
    path: Path, evaluations: Sequence[CaseEvaluation], prefixes: Sequence[str]
) -> Path:
    """Estrae in un CSV dedicato solo le metriche di una famiglia."""
    rows = [
        row
        for row in case_metric_rows(evaluations)
        if any(str(row["metric"]).startswith(prefix) for prefix in prefixes)
    ]
    return _write_csv(path, CASE_METRIC_COLUMNS, rows)
