"""Dual-run diagnostico: le due pipeline sulla stessa domanda.

La modalita' serve a **preparare** il rerun comparativo, non a valutarlo. La
differenza e' netta e va tenuta netta: qui si misura *dove* i due backend
divergono, non *quale dei due ha ragione*. Nessuna metrica di qualita' viene
calcolata, nessun gold viene letto, e nessuna riga di output porta un giudizio.

Il confronto avviene sull'unico asse su cui i due modelli sono commensurabili: il
`GraphEvidenceRecord`. Un `EvidenceStatement` legacy e un claim V3 non stanno in
corrispondenza uno a uno — un parent puo' avere due claim attivi, come
`evidence:11240`, e un claim puo' non avere nessuno statement legacy — ma
entrambi dichiarano da quale record del grafo provengono. Confrontare gli ID di
record e' l'unica sovrapposizione che non richiede di appiattire un modello
sull'altro.

Il numero di claim V3 e il numero di statement legacy non vengono confrontati fra
loro. Sarebbero due conteggi di cose diverse, e la loro differenza non
significherebbe niente.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.retrieval.backends import (
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
)
from backend.pipeline.evidence.retrieval.pipeline import (
    EvidenceRetrievalPipeline,
    RetrievalOutcome,
)

DIAGNOSTIC_VERSION = "dual_retrieval_diagnostic/1.0"

MODE_NAME = "dual_retrieval_diagnostic"


def _legacy_graph_ids(outcome: RetrievalOutcome | None) -> tuple[str, ...]:
    if outcome is None:
        return ()
    payload = outcome.payload
    ids: set[str] = set()
    for result in getattr(payload, "all_results", ()):
        ids.update(str(item) for item in getattr(result, "graph_evidence_ids", ()) or ())
    return tuple(sorted(ids))


def _legacy_candidate_ids(outcome: RetrievalOutcome | None) -> tuple[str, ...]:
    if outcome is None:
        return ()
    payload = outcome.payload
    return tuple(
        sorted(
            {str(result.statement_id) for result in getattr(payload, "all_results", ())}
        )
    )


def _v3_ids(outcome: RetrievalOutcome | None) -> dict[str, tuple[str, ...]]:
    if outcome is None:
        return {"claim_ids": (), "graph_evidence_ids": (), "parent_ids": ()}
    payload = outcome.payload
    # Solo i bucket resi: audit e rejected non sono risultati, e includerli
    # gonfierebbe l'overlap con oggetti che il gate ha escluso.
    shown = payload.primary_ranked_results + payload.retained_with_warning
    return {
        "claim_ids": tuple(sorted({item.claim_id for item in shown})),
        "graph_evidence_ids": tuple(sorted({item.graph_evidence_id for item in shown})),
        "parent_ids": tuple(sorted({item.parent_id for item in shown if item.parent_id})),
    }


@dataclass(frozen=True)
class DualRunDiagnostic:
    """Una riga di diagnostica: due esecuzioni, e dove differiscono."""

    query_id: str
    legacy_normalized_query: dict[str, Any] = field(default_factory=dict)
    v3_normalized_query: dict[str, Any] = field(default_factory=dict)
    legacy_candidate_ids: tuple[str, ...] = ()
    legacy_graph_evidence_ids: tuple[str, ...] = ()
    v3_claim_ids: tuple[str, ...] = ()
    v3_parent_ids: tuple[str, ...] = ()
    v3_graph_evidence_ids: tuple[str, ...] = ()
    v3_bucket_counts: dict[str, int] = field(default_factory=dict)
    graph_evidence_overlap: tuple[str, ...] = ()
    legacy_only_graph_evidence: tuple[str, ...] = ()
    v3_only_graph_evidence: tuple[str, ...] = ()
    warnings: dict[str, list[str]] = field(default_factory=dict)
    latency_ms: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    gold_metrics_computed: bool = False
    diagnostic_version: str = DIAGNOSTIC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostic_version": self.diagnostic_version,
            "errors": dict(self.errors),
            "gold_metrics_computed": False,
            "graph_evidence_overlap": list(self.graph_evidence_overlap),
            "latency_ms": dict(self.latency_ms),
            "legacy_candidate_ids": list(self.legacy_candidate_ids),
            "legacy_graph_evidence_ids": list(self.legacy_graph_evidence_ids),
            "legacy_normalized_query": dict(self.legacy_normalized_query),
            "legacy_only_graph_evidence": list(self.legacy_only_graph_evidence),
            "query_id": self.query_id,
            "v3_bucket_counts": dict(self.v3_bucket_counts),
            "v3_claim_ids": list(self.v3_claim_ids),
            "v3_graph_evidence_ids": list(self.v3_graph_evidence_ids),
            "v3_normalized_query": dict(self.v3_normalized_query),
            "v3_only_graph_evidence": list(self.v3_only_graph_evidence),
            "v3_parent_ids": list(self.v3_parent_ids),
            "warnings": {key: list(value) for key, value in sorted(self.warnings.items())},
        }


def _run(
    pipeline: EvidenceRetrievalPipeline, query: Mapping[str, Any], backend: str
) -> tuple[RetrievalOutcome | None, str]:
    """Esegue un backend e cattura l'errore invece di propagarlo.

    Il dual-run deve produrre una riga anche quando uno dei due lati fallisce:
    e' proprio il caso in cui il confronto serve di piu'. L'errore viaggia nella
    riga, non nello stack.
    """
    try:
        return pipeline.run(query, retrieval_backend=backend), ""
    except Exception as error:  # noqa: BLE001 - registrato nella riga diagnostica
        return None, f"{type(error).__name__}: {error}"


def diagnose(
    query: Mapping[str, Any],
    *,
    pipeline: EvidenceRetrievalPipeline | None = None,
    legacy_query: Mapping[str, Any] | None = None,
) -> DualRunDiagnostic:
    """Esegue entrambi i backend sulla stessa domanda e ne misura la divergenza.

    `legacy_query` esiste perche' i due backend accettano vocabolari diversi: il
    legacy vuole `biomarkers`/`disease_aliases`, il V3 vuole `gene`/`alteration`.
    Tradurre automaticamente l'uno nell'altro significherebbe inventare la meta'
    dei campi; chi vuole confrontare le due normalizzazioni le scrive entrambe.
    """
    runner = pipeline or EvidenceRetrievalPipeline()
    legacy_payload = dict(legacy_query if legacy_query is not None else query)

    legacy_outcome, legacy_error = _run(runner, legacy_payload, BACKEND_LEGACY)
    v3_outcome, v3_error = _run(runner, query, BACKEND_QUALIFIED_CLAIM_V3)

    legacy_graph = set(_legacy_graph_ids(legacy_outcome))
    v3_ids = _v3_ids(v3_outcome)
    v3_graph = set(v3_ids["graph_evidence_ids"])

    errors = {name: text for name, text in (("legacy", legacy_error), ("v3", v3_error)) if text}
    warnings: dict[str, list[str]] = {}
    if legacy_outcome is not None:
        warnings["legacy"] = sorted(
            {
                warning
                for result in getattr(legacy_outcome.payload, "all_results", ())
                for warning in getattr(result, "warnings", ()) or ()
            }
        )
    if v3_outcome is not None:
        warnings["v3"] = list(v3_outcome.payload.warnings)

    return DualRunDiagnostic(
        query_id=str(query.get("query_id") or ""),
        legacy_normalized_query=(
            runner.backend(BACKEND_LEGACY).build_native_query(legacy_payload).as_dict()
            if legacy_outcome is not None
            else {}
        ),
        v3_normalized_query=(
            v3_outcome.payload.query["normalized"] if v3_outcome is not None else {}
        ),
        legacy_candidate_ids=_legacy_candidate_ids(legacy_outcome),
        legacy_graph_evidence_ids=tuple(sorted(legacy_graph)),
        v3_claim_ids=v3_ids["claim_ids"],
        v3_parent_ids=v3_ids["parent_ids"],
        v3_graph_evidence_ids=v3_ids["graph_evidence_ids"],
        v3_bucket_counts=(
            v3_outcome.payload.bucket_counts() if v3_outcome is not None else {}
        ),
        graph_evidence_overlap=tuple(sorted(legacy_graph & v3_graph)),
        legacy_only_graph_evidence=tuple(sorted(legacy_graph - v3_graph)),
        v3_only_graph_evidence=tuple(sorted(v3_graph - legacy_graph)),
        warnings=warnings,
        latency_ms={
            "legacy": legacy_outcome.latency_ms if legacy_outcome is not None else -1,
            "v3": v3_outcome.latency_ms if v3_outcome is not None else -1,
        },
        errors=errors,
    )


def diagnose_all(
    queries: Sequence[Mapping[str, Any]],
    *,
    pipeline: EvidenceRetrievalPipeline | None = None,
    legacy_queries: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[DualRunDiagnostic, ...]:
    """Il dual-run su un insieme di query, nell'ordine in cui sono date."""
    runner = pipeline or EvidenceRetrievalPipeline()
    lookup = dict(legacy_queries or {})
    return tuple(
        diagnose(
            query,
            pipeline=runner,
            legacy_query=lookup.get(str(query.get("query_id") or "")),
        )
        for query in queries
    )


def as_jsonl(rows: Sequence[DualRunDiagnostic]) -> str:
    """Le righe in JSONL, ordinate e senza spazi variabili."""
    return "".join(
        json.dumps(row.to_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        for row in rows
    )


def diagnostic_contract() -> dict[str, Any]:
    """Descrizione serializzabile della modalita', per gli artefatti della fase."""
    return {
        "compared_on": "graph_evidence_record_id",
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "gold_metrics_computed": False,
        "gold_read": False,
        "legacy_and_v3_result_counts_compared": False,
        "mode_name": MODE_NAME,
        "offline": True,
        "prepares_rerun_does_not_evaluate_it": True,
        "recorded_fields": [
            "legacy_normalized_query",
            "v3_normalized_query",
            "legacy_candidate_ids",
            "v3_parent_ids",
            "v3_claim_ids",
            "v3_bucket_counts",
            "graph_evidence_overlap",
            "legacy_only_graph_evidence",
            "v3_only_graph_evidence",
            "warnings",
            "latency_ms",
            "errors",
        ],
        "v3_buckets_compared": ["primary_ranked_results", "retained_with_warning"],
    }


__all__ = [
    "DIAGNOSTIC_VERSION",
    "MODE_NAME",
    "DualRunDiagnostic",
    "as_jsonl",
    "diagnose",
    "diagnose_all",
    "diagnostic_contract",
]
