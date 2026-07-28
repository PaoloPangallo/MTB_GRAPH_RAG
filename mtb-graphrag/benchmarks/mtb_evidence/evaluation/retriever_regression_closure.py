"""Misure della chiusura delle regressioni del retriever V3.

La fase precedente ha lasciato aperta una discrepanza: `evidence:11219`, che
porta `EGFR L858R OR EGFR Exon 19 Deletion`, finiva fra i respinti su una query
`EGFR L858R`. Questo modulo misura che cosa cambia quando l'asse del
biomarcatore impara a leggere l'operatore, e che cosa **non** cambia.

Le misure sono tutte differenziali e tutte a due gate. Il "prima" non viene
riletto da un artefatto — verrebbe da una fase chiusa e non sarebbe
ricalcolabile — ma prodotto adesso dal retriever costruito con il gate 1.1,
sullo stesso corpus e con le stesse query. E' l'unico modo in cui la differenza
misurata e' attribuibile al gate e a nient'altro: due esecuzioni che
differiscono per una sola cosa.

Il corpus promosso non viene toccato, i pesi non vengono riletti in modo diverso
e il gold non compare in nessun percorso di questo modulo.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.shadow import biomarker_expression as BIO
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE_V11
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE_V12
from benchmarks.mtb_evidence.evaluation import retriever_binding_1_4 as BINDING

CLOSURE_VERSION = "v3-retriever-regression-closure/1.0"
SUPERSEDES = "v3-retriever-binding/1.4"

# Gli endpoint nominati dalla richiesta di chiusura. Non sono "i casi che
# funzionano": sono i casi in cui il retriever puo' sbagliare in modo silenzioso,
# e per ognuno l'artefatto registra dove finisce sotto entrambi i gate.
REGRESSION_ENDPOINTS = (
    "evidence:11219",
    "evidence:11598",
    "evidence:11599",
    "evidence:1867",
    "evidence:8173",
    "evidence:1846",
    "evidence:1847",
)

# La query da cui la discrepanza e' stata osservata, e quella che la fa vedere
# sotto una relazione di malattia diversa.
QUERY_11219 = "RB-01-EGFR-L858R-NSCLC"
QUERY_11219_PARENT = "RB-02-EGFR-L858R-LUAD"

# La query in cui `evidence:8173` mostra tutti e tre gli esiti insieme: relazione
# di malattia sibling, biomarcatore incompatibile, bucket finale respinto.
QUERY_8173 = "RB-04-FGFR2-ICCA"

# Una query fuori dalle quattordici, necessaria perche' nessuna di quelle chiede
# `EGFR T790M` da solo, che e' l'unico modo di far vedere `evidence:1867`
# primario e le due congiunzioni respinte per la ragione giusta.
EXTRA_QUERIES = (
    {
        "query_id": "RC-01-EGFR-T790M-NSCLC",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR T790M",
        "disease": "Lung Non-small Cell Carcinoma",
        "expectation": (
            "evidence:1867 e' l'unico claim atomico su T790M e resta primary; le "
            "congiunzioni che contengono T790M restano respinte."
        ),
    },
    {
        "query_id": "RC-02-EGFR-EXON19-NSCLC",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR Exon 19 Deletion",
        "disease": "NSCLC",
        "expectation": (
            "L'altro disgiunto della stessa espressione raggiunge gli stessi claim "
            "del primo: la disgiunzione non privilegia il membro scritto per primo."
        ),
    },
    {
        "query_id": "RC-03-EGFR-L858R-AND-T790M",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR L858R AND EGFR T790M",
        "disease": "NSCLC",
        "expectation": (
            "La congiunzione interamente soddisfatta raggiunge evidence:11599. Un "
            "claim che richiede un solo membro e' soddisfatto anche lui, perche' la "
            "query afferma che quell'alterazione c'e': evidence:1867 diventa "
            "raggiungibile. Il verso opposto resta chiuso — evidence:11598 chiede "
            "Exon 19 Deletion, che questa query non afferma, e resta respinto."
        ),
    },
    {
        "query_id": "RC-04-EGFR-T790M-AND-L858R",
        "claim_domain": "therapeutic",
        "biomarker": "EGFR T790M AND EGFR L858R",
        "disease": "NSCLC",
        "expectation": (
            "La stessa congiunzione in ordine invertito da' esattamente lo stesso "
            "esito, decisione per decisione: l'identita' di un'espressione e' "
            "l'insieme dei suoi termini, non la stringa."
        ),
    },
)

ARBITRARILY_HIGH_SCORE = BINDING.ARBITRARILY_HIGH_SCORE


def closure_queries() -> tuple[dict[str, Any], ...]:
    """Le quattordici della fase precedente piu' le quattro di questa."""
    return tuple(BINDING.REGRESSION_QUERIES) + EXTRA_QUERIES


def query_payload(query: Mapping[str, Any]) -> dict[str, Any]:
    """La query senza il campo di attesa, che non fa parte della domanda."""
    return {key: value for key, value in query.items() if key != "expectation"}


def _digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def retrievers() -> tuple[Any, Any]:
    """Il retriever prima e dopo. Stesso corpus, stessi pesi, gate diverso."""
    before = V3.QualifiedClaimRetrieverV3.from_registry(gate=GATE_V11)
    after = V3.QualifiedClaimRetrieverV3.from_registry(gate=GATE_V12)
    return before, after


def bucket_assignment(result: Any) -> dict[str, str]:
    """Dove e' finito ogni oggetto. E' la decisione, spogliata di tutto il resto.

    Serve perche' il digest canonico del risultato include la traccia dei gate,
    che sotto il 1.2 esiste e sotto il 1.1 no: due digest diversi non dicono se
    le decisioni siano cambiate. Questa mappa si'.
    """
    return {item.claim_id: item.bucket for item in result.all_results}


def endpoint_rows(result: Any, *, gate_version: str, query_id: str) -> list[dict[str, Any]]:
    """Dove e' finito ogni endpoint protetto, e per decisione di quale gate."""
    rows: list[dict[str, Any]] = []
    for item in result.all_results:
        if item.graph_evidence_id not in REGRESSION_ENDPOINTS:
            continue
        trace = item.gate_trace or {}
        biomarker = dict(trace.get("biomarker_match") or {})
        rows.append(
            {
                "biomarker_match_type": str(biomarker.get("match_type") or ""),
                "bucket": item.bucket,
                "claim_id": item.claim_id,
                "claim_type": item.claim_type,
                "disease_relation": item.provenance["disease_relation_provenance"][
                    "relation_type"
                ],
                "dominant_gate": str(trace.get("dominant_gate") or ""),
                "gate_local_buckets": dict(trace.get("gate_local_buckets") or {}),
                "gate_version": gate_version,
                "graph_evidence_id": item.graph_evidence_id,
                "query_id": query_id,
                "ranking_score_allowed": bool(item.score.get("ranking_score_allowed")),
                "reason_codes": list(item.reason_codes),
            }
        )
    return sorted(rows, key=lambda row: (row["graph_evidence_id"], row["claim_id"]))


def regression_rows() -> list[dict[str, Any]]:
    """Una riga per query: conteggi, decisioni e endpoint, prima e dopo."""
    before, after = retrievers()
    rows: list[dict[str, Any]] = []
    for query in closure_queries():
        payload = query_payload(query)
        old = before.retrieve(payload)
        new = after.retrieve(payload)
        old_assignment = bucket_assignment(old)
        new_assignment = bucket_assignment(new)
        moved = {
            claim_id: {
                "after": new_assignment[claim_id],
                "before": bucket,
            }
            for claim_id, bucket in sorted(old_assignment.items())
            if new_assignment.get(claim_id) != bucket
        }
        rows.append(
            {
                "bucket_assignment_digest_after": _digest(new_assignment),
                "bucket_assignment_digest_before": _digest(old_assignment),
                "bucket_counts_after": new.bucket_counts(),
                "bucket_counts_before": old.bucket_counts(),
                "closure_version": CLOSURE_VERSION,
                "decisions_unchanged": not moved,
                "endpoints_after": endpoint_rows(
                    new, gate_version=after.gate_version, query_id=query["query_id"]
                ),
                "endpoints_before": endpoint_rows(
                    old, gate_version=before.gate_version, query_id=query["query_id"]
                ),
                "expectation": query.get("expectation", ""),
                "gate_version_after": after.gate_version,
                "gate_version_before": before.gate_version,
                "moved_claims": moved,
                "normalized_biomarker": new.query["normalized"]["normalized_biomarker"],
                "query_id": query["query_id"],
                "result_digest_after": new.canonical_digest(),
                "result_digest_before": old.canonical_digest(),
                "supersedes": SUPERSEDES,
            }
        )
    return rows


def gate_trace_for(
    graph_evidence_id: str, query_id: str
) -> dict[str, Any]:
    """La traccia completa di un endpoint su una query, prima e dopo.

    Include la query normalizzata e quella originale: la richiesta di chiusura
    chiede di poter ricostruire *quale domanda* ha prodotto l'esito, e una
    traccia che non riportasse la query costringerebbe a fidarsi del titolo.
    """
    before, after = retrievers()
    query = next(
        item for item in closure_queries() if item["query_id"] == query_id
    )
    payload = query_payload(query)
    old = before.retrieve(payload)
    new = after.retrieve(payload)

    def claims(result: Any) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in result.all_results
            if item.graph_evidence_id == graph_evidence_id
        ]

    return {
        "after": {
            "claims": claims(new),
            "gate_version": after.gate_version,
            "result_schema_version": after.result_schema_version,
        },
        "before": {
            "claims": claims(old),
            "gate_version": before.gate_version,
            "result_schema_version": before.result_schema_version,
        },
        "closure_version": CLOSURE_VERSION,
        "expectation": query.get("expectation", ""),
        "graph_evidence_id": graph_evidence_id,
        "normalized_query": new.query["normalized"],
        "original_query": new.query["original"],
        "query_id": query_id,
        "supersedes": SUPERSEDES,
    }


def boolean_semantics_rows() -> list[dict[str, Any]]:
    """Ogni espressione booleana del corpus, letta dal parser.

    Non e' una lista di casi scelti: e' l'inventario completo, cosi' che
    un'espressione con una forma imprevista non possa passare inosservata.
    """
    _, after = retrievers()
    seen: dict[str, dict[str, Any]] = {}
    for _obj, record in after._objects:  # noqa: SLF001 - inventario, non retrieval
        literal = str(record.get("biomarker") or "")
        if not literal or literal in seen:
            continue
        expression = BIO.canonical(literal)
        seen[literal] = {
            "graph_evidence_id": str(record.get("graph_evidence_id") or ""),
            "interpretable": expression.is_interpretable,
            "literal": literal,
            "operator": expression.operator,
            "term_count": len(expression.terms),
            "terms": list(expression.terms),
        }
    return sorted(seen.values(), key=lambda row: row["literal"])


# Le coppie che la richiesta di chiusura nomina una per una, piu' quelle che
# proteggono i segnaposto. Sono scritte qui e non nel test perche' l'artefatto
# deve poterle mostrare senza eseguire la suite.
SEMANTICS_CASES = (
    ("EGFR L858R", "EGFR L858R OR EGFR Exon 19 Deletion", "A OR B con query A"),
    (
        "EGFR Exon 19 Deletion",
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "A OR B con query B",
    ),
    (
        "EGFR Exon 19 Deletion OR EGFR L858R",
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "A OR B con query B OR A: ordine invertito",
    ),
    (
        "EGFR L858R OR EGFR Exon 19 Deletion OR EGFR L858R",
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "A OR B con query duplicata",
    ),
    ("EGFR L858R", "EGFR L858R AND EGFR T790M", "A AND B con solo A"),
    ("EGFR T790M", "EGFR L858R AND EGFR T790M", "A AND B con solo B"),
    (
        "EGFR L858R AND EGFR T790M",
        "EGFR L858R AND EGFR T790M",
        "A AND B con A+B",
    ),
    (
        "EGFR T790M AND EGFR L858R",
        "EGFR L858R AND EGFR T790M",
        "A AND B con B AND A: ordine invertito",
    ),
    (
        "EGFR L858R AND EGFR T790M AND EGFR L858R",
        "EGFR L858R AND EGFR T790M",
        "A AND B con query duplicata",
    ),
    (
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "EGFR L858R",
        "query disgiuntiva contro claim singolo",
    ),
    (
        "FGFR2::BICC1 Fusion",
        "FGFR2::v Fusion OR FGFR2::? Fusion",
        "i segnaposto v e ? non sono wildcard",
    ),
    (
        "EGFR L858R",
        "EGFR L858R AND EGFR T790M OR EGFR C797S",
        "espressione mista: non interpretabile",
    ),
    (
        "EGFR L858R",
        "(EGFR L858R OR EGFR T790M) AND EGFR C797S",
        "espressione annidata: non interpretabile",
    ),
)


def semantics_audit() -> dict[str, Any]:
    """Il contratto della semantica booleana, le sue coppie e l'inventario."""
    return {
        "cases": [
            dict(BIO.describe(query, claim))
            | {"claim": claim, "query": query, "scenario": scenario}
            for query, claim, scenario in SEMANTICS_CASES
        ],
        "closure_version": CLOSURE_VERSION,
        "contract": BIO.boolean_semantics_contract(),
        "corpus_expressions": boolean_semantics_rows(),
        "gate_contract": GATE_V12.gate_contract(),
        "result_schema_after": RESULT.result_schema(GATE_V12),
        "result_schema_before": RESULT.result_schema(GATE_V11),
        "supersedes": SUPERSEDES,
    }


def scope() -> dict[str, Any]:
    """Che cosa questa fase ha guardato, e che cosa ha lasciato fermo."""
    before, after = retrievers()
    return {
        "closure_version": CLOSURE_VERSION,
        "corpus_hash": after.corpus_hash,
        "corpus_unchanged": before.corpus_hash == after.corpus_hash,
        "frozen_in_this_phase": [
            "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/",
            "backend/pipeline/evidence/qualified_retriever.py",
            "backend/pipeline/evidence/qualified_retrieval_scoring.py",
            "backend/pipeline/evidence/shadow/integrated_gates.py",
            "backend/pipeline/evidence/shadow/integrated_gates_v11.py",
            "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
            "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/",
            "benchmarks/mtb_evidence/v3/retriever_binding_1_4/",
        ],
        "gate_after": after.gate_version,
        "gate_before": before.gate_version,
        "gold_read": False,
        "queries": [item["query_id"] for item in closure_queries()],
        "query_count": len(closure_queries()),
        "regression_endpoints": list(REGRESSION_ENDPOINTS),
        "repository_version": after.repository_version,
        "scoring_weights_retuned": False,
        "supersedes": SUPERSEDES,
        "questions": [
            {
                "answered_by": "evidence_11219_gate_trace.json",
                "question": "Quale gate ha respinto evidence:11219 su EGFR L858R?",
            },
            {
                "answered_by": "biomarker_boolean_semantics_audit.json",
                "question": "La semantica OR e' corretta o errata?",
            },
            {
                "answered_by": "regression_results.jsonl",
                "question": "Che cosa cambia, e che cosa resta fermo, sulle diciotto query?",
            },
            {
                "answered_by": "evidence_8173_gate_trace.json",
                "question": (
                    "Il bucket finale di evidence:8173 conserva la relazione di "
                    "malattia e nomina il gate dominante?"
                ),
            },
        ],
    }


__all__ = [
    "ARBITRARILY_HIGH_SCORE",
    "CLOSURE_VERSION",
    "EXTRA_QUERIES",
    "QUERY_11219",
    "QUERY_11219_PARENT",
    "QUERY_8173",
    "REGRESSION_ENDPOINTS",
    "SEMANTICS_CASES",
    "SUPERSEDES",
    "boolean_semantics_rows",
    "bucket_assignment",
    "closure_queries",
    "endpoint_rows",
    "gate_trace_for",
    "query_payload",
    "regression_rows",
    "retrievers",
    "scope",
    "semantics_audit",
]
