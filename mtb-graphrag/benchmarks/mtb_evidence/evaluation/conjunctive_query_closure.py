"""Misure della chiusura direzionale delle query congiuntive.

La fase precedente ha corretto l'asse del biomarcatore insegnandogli a leggere
gli operatori, e nel farlo ha adottato una regola sola per le congiunzioni: i
termini del claim contenuti in quelli della query bastano. Questo modulo misura
quali claim quella regola raggiungeva, dove finiscono ora che la direzione del
contenimento decide il bucket, e che cosa non si muove.

Le misure sono differenziali e a due gate, come nella fase precedente: il
"prima" non viene riletto da un artefatto ma prodotto adesso dal retriever
costruito con il gate 1.2, sullo stesso corpus e con le stesse query. Due
esecuzioni che differiscono per una cosa sola.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.shadow import biomarker_expression as BIO
from backend.pipeline.evidence.shadow import biomarker_query_direction as DIR
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE_V12
from backend.pipeline.evidence.shadow import integrated_gates_v13 as GATE_V13
from benchmarks.mtb_evidence.evaluation import retriever_regression_closure as CLOSURE

# Riesportato: i test della fase citano la fase precedente attraverso questo
# modulo invece di importarla due volte.
CLOSURE = CLOSURE

PHASE_VERSION = "v3-conjunctive-query-closure/1.0"
SUPERSEDES = "v3-retriever-regression-closure/1.0"

# Il match type che il 1.3 sostituisce. Non e' stato rinominato: e' stato diviso
# in due esiti con direzioni opposte.
SUPERSEDED_MATCH_TYPE = BIO.MATCH_CONJUNCTION_SATISFIED

REGRESSION_ENDPOINTS = CLOSURE.REGRESSION_ENDPOINTS

# Le query che questa fase aggiunge alle diciotto precedenti. Ognuna copre una
# riga della tabella direzionale che nessuna delle altre esercitava.
EXTRA_QUERIES = (
    {
        "query_id": "CQ-01-CLAIM-REQUIRES-ADDITIONAL",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR T790M AND EGFR Exon 19 Deletion",
        "disease": "NSCLC",
        "expectation": (
            "evidence:1396 chiede anche C797S, che la query non afferma: parla di "
            "un'altra popolazione e resta respinto."
        ),
    },
    {
        "query_id": "CQ-02-PARTIAL-OVERLAP",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR T790M AND EGFR C797S",
        "disease": "NSCLC",
        "expectation": (
            "Gli insiemi si intersecano senza contenersi: nessuna delle due "
            "espressioni descrive l'altra, e l'esito e' respinto."
        ),
    },
    {
        "query_id": "CQ-03-DISJUNCTIVE-CLAIM",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR L858R AND EGFR Exon 19 Deletion",
        "disease": "NSCLC",
        "expectation": (
            "evidence:11219 e' disgiuntivo sotto una query congiuntiva: descrive "
            "l'una o l'altra alterazione, mai le due insieme, e resta warning."
        ),
    },
)


def closure_queries() -> tuple[dict[str, Any], ...]:
    """Le diciotto della fase precedente piu' le tre di questa."""
    return tuple(CLOSURE.closure_queries()) + EXTRA_QUERIES


def query_payload(query: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in query.items() if key != "expectation"}


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def retrievers() -> tuple[Any, Any]:
    """Il retriever prima e dopo. Stesso corpus, stessi pesi, gate diverso."""
    before = V3.QualifiedClaimRetrieverV3.from_registry(gate=GATE_V12)
    after = V3.QualifiedClaimRetrieverV3.from_registry(gate=GATE_V13)
    return before, after


def _match_type(item: Any) -> str:
    trace = item.gate_trace or {}
    return str((trace.get("biomarker_match") or {}).get("match_type") or "")


def delta_rows() -> list[dict[str, Any]]:
    """Una riga per ogni claim che cambia match type o bucket.

    E' il delta che la chiusura chiede: identificatore, i due match type, i due
    bucket e i codici con cui il nuovo esito si giustifica.
    """
    before, after = retrievers()
    rows: list[dict[str, Any]] = []
    for query in closure_queries():
        payload = query_payload(query)
        old = {item.claim_id: item for item in before.retrieve(payload).all_results}
        new = {item.claim_id: item for item in after.retrieve(payload).all_results}
        for claim_id in sorted(old):
            was, now = old[claim_id], new[claim_id]
            old_match, new_match = _match_type(was), _match_type(now)
            if was.bucket == now.bucket and old_match == new_match:
                continue
            trace = now.gate_trace or {}
            rows.append(
                {
                    "claim_id": claim_id,
                    "graph_evidence_id": now.graph_evidence_id,
                    "new_bucket": now.bucket,
                    "new_match_type": new_match,
                    "old_bucket": was.bucket,
                    "old_match_type": old_match,
                    "phase_version": PHASE_VERSION,
                    "query_id": query["query_id"],
                    "reason_codes": list(now.reason_codes),
                    "reclassified_from_superseded_rule": old_match
                    == SUPERSEDED_MATCH_TYPE,
                    "warnings": list(now.warnings),
                }
            )
    return rows


def superseded_cohort() -> dict[str, Any]:
    """I claim che la regola sostituita raggiungeva, e dove finiscono.

    La coorte e' definita dal match type che il 1.2 assegnava, non dal bucket:
    un claim che il contenimento raggiungeva ma che un altro gate teneva gia' in
    audit fa parte della coorte tanto quanto uno che finiva fra i primari, e
    contarne solo i secondi darebbe una riclassificazione piu' piccola di quella
    avvenuta.
    """
    before, after = retrievers()
    claims: dict[str, dict[str, Any]] = {}
    per_query: dict[str, int] = {}
    for query in closure_queries():
        payload = query_payload(query)
        old = {item.claim_id: item for item in before.retrieve(payload).all_results}
        new = {item.claim_id: item for item in after.retrieve(payload).all_results}
        hits = [
            claim_id
            for claim_id, item in old.items()
            if _match_type(item) == SUPERSEDED_MATCH_TYPE
        ]
        if hits:
            per_query[query["query_id"]] = len(hits)
        for claim_id in hits:
            claims.setdefault(
                claim_id,
                {
                    "claim_id": claim_id,
                    "graph_evidence_id": new[claim_id].graph_evidence_id,
                    "new_bucket": new[claim_id].bucket,
                    "new_match_type": _match_type(new[claim_id]),
                    "old_bucket": old[claim_id].bucket,
                    "queries": [],
                },
            )["queries"].append(query["query_id"])

    def tally(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in claims.values():
            counts[row[key]] = counts.get(row[key], 0) + 1
        return dict(sorted(counts.items()))

    return {
        "claims": sorted(claims.values(), key=lambda row: row["claim_id"]),
        "distinct_claims": len(claims),
        "new_bucket_tally": tally("new_bucket"),
        "new_match_type_tally": tally("new_match_type"),
        "none_reaches_primary": all(
            row["new_bucket"] != RESULT.PRIMARY_BUCKET for row in claims.values()
        ),
        "old_bucket_tally": tally("old_bucket"),
        "per_query_hits": dict(sorted(per_query.items())),
        "phase_version": PHASE_VERSION,
        "superseded_match_type": SUPERSEDED_MATCH_TYPE,
        "supersedes": SUPERSEDES,
    }


def endpoint_rows() -> list[dict[str, Any]]:
    """Gli endpoint protetti sotto entrambi i gate, query per query."""
    before, after = retrievers()
    rows: list[dict[str, Any]] = []
    for query in closure_queries():
        payload = query_payload(query)
        old = {item.claim_id: item for item in before.retrieve(payload).all_results}
        for item in after.retrieve(payload).all_results:
            if item.graph_evidence_id not in REGRESSION_ENDPOINTS:
                continue
            if not item.claim_id.startswith("CLM-"):
                continue
            was = old[item.claim_id]
            rows.append(
                {
                    "claim_id": item.claim_id,
                    "graph_evidence_id": item.graph_evidence_id,
                    "new_bucket": item.bucket,
                    "new_match_type": _match_type(item),
                    "old_bucket": was.bucket,
                    "old_match_type": _match_type(was),
                    "query_id": query["query_id"],
                    "unchanged": was.bucket == item.bucket,
                }
            )
    return sorted(rows, key=lambda row: (row["query_id"], row["graph_evidence_id"]))


def query_rows() -> list[dict[str, Any]]:
    """Una riga per query: conteggi e digest delle assegnazioni, prima e dopo."""
    before, after = retrievers()
    rows: list[dict[str, Any]] = []
    for query in closure_queries():
        payload = query_payload(query)
        old = before.retrieve(payload)
        new = after.retrieve(payload)
        old_assignment = {i.claim_id: i.bucket for i in old.all_results}
        new_assignment = {i.claim_id: i.bucket for i in new.all_results}
        rows.append(
            {
                "bucket_assignment_digest_after": _digest(new_assignment),
                "bucket_assignment_digest_before": _digest(old_assignment),
                "bucket_counts_after": new.bucket_counts(),
                "bucket_counts_before": old.bucket_counts(),
                "decisions_unchanged": old_assignment == new_assignment,
                "expectation": query.get("expectation", ""),
                "gate_version_after": after.gate_version,
                "gate_version_before": before.gate_version,
                "normalized_biomarker": new.query["normalized"][
                    "normalized_biomarker"
                ],
                "phase_version": PHASE_VERSION,
                "query_id": query["query_id"],
                "query_operator": BIO.canonical(
                    new.query["normalized"]["normalized_biomarker"]
                ).operator,
                "supersedes": SUPERSEDES,
            }
        )
    return rows


# Le coppie che la chiusura nomina una per una. Sono qui e non nel test perche'
# l'artefatto deve poterle mostrare senza eseguire la suite.
DIRECTIONAL_CASES = (
    ("EGFR L858R AND EGFR T790M", "EGFR L858R AND EGFR T790M", "1 stesso insieme"),
    ("EGFR T790M AND EGFR L858R", "EGFR L858R AND EGFR T790M", "1 ordine invertito"),
    (
        "EGFR L858R AND EGFR T790M AND EGFR L858R",
        "EGFR L858R AND EGFR T790M",
        "1 duplicati",
    ),
    ("EGFR L858R AND EGFR T790M", "EGFR L858R", "2 claim A"),
    ("EGFR L858R AND EGFR T790M", "EGFR T790M", "2 claim B"),
    (
        "EGFR L858R AND EGFR T790M",
        "EGFR L858R AND EGFR T790M AND EGFR C797S",
        "3 il claim chiede un congiunto in piu'",
    ),
    (
        "EGFR L858R AND EGFR T790M",
        "EGFR L858R AND EGFR C797S",
        "4 overlap parziale",
    ),
    (
        "EGFR L858R AND EGFR T790M",
        "EGFR L858R OR EGFR T790M",
        "5 claim disgiuntivo",
    ),
    (
        "EGFR L858R AND EGFR T790M",
        "EGFR L858R AND EGFR T790M OR EGFR C797S",
        "6 espressione mista",
    ),
    (
        "EGFR L858R",
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "query non congiuntiva: decisa dal 1.2",
    ),
    (
        "EGFR L858R",
        "EGFR L858R AND EGFR T790M",
        "query non congiuntiva: decisa dal 1.2",
    ),
)


def semantics_audit() -> dict[str, Any]:
    """Il contratto direzionale e le sue coppie."""
    return {
        "cases": [
            dict(DIR.describe(query, claim))
            | {"claim": claim, "query": query, "scenario": scenario}
            for query, claim, scenario in DIRECTIONAL_CASES
        ],
        "contract": DIR.directional_semantics_contract(),
        "gate_contract": GATE_V13.gate_contract(),
        "phase_version": PHASE_VERSION,
        "result_schema_after": RESULT.result_schema(GATE_V13),
        "result_schema_before": RESULT.result_schema(GATE_V12),
        "supersedes": SUPERSEDES,
    }


def scope() -> dict[str, Any]:
    """Che cosa questa fase ha guardato, e che cosa ha lasciato fermo."""
    before, after = retrievers()
    rows = query_rows()
    return {
        "corpus_hash": after.corpus_hash,
        "corpus_unchanged": before.corpus_hash == after.corpus_hash,
        "frozen_in_this_phase": [
            "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/",
            "backend/pipeline/evidence/qualified_retriever.py",
            "backend/pipeline/evidence/shadow/biomarker_expression.py",
            "backend/pipeline/evidence/shadow/integrated_gates.py",
            "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
            "backend/pipeline/evidence/shadow/integrated_gates_v12.py",
            "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
            "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/",
            "benchmarks/mtb_evidence/v3/retriever_binding_1_4/",
            "benchmarks/mtb_evidence/v3/retriever_regression_closure/",
        ],
        "gate_after": after.gate_version,
        "gate_before": before.gate_version,
        "gold_read": False,
        "phase_version": PHASE_VERSION,
        "queries": [row["query_id"] for row in rows],
        "queries_with_changed_decisions": sorted(
            row["query_id"] for row in rows if not row["decisions_unchanged"]
        ),
        "query_count": len(rows),
        "regression_endpoints": list(REGRESSION_ENDPOINTS),
        "repository_version": after.repository_version,
        "scoring_weights_retuned": False,
        "supersedes": SUPERSEDES,
    }


__all__ = [
    "DIRECTIONAL_CASES",
    "EXTRA_QUERIES",
    "PHASE_VERSION",
    "REGRESSION_ENDPOINTS",
    "SUPERSEDED_MATCH_TYPE",
    "SUPERSEDES",
    "closure_queries",
    "delta_rows",
    "endpoint_rows",
    "query_payload",
    "query_rows",
    "retrievers",
    "scope",
    "semantics_audit",
    "superseded_cohort",
]
