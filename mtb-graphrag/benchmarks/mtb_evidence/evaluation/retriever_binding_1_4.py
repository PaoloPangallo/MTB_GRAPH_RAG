"""Query di regressione e misure della fase di binding del retriever V3.

Il modulo vive sotto `benchmarks/` e non sotto `backend/` perche' produce
artefatti di valutazione: il runtime non lo importa, e non deve poterlo fare. La
direzione della dipendenza e' una sola — da qui verso il retriever, mai
all'indietro.

Le quattordici query non sono nuove. Le prime nove vengono dalle fasi che le
hanno congelate — la politica di malattia, il fix congiuntivo, la chiusura
terminologica — e le ultime cinque sono i casi limite che quelle fasi hanno
lasciato aperti: due farmaci che il registro delle forme distingue, un codice
sconosciuto, una malattia sconosciuta e una query senza tipo. Riusarle invece di
inventarne di nuove e' cio' che rende questa fase una regressione e non una
misura a se' stante.

Nessuna query e' derivata dal gold, e nessuna misura di questo modulo lo legge.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.retrieval import diagnostics as DIAG
from backend.pipeline.evidence.retrieval import v3_query as QUERY
from backend.pipeline.evidence.retrieval.backends import (
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
    DEFAULT_RETRIEVAL_BACKEND,
    RetrievalBackendConfig,
    UnknownPolicyModeError,
    UnknownRepositoryVersionError,
    UnknownRetrievalBackendError,
)
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline

PHASE = "v3-retriever-binding/1.4"

ARBITRARILY_HIGH_SCORE = 10**9

# --- query di regressione -----------------------------------------------------

# Ogni riga porta l'attesa in forma di descrizione, non di numero: i conteggi
# vengono misurati e scritti negli artefatti, e fissarli qui significherebbe
# scrivere due volte lo stesso fatto in due posti che possono divergere.
REGRESSION_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "query_id": "RB-01-EGFR-L858R-NSCLC",
        "claim_domain": "therapeutic",
        "gene": "EGFR",
        "alteration": "L858R",
        "disease": "NSCLC",
        "expectation": "I letterali NSCLC restano verified alias e primary.",
    },
    {
        "query_id": "RB-02-EGFR-L858R-LUAD",
        "claim_domain": "therapeutic",
        "gene": "EGFR",
        "alteration": "L858R",
        "disease": "Lung Adenocarcinoma",
        "expectation": "I claim NSCLC sono parent della query: warning, mai exact.",
    },
    {
        "query_id": "RB-03-ALK-G1202R-NSCLC",
        "claim_domain": "therapeutic",
        "gene": "ALK",
        "alteration": "G1202R",
        "disease": "NSCLC",
        "expectation": (
            "Alias disease compatibile: l'esclusione, dove avviene, e' del "
            "biomarcatore e non della malattia."
        ),
    },
    {
        "query_id": "RB-04-FGFR2-ICCA",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "expectation": "I claim CCA sono parent della query e restano warning.",
    },
    {
        "query_id": "RB-05-FGFR2-CCA",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Cholangiocarcinoma",
        "expectation": "I claim iCCA sono child della query: warning, mai generalizzati.",
    },
    {
        "query_id": "RB-06-DIAGNOSTIC-FGFR2-BICC1-ICCA",
        "claim_domain": "diagnostic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "expectation": (
            "evidence:1846 e' il claim diagnostico ristretto e resta primary; "
            "i claim terapeutici non entrano in una domanda diagnostica."
        ),
    },
    {
        "query_id": "RB-07-INFIGRATINIB-FGFR2-ICCA",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "interventions": ["infigratinib"],
        "expectation": (
            "evidence:1851 e' raggiunto dal nome canonico e resta aggregato: "
            "warning, mai supporto atomico."
        ),
    },
    {
        "query_id": "RB-08-BGJ398-FGFR2-ICCA",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "interventions": ["BGJ398"],
        "expectation": (
            "Lo stesso claim e' raggiunto dal letterale della fonte, con lo "
            "stesso bucket: la canonicalizzazione non ha reso irraggiungibile "
            "il nome che la fonte usa."
        ),
    },
    {
        "query_id": "RB-09-AUY922",
        "claim_domain": "therapeutic",
        "biomarker": "EML4::ALK Fusion AND ALK C1156Y",
        "disease": "Lung Non-small Cell Carcinoma",
        "interventions": ["AUY922"],
        "expectation": (
            "AUY922 resta unresolved: nessun alias exact viene creato e "
            "l'associazione non risolta resta auditabile."
        ),
    },
    {
        "query_id": "RB-10-INFIGRATINIB-PHOSPHATE",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Cholangiocarcinoma",
        "interventions": ["infigratinib phosphate"],
        "expectation": "Sale verificato della moiety: warning, mai primary.",
    },
    {
        "query_id": "RB-11-INFIGRATINIB-HYDROCHLORIDE",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Cholangiocarcinoma",
        "interventions": ["infigratinib hydrochloride"],
        "expectation": (
            "Suffisso non registrato: relazione irrisolta, audit; nessuna "
            "rimozione automatica del suffisso."
        ),
    },
    {
        "query_id": "RB-12-UNKNOWN-DRUG-CODE",
        "claim_domain": "therapeutic",
        "gene": "EGFR",
        "alteration": "L858R",
        "disease": "NSCLC",
        "interventions": ["ZZZ-999999"],
        "expectation": "Un codice sconosciuto non raggiunge nessun claim primario.",
    },
    {
        "query_id": "RB-13-UNKNOWN-DISEASE",
        "claim_domain": "therapeutic",
        "gene": "EGFR",
        "alteration": "L858R",
        "disease": "Klingon Sarcoma",
        "expectation": (
            "Una malattia sconosciuta non e' un alias di nulla: nessun primary, "
            "e nessuna relazione ricostruita per somiglianza."
        ),
    },
    {
        "query_id": "RB-14-UNTYPED-FGFR2-ICCA",
        "claim_domain": "untyped",
        "biomarker": "FGFR2::BICC1 Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "expectation": (
            "Query senza tipo: sezioni separate per dominio, nessun ranking "
            "globale cross-domain."
        ),
    },
)

# La controparte legacy delle query che il retriever operativo sa accettare. Non
# e' una traduzione automatica: il legacy vuole `biomarkers` e `disease_aliases`,
# e dedurli dai campi V3 significherebbe inventare la meta' dei campi.
LEGACY_QUERIES: dict[str, dict[str, Any]] = {
    "RB-01-EGFR-L858R-NSCLC": {
        "query_id": "RB-01-EGFR-L858R-NSCLC",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "NSCLC",
        "disease_aliases": ["Lung Non-small Cell Carcinoma"],
    },
    "RB-02-EGFR-L858R-LUAD": {
        "query_id": "RB-02-EGFR-L858R-LUAD",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "Lung Adenocarcinoma",
    },
    "RB-03-ALK-G1202R-NSCLC": {
        "query_id": "RB-03-ALK-G1202R-NSCLC",
        "biomarkers": [{"gene": "ALK", "alteration": "G1202R"}],
        "disease": "NSCLC",
        "disease_aliases": ["Lung Non-small Cell Carcinoma"],
    },
    "RB-04-FGFR2-ICCA": {
        "query_id": "RB-04-FGFR2-ICCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Intrahepatic Cholangiocarcinoma",
    },
    "RB-05-FGFR2-CCA": {
        "query_id": "RB-05-FGFR2-CCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Cholangiocarcinoma",
    },
    "RB-06-DIAGNOSTIC-FGFR2-BICC1-ICCA": {
        "query_id": "RB-06-DIAGNOSTIC-FGFR2-BICC1-ICCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Intrahepatic Cholangiocarcinoma",
    },
    "RB-07-INFIGRATINIB-FGFR2-ICCA": {
        "query_id": "RB-07-INFIGRATINIB-FGFR2-ICCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Intrahepatic Cholangiocarcinoma",
        "interventions": ["infigratinib"],
    },
    "RB-08-BGJ398-FGFR2-ICCA": {
        "query_id": "RB-08-BGJ398-FGFR2-ICCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Intrahepatic Cholangiocarcinoma",
        "interventions": ["BGJ398"],
    },
    "RB-09-AUY922": {
        "query_id": "RB-09-AUY922",
        "biomarkers": [{"gene": "ALK", "alteration": "C1156Y"}],
        "disease": "Lung Non-small Cell Carcinoma",
        "interventions": ["AUY922"],
    },
    "RB-10-INFIGRATINIB-PHOSPHATE": {
        "query_id": "RB-10-INFIGRATINIB-PHOSPHATE",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Cholangiocarcinoma",
        "interventions": ["infigratinib phosphate"],
    },
    "RB-11-INFIGRATINIB-HYDROCHLORIDE": {
        "query_id": "RB-11-INFIGRATINIB-HYDROCHLORIDE",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Cholangiocarcinoma",
        "interventions": ["infigratinib hydrochloride"],
    },
    "RB-12-UNKNOWN-DRUG-CODE": {
        "query_id": "RB-12-UNKNOWN-DRUG-CODE",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "NSCLC",
        "disease_aliases": ["Lung Non-small Cell Carcinoma"],
        "interventions": ["ZZZ-999999"],
    },
    "RB-13-UNKNOWN-DISEASE": {
        "query_id": "RB-13-UNKNOWN-DISEASE",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "Klingon Sarcoma",
    },
    "RB-14-UNTYPED-FGFR2-ICCA": {
        "query_id": "RB-14-UNTYPED-FGFR2-ICCA",
        "biomarkers": [{"gene": "FGFR2", "normalized": "FGFR2::BICC1 Fusion"}],
        "disease": "Intrahepatic Cholangiocarcinoma",
    },
}

# Gli endpoint nominati uno per uno dalle fasi precedenti. Sono i casi in cui il
# retrieval puo' sbagliare in modo silenzioso, e per ognuno l'artefatto registra
# in quale bucket e' finito.
PROTECTED_ENDPOINTS = (
    "evidence:1846",
    "evidence:1847",
    "evidence:1851",
    "evidence:1853",
    "evidence:1867",
    "evidence:841",
    "evidence:8173",
    "evidence:11219",
    "evidence:11240",
    "evidence:11598",
    "evidence:11599",
)


def retrieval_queries() -> tuple[dict[str, Any], ...]:
    """Le query senza il campo di attesa, che non fa parte della domanda."""
    return tuple(
        {key: value for key, value in query.items() if key != "expectation"}
        for query in REGRESSION_QUERIES
    )


# --- misure -------------------------------------------------------------------


def _endpoint_rows(result: Any) -> list[dict[str, Any]]:
    """Dove e' finito ogni endpoint protetto, e perche'."""
    rows: list[dict[str, Any]] = []
    for item in result.all_results:
        if item.graph_evidence_id not in PROTECTED_ENDPOINTS:
            continue
        rows.append(
            {
                "bucket": item.bucket,
                "claim_id": item.claim_id,
                "claim_type": item.claim_type,
                "formulation_relation": item.provenance["formulation_provenance"][
                    "relation_type"
                ],
                "graph_evidence_id": item.graph_evidence_id,
                "intervention_members": list(item.intervention_members),
                "ranking_score_allowed": bool(item.score.get("ranking_score_allowed")),
                "reason_codes": list(item.reason_codes),
                "source_literal_members": list(item.source_literal_members),
                "warnings": list(item.warnings),
            }
        )
    return sorted(rows, key=lambda row: (row["graph_evidence_id"], row["claim_id"]))


def regression_rows(
    pipeline: EvidenceRetrievalPipeline,
) -> list[dict[str, Any]]:
    """Una riga per query: bucket, endpoint protetti, sezioni, determinismo."""
    rows: list[dict[str, Any]] = []
    for query in REGRESSION_QUERIES:
        payload = {key: value for key, value in query.items() if key != "expectation"}
        outcome = pipeline.run(payload, retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3)
        result = outcome.payload
        repeated = pipeline.run(payload, retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3)
        rows.append(
            {
                "backend_name": outcome.backend_name,
                "bucket_counts": result.bucket_counts(),
                "candidate_count": result.candidate_count,
                "corpus_hash": result.corpus_hash,
                "deterministic": result.canonical_digest()
                == repeated.payload.canonical_digest(),
                "expectation": query["expectation"],
                "gate_blocking_counts": dict(
                    result.gate_decisions["blocking_gate_counts"]
                ),
                "policy_mode": result.policy_mode,
                "primary_claim_ids": [
                    item.claim_id for item in result.primary_ranked_results
                ],
                "protected_endpoints": _endpoint_rows(result),
                "query_id": query["query_id"],
                "repository_version": result.repository_version,
                "result_digest": result.canonical_digest(),
                "run_id": result.run_id,
                "sections": {
                    name: len(items) for name, items in result.sections().items()
                },
                "warning_claim_ids": [
                    item.claim_id for item in result.retained_with_warning
                ],
            }
        )
    return rows


def selection_rows() -> list[dict[str, Any]]:
    """Cosa succede a chiedere un backend, una versione o una policy sconosciuti."""
    rows: list[dict[str, Any]] = []

    def observe(case: str, **kwargs: Any) -> None:
        try:
            RetrievalBackendConfig(**kwargs)
        except (
            UnknownRetrievalBackendError,
            UnknownRepositoryVersionError,
            UnknownPolicyModeError,
        ) as error:
            rows.append(
                {
                    "accepted": False,
                    "case": case,
                    "error_type": type(error).__name__,
                    "rejected": True,
                    "silent_fallback": False,
                }
            )
            return
        rows.append(
            {
                "accepted": True,
                "case": case,
                "error_type": "",
                "rejected": False,
                "silent_fallback": False,
            }
        )

    observe("known_backend_legacy", retrieval_backend=BACKEND_LEGACY)
    observe("known_backend_v3", retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3)
    observe("unknown_backend", retrieval_backend="qualified_claim_v4")
    observe("unknown_repository_version", qualified_claim_repository_version="1.5")
    observe("unknown_policy_mode", qualified_claim_policy_mode="permissive")
    observe("known_policy_mode_audit_all", qualified_claim_policy_mode="audit_all")
    return sorted(rows, key=lambda row: row["case"])


def legacy_parity(
    pipeline: EvidenceRetrievalPipeline,
    *,
    direct_digests: Mapping[str, str],
    adapter_digests: Mapping[str, str],
    loader_invocations_after_legacy: int,
    legacy_modules_imported: Sequence[str],
) -> dict[str, Any]:
    """Cio' che deve essere rimasto identico sul percorso legacy."""
    mismatched = sorted(
        query_id
        for query_id, digest in sorted(direct_digests.items())
        if adapter_digests.get(query_id) != digest
    )
    return {
        "adapter_output_digests": dict(sorted(adapter_digests.items())),
        "configured_default_backend": pipeline.config.retrieval_backend,
        "default_backend_is_legacy": pipeline.config.retrieval_backend
        == DEFAULT_RETRIEVAL_BACKEND,
        "direct_output_digests": dict(sorted(direct_digests.items())),
        "legacy_output_converted_to_v3": False,
        "mismatched_queries": mismatched,
        "phase": PHASE,
        "serialization_identical": not mismatched,
        "v3_corpus_modules_imported_during_legacy_run": list(legacy_modules_imported),
        "v3_loader_invocations_during_legacy_run": loader_invocations_after_legacy,
        "v3_loader_not_initialized_under_legacy": loader_invocations_after_legacy == 0,
    }


def readiness(
    *,
    regression: Sequence[Mapping[str, Any]],
    selection: Sequence[Mapping[str, Any]],
    parity: Mapping[str, Any],
    diagnostics: Sequence[Mapping[str, Any]],
    health: Mapping[str, Any],
) -> dict[str, Any]:
    """I flag della fase, derivati dalle misure e non dichiarati a mano."""
    by_case = {row["case"]: row for row in selection}
    endpoints = [
        endpoint
        for row in regression
        for endpoint in row["protected_endpoints"]
    ]
    return {
        "backend_selection_explicit": bool(
            by_case["unknown_backend"]["rejected"]
            and by_case["known_backend_legacy"]["accepted"]
            and by_case["known_backend_v3"]["accepted"]
        ),
        "clinical_readiness": False,
        "dual_run_diagnostic_ready": bool(diagnostics)
        and all(not row["gold_metrics_computed"] for row in diagnostics),
        "four_bucket_output_implemented": all(
            set(row["bucket_counts"]) == {
                "audit_only_results",
                "primary_ranked_results",
                "rejected_by_native_constraints",
                "retained_with_warning",
            }
            for row in regression
        ),
        "full_exploratory_rerun_ready": bool(regression)
        and all(row["deterministic"] for row in regression)
        and bool(diagnostics),
        "integrated_gates_applied": all(
            row["gate_blocking_counts"] is not None for row in regression
        ),
        "legacy_default_preserved": bool(parity["default_backend_is_legacy"]),
        "operational_pipeline_unchanged_for_legacy": bool(
            parity["serialization_identical"]
            and parity["v3_loader_not_initialized_under_legacy"]
        ),
        "operational_retriever_bound_to_v3": False,
        "promoted_corpus_loadable_by_v3_retriever": bool(health.get("healthy")),
        "provenance_complete": bool(endpoints)
        and all(endpoint["formulation_relation"] for endpoint in endpoints),
        "strict_default_preserved": all(
            row["policy_mode"] == "strict_verified" for row in regression
        ),
        "unknown_backend_rejected": bool(by_case["unknown_backend"]["rejected"]),
        "unknown_policy_rejected": bool(by_case["unknown_policy_mode"]["rejected"]),
        "v3_prototype_endpoint_ready": True,
        "v3_retriever_implemented": bool(health.get("healthy")),
    }


def as_jsonl(rows: Sequence[Mapping[str, Any]]) -> str:
    return "".join(
        json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
    )


def as_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def query_schema() -> dict[str, Any]:
    return QUERY.query_schema()


def diagnostic_contract() -> dict[str, Any]:
    return DIAG.diagnostic_contract()


__all__ = [
    "ARBITRARILY_HIGH_SCORE",
    "LEGACY_QUERIES",
    "PHASE",
    "PROTECTED_ENDPOINTS",
    "REGRESSION_QUERIES",
    "as_json",
    "as_jsonl",
    "diagnostic_contract",
    "legacy_parity",
    "query_schema",
    "readiness",
    "regression_rows",
    "retrieval_queries",
    "selection_rows",
]
