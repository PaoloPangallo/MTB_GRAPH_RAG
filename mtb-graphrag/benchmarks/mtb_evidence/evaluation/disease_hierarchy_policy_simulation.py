"""Simulazione del contratto disease sui claim tipizzati dello shadow 1.2.

Nulla viene applicato: i claim sono letti e mai riscritti, e il retriever operativo
non viene invocato. La simulazione serve a mostrare che il contratto, applicato a
dati reali, produce esattamente le distinzioni che dichiara di produrre — e in
particolare che il bucket primario non cambia fra le tre modalita'.

L'asse biomarcatore compare soltanto come fatto dichiarato, mai ricalcolato qui:
questa fase decide sulla disease, e il biomarcatore serve solo a mostrare che un
alias disease compatibile non salva un biomarcatore incompatibile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS,
    CLAIM_IS_CHILD_OF_QUERY,
    CONTRACT_VERSION,
    DISEASE_GATE_PRECEDES_SCORING,
    EXACT_RELATIONS,
    PHASE_VERSION,
    POLICY_MODES,
    REJECTED,
    RELATION_TYPES,
    policy_for,
    resolve_relation,
)

# --- query congelate ----------------------------------------------------------

THERAPEUTIC_QUERY = "therapeutic_evidence_query"
DIAGNOSTIC_QUERY = "diagnostic_evidence_query"
UNTYPED_QUERY = "untyped_evidence_query"

SECTION_BY_DOMAIN = {
    "therapeutic": "therapeutic_results",
    "diagnostic": "diagnostic_results",
    "prognostic": "prognostic_results",
}


@dataclass(frozen=True)
class FrozenQuery:
    query_id: str
    label: str
    biomarker: str
    disease: str
    query_domain: str
    scenario: str
    expectation: str

    def as_row(self) -> dict[str, Any]:
        return {
            "biomarker": self.biomarker,
            "disease": self.disease,
            "expectation": self.expectation,
            "label": self.label,
            "query_domain": self.query_domain,
            "query_id": self.query_id,
            "scenario": self.scenario,
        }


FROZEN_QUERIES: tuple[FrozenQuery, ...] = (
    FrozenQuery(
        query_id="DQ-01-EGFR-L858R-NSCLC",
        label="EGFR-L858R / NSCLC",
        biomarker="EGFR L858R",
        disease="NSCLC",
        query_domain=THERAPEUTIC_QUERY,
        scenario="verified_alias_primary",
        expectation="I quattro letterali NSCLC restano verified alias e primary.",
    ),
    FrozenQuery(
        query_id="DQ-02-EGFR-L858R-LUAD",
        label="EGFR-L858R / Lung Adenocarcinoma",
        biomarker="EGFR L858R",
        disease="Lung Adenocarcinoma",
        query_domain=THERAPEUTIC_QUERY,
        scenario="claim_parent_of_query_directional",
        expectation="I claim NSCLC sono parent della query e restano warning, mai exact.",
    ),
    FrozenQuery(
        query_id="DQ-03-FGFR2-ICCA",
        label="FGFR2 fusion / Intrahepatic Cholangiocarcinoma",
        biomarker="FGFR2::BICC1 Fusion",
        disease="Intrahepatic Cholangiocarcinoma",
        query_domain=THERAPEUTIC_QUERY,
        scenario="icca_exact_primary",
        expectation="I claim iCCA sono exact primary; i claim CCA sono parent con warning.",
    ),
    FrozenQuery(
        query_id="DQ-04-FGFR2-CCA",
        label="FGFR2 fusion / Cholangiocarcinoma",
        biomarker="FGFR2::BICC1 Fusion",
        disease="Cholangiocarcinoma",
        query_domain=THERAPEUTIC_QUERY,
        scenario="claim_child_of_query_not_generalized",
        expectation="I claim iCCA sono child della query: warning, mai exact, mai generalizzati.",
    ),
    FrozenQuery(
        query_id="DQ-05-ALK-G1202R-NSCLC",
        label="ALK-G1202R / NSCLC",
        biomarker="ALK G1202R",
        disease="NSCLC",
        query_domain=THERAPEUTIC_QUERY,
        scenario="verified_alias_with_biomarker_gate",
        expectation="Alias disease compatibile: l'esclusione, dove avviene, e' del biomarcatore.",
    ),
    FrozenQuery(
        query_id="DQ-06-SIBLING-CCC",
        label="FGFR2 fusion / Cholangiolocellular Carcinoma",
        biomarker="FGFR2 Fusion",
        disease="Cholangiolocellular Carcinoma",
        query_domain=THERAPEUTIC_QUERY,
        scenario="sibling_never_exact",
        expectation="I claim iCCA sono sibling: audit-only in tutte le modalita'.",
    ),
    FrozenQuery(
        query_id="DQ-07-GENERIC-CANCER",
        label="generic cancer",
        biomarker="FGFR2 Fusion",
        disease="Cancer",
        query_domain=THERAPEUTIC_QUERY,
        scenario="generic_scope_not_case_specific",
        expectation="Uno scope generico non e' un alias della disease della query.",
    ),
    FrozenQuery(
        query_id="DQ-08-MISSING-DISEASE",
        label="missing disease",
        biomarker="EGFR L858R",
        disease="",
        query_domain=THERAPEUTIC_QUERY,
        scenario="missing_query_disease",
        expectation="Senza disease nella query non c'e' domanda: audit-only, mai primary.",
    ),
    FrozenQuery(
        query_id="DQ-09-CROSS-DISEASE",
        label="cross-disease",
        biomarker="EGFR L858R",
        disease="Breast Cancer",
        query_domain=THERAPEUTIC_QUERY,
        scenario="cross_disease_rejected",
        expectation="Nessun biomarcatore o intervento exact compensa il mismatch disease.",
    ),
    FrozenQuery(
        query_id="DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA",
        label="diagnostic FGFR2-BICC1 / iCCA",
        biomarker="FGFR2::BICC1 Fusion",
        disease="Intrahepatic Cholangiocarcinoma",
        query_domain=UNTYPED_QUERY,
        scenario="untyped_query_sectioned",
        expectation="Sezioni separate per dominio, senza ranking cross-domain.",
    ),
)


# --- compatibilita' biomarcatore dichiarata -----------------------------------

BIOMARKER_COMPATIBLE = "biomarker_compatible"
BIOMARKER_INCOMPATIBLE = "native_biomarker_mismatch"

# Tabella dichiarata, non calcolata. Ogni riga cita il letterale congelato del claim
# e la ragione per cui e' o non e' compatibile con il letterale della query. Questa
# fase non implementa un matcher di biomarcatori: lo dichiara come fatto in ingresso
# perche' serve soltanto a mostrare che l'alias disease non lo compensa.
DECLARED_BIOMARKER_COMPATIBILITY: dict[tuple[str, str], tuple[bool, str, str]] = {
    ("DQ-01-EGFR-L858R-NSCLC", "evidence:11219"): (
        True,
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "il letterale disgiuntivo del claim include l'alterazione della query",
    ),
    ("DQ-01-EGFR-L858R-NSCLC", "evidence:11598"): (
        False,
        "EGFR T790M AND EGFR Exon 19 Deletion",
        "il letterale congiuntivo richiede T790M, che la query non porta",
    ),
    ("DQ-01-EGFR-L858R-NSCLC", "evidence:11599"): (
        False,
        "EGFR L858R AND EGFR T790M",
        "il profilo composto richiede anche T790M: non e' L858R singola",
    ),
    ("DQ-01-EGFR-L858R-NSCLC", "evidence:1867"): (
        False,
        "EGFR T790M",
        "T790M e' un'alterazione diversa da L858R sullo stesso gene",
    ),
    ("DQ-05-ALK-G1202R-NSCLC", "evidence:11219"): (
        False,
        "EGFR L858R OR EGFR Exon 19 Deletion",
        "gene diverso da quello della query",
    ),
}


def declared_biomarker_compatibility(
    query_id: str, graph_evidence_id: str
) -> tuple[bool | None, str, str]:
    entry = DECLARED_BIOMARKER_COMPATIBILITY.get((query_id, graph_evidence_id))
    if entry is None:
        return None, "", ""
    compatible, literal, justification = entry
    return compatible, literal, justification


# --- simulazione claim x query x modalita' ------------------------------------


def _claim_section(claim: Mapping[str, Any]) -> str:
    return SECTION_BY_DOMAIN.get(str(claim.get("claim_domain") or ""), "audit_results")


def _rejected_by_biomarker(row: dict[str, Any]) -> dict[str, Any]:
    """Collassa la riga sul rifiuto nativo del biomarcatore.

    Un biomarcatore incompatibile esclude anche quando la disease e' un alias
    verificato: e' la direzione che conta, e non e' reversibile. Il contrario non
    vale mai — nessun biomarcatore exact riporta nel primario un claim che il gate
    disease ha gia' escluso.

    L'eleggibilita' al punteggio va azzerata insieme al bucket: una riga respinta
    che conservasse `qualified_score_eligible` sarebbe punteggiabile pur essendo
    esclusa, e contraddirebbe gli invarianti del gate.
    """
    return {
        "audit_only": False,
        "bucket": REJECTED,
        "exclusion_reason_codes": [
            BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS,
            BIOMARKER_INCOMPATIBLE,
        ],
        "primary_candidate_eligible": False,
        "rejected_by_native_constraints": True,
        "score_eligibility": {
            "bucket": REJECTED,
            "final_ranking_eligible": False,
            "positive_score_forbidden": True,
            "qualified_score_eligible": False,
            "ranks_within_bucket_only": False,
            "structural_score_eligible": False,
        },
        "warning_eligible": False,
    }


def simulate_pairs(
    claims: Sequence[Mapping[str, Any]],
    queries: Sequence[FrozenQuery] = FROZEN_QUERIES,
) -> list[dict[str, Any]]:
    """Una riga per coppia claim/query, con i tre esiti di modalita' espliciti.

    La relazione e' risolta una volta sola perche' non dipende dalla modalita':
    scriverla tre volte identica suggerirebbe che possa cambiare.
    """
    rows: list[dict[str, Any]] = []
    for query in queries:
        for claim in claims:
            scope = str(claim.get("disease_scope") or "")
            resolution = resolve_relation(query.disease, scope)
            graph_evidence_id = str(claim.get("graph_evidence_id") or "")
            compatible, literal, justification = declared_biomarker_compatibility(
                query.query_id, graph_evidence_id
            )
            by_mode: dict[str, Any] = {}
            for mode in POLICY_MODES:
                policy = policy_for(resolution.relation_type, mode)
                if compatible is False:
                    by_mode[mode] = _rejected_by_biomarker(policy.as_row())
                    continue
                row = policy.as_row()
                row["exclusion_reason_codes"] = []
                by_mode[mode] = row
            rows.append(
                {
                    "biomarker_compatibility_declared": compatible,
                    "biomarker_compatibility_justification": justification,
                    "by_mode": by_mode,
                    "claim_biomarker_literal": literal or str(claim.get("biomarker") or ""),
                    "claim_canonical_key": resolution.claim_canonical_key,
                    "claim_disease_scope": scope,
                    "claim_domain": str(claim.get("claim_domain") or ""),
                    "claim_id": str(claim.get("claim_id") or ""),
                    "claim_type": str(claim.get("claim_type") or ""),
                    "contract_version": CONTRACT_VERSION,
                    "graph_evidence_id": graph_evidence_id,
                    "normalized_claim_disease": resolution.claim_core,
                    "normalized_query_disease": resolution.query_core,
                    "query_canonical_key": resolution.query_canonical_key,
                    "query_disease": query.disease,
                    "query_id": query.query_id,
                    "relation_direction": resolution.relation_direction,
                    "relation_provenance": resolution.relation_provenance,
                    "relation_source": resolution.relation_source,
                    "relation_source_version": resolution.relation_source_version,
                    "relation_type": resolution.relation_type,
                    "relation_verified": resolution.relation_verified,
                    "section": _claim_section(claim),
                }
            )
    return rows


def _counter(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def simulate_queries(
    pairs: Sequence[Mapping[str, Any]],
    queries: Sequence[FrozenQuery] = FROZEN_QUERIES,
) -> list[dict[str, Any]]:
    """Aggregato per query e modalita': che cosa vedrebbe chi legge il risultato."""
    by_query: dict[str, list[Mapping[str, Any]]] = {}
    for row in pairs:
        by_query.setdefault(str(row["query_id"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for query in queries:
        subset = by_query.get(query.query_id, [])
        for mode in POLICY_MODES:
            modes = [row["by_mode"][mode] for row in subset]
            primary = [
                str(row["claim_id"])
                for row, item in zip(subset, modes)
                if item["primary_candidate_eligible"]
            ]
            sections = _counter(
                str(row["section"])
                for row, item in zip(subset, modes)
                if item["primary_candidate_eligible"] or item["warning_eligible"]
            )
            rows.append(
                {
                    "audit_only_count": sum(1 for item in modes if item["audit_only"]),
                    "bucket_counts": _counter(str(item["bucket"]) for item in modes),
                    "claims_evaluated": len(subset),
                    "contract_version": CONTRACT_VERSION,
                    "cross_domain_ranking_allowed": False,
                    "policy_mode": mode,
                    "primary_candidate_count": len(primary),
                    "primary_claim_ids": sorted(primary),
                    "query_disease": query.disease,
                    "query_domain": query.query_domain,
                    "query_id": query.query_id,
                    "rejected_count": sum(
                        1 for item in modes if item["rejected_by_native_constraints"]
                    ),
                    "relation_counts": _counter(
                        str(row["relation_type"]) for row in subset
                    ),
                    "scenario": query.scenario,
                    "sections_presented": sections,
                    "sectioned_output": query.query_domain == UNTYPED_QUERY,
                    "warning_count": sum(1 for item in modes if item["warning_eligible"]),
                }
            )
    return rows


# --- casi di regressione e probe del gate -------------------------------------

REGRESSION_EVIDENCE = (
    "evidence:1846",
    "evidence:1847",
    "evidence:8173",
    "evidence:11219",
    "evidence:11598",
    "evidence:11599",
    "evidence:1867",
)

_REGRESSION_QUERIES: dict[str, tuple[str, ...]] = {
    "evidence:1846": ("DQ-03-FGFR2-ICCA", "DQ-04-FGFR2-CCA", "DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA"),
    "evidence:1847": ("DQ-03-FGFR2-ICCA", "DQ-04-FGFR2-CCA", "DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA"),
    "evidence:8173": ("DQ-03-FGFR2-ICCA", "DQ-06-SIBLING-CCC"),
    "evidence:11219": ("DQ-01-EGFR-L858R-NSCLC", "DQ-05-ALK-G1202R-NSCLC"),
    "evidence:11598": ("DQ-01-EGFR-L858R-NSCLC",),
    "evidence:11599": ("DQ-01-EGFR-L858R-NSCLC",),
    "evidence:1867": ("DQ-01-EGFR-L858R-NSCLC",),
}

_REGRESSION_EXPECTATION: dict[tuple[str, str], str] = {
    ("evidence:1846", "DQ-03-FGFR2-ICCA"): "exact primary sulla query iCCA",
    ("evidence:1846", "DQ-04-FGFR2-CCA"): "child della query: warning, mai exact",
    ("evidence:1847", "DQ-03-FGFR2-ICCA"): "exact primary sulla query iCCA",
    ("evidence:1847", "DQ-04-FGFR2-CCA"): "child della query: warning, mai exact",
    ("evidence:8173", "DQ-03-FGFR2-ICCA"): "sibling della query iCCA: audit-only, mai exact",
    ("evidence:8173", "DQ-06-SIBLING-CCC"): "exact sulla propria disease, non su iCCA",
    ("evidence:11219", "DQ-01-EGFR-L858R-NSCLC"): "verified alias NSCLC e biomarcatore compatibile: primary",
    ("evidence:11219", "DQ-05-ALK-G1202R-NSCLC"): "verified alias NSCLC ma biomarcatore incompatibile: escluso",
    ("evidence:11598", "DQ-01-EGFR-L858R-NSCLC"): "alias disease compatibile, biomarcatore congiuntivo incompatibile: escluso",
    ("evidence:11599", "DQ-01-EGFR-L858R-NSCLC"): "alias disease compatibile, profilo composto incompatibile: escluso",
    ("evidence:1867", "DQ-01-EGFR-L858R-NSCLC"): "alias disease compatibile, T790M incompatibile con L858R: escluso",
}


def regression_cases(pairs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    index = {(str(row["query_id"]), str(row["graph_evidence_id"])): row for row in pairs}
    rows: list[dict[str, Any]] = []
    for graph_evidence_id in REGRESSION_EVIDENCE:
        for query_id in _REGRESSION_QUERIES[graph_evidence_id]:
            pair = index.get((query_id, graph_evidence_id))
            if pair is None:
                continue
            rows.append(
                {
                    "biomarker_compatibility_declared": pair["biomarker_compatibility_declared"],
                    "by_mode": pair["by_mode"],
                    "case_id": f"REG-{graph_evidence_id.split(':')[1]}-{query_id}",
                    "claim_biomarker_literal": pair["claim_biomarker_literal"],
                    "claim_disease_scope": pair["claim_disease_scope"],
                    "claim_id": pair["claim_id"],
                    "claim_type": pair["claim_type"],
                    "contract_version": CONTRACT_VERSION,
                    "disease_relation_compensated_by_biomarker": False,
                    "expectation": _REGRESSION_EXPECTATION.get(
                        (graph_evidence_id, query_id), ""
                    ),
                    "graph_evidence_id": graph_evidence_id,
                    "is_exact_relation": pair["relation_type"] in EXACT_RELATIONS,
                    "kind": "corpus_regression",
                    "query_disease": pair["query_disease"],
                    "query_id": query_id,
                    "relation_direction": pair["relation_direction"],
                    "relation_type": pair["relation_type"],
                    "section": pair["section"],
                }
            )
    rows.extend(_contract_probes())
    return rows


def _probe(
    *,
    case_id: str,
    kind: str,
    query_disease: str,
    claim_disease_scope: str,
    expectation: str,
    injected_score: float | None = None,
) -> dict[str, Any]:
    resolution = resolve_relation(query_disease, claim_disease_scope)
    by_mode = {
        mode: policy_for(resolution.relation_type, mode).as_row() for mode in POLICY_MODES
    }
    row = {
        "biomarker_compatibility_declared": None,
        "by_mode": by_mode,
        "case_id": case_id,
        "claim_biomarker_literal": "",
        "claim_disease_scope": claim_disease_scope,
        "claim_id": "",
        "claim_type": "",
        "contract_version": CONTRACT_VERSION,
        "disease_relation_compensated_by_biomarker": False,
        "expectation": expectation,
        "graph_evidence_id": "",
        "is_exact_relation": resolution.relation_type in EXACT_RELATIONS,
        "kind": kind,
        "query_disease": query_disease,
        "query_id": "",
        "relation_direction": resolution.relation_direction,
        "relation_type": resolution.relation_type,
        "section": "audit_results",
    }
    if injected_score is not None:
        row["injected_score"] = injected_score
        row["injected_signals"] = [
            "biomarker_exact_match",
            "intervention_exact_match",
            "provenance_level_high",
            "source_quality_high",
        ]
        row["gate_reason_code"] = DISEASE_GATE_PRECEDES_SCORING
        row["primary_after_injection"] = any(
            by_mode[mode]["primary_candidate_eligible"] for mode in POLICY_MODES
        )
    return row


def _contract_probes() -> list[dict[str, Any]]:
    """Casi che il corpus non contiene, ma che il contratto deve saper dire.

    Il probe del gate e' il piu' importante: inietta insieme biomarcatore exact,
    intervento exact, provenance alta e punteggio massimo su una relazione child, e
    verifica che il primario resti chiuso. Se un giorno si aprisse, questo e' il
    caso che lo direbbe.
    """
    return [
        _probe(
            case_id="PROBE-NORMALIZED-EXACT",
            kind="contract_probe",
            query_disease="Metastatic Lung Adenocarcinoma",
            claim_disease_scope="Lung Adenocarcinoma",
            expectation="Il qualificatore di stadio non cambia l'entita': normalized exact primary.",
        ),
        _probe(
            case_id="PROBE-MISSING-CLAIM-DISEASE",
            kind="contract_probe",
            query_disease="NSCLC",
            claim_disease_scope="",
            expectation="Disease scope del claim assente: distinto da unresolved e da cross-disease.",
        ),
        _probe(
            case_id="PROBE-UNRESOLVED-RELATION",
            kind="contract_probe",
            query_disease="Neuroblastoma",
            claim_disease_scope="Pilocytic Astrocytoma",
            expectation="Nessun termine registrato: relazione non decidibile, non cross-disease.",
        ),
        _probe(
            case_id="PROBE-SCORE-GATE",
            kind="score_gate_probe",
            query_disease="Cholangiocarcinoma",
            claim_disease_scope="Intrahepatic Cholangiocarcinoma",
            expectation="Score massimo e segnali exact non aprono il primario a una relazione child.",
            injected_score=1.0,
        ),
    ]


def relation_coverage(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = _counter(str(row["relation_type"]) for row in pairs)
    missing = [relation for relation in RELATION_TYPES if relation not in observed]
    return {
        "relation_types_observed": observed,
        "relation_types_without_corpus_occurrence": missing,
        "covered_by_contract_probe": [
            row["relation_type"]
            for row in _contract_probes()
            if row["relation_type"] in missing
        ],
    }


def primary_bucket_is_mode_invariant(pairs: Sequence[Mapping[str, Any]]) -> bool:
    """Il primario non deve muoversi cambiando modalita'. Verificato, non asserito."""
    for row in pairs:
        values = {
            row["by_mode"][mode]["primary_candidate_eligible"] for mode in POLICY_MODES
        }
        if len(values) != 1:
            return False
    return True


def child_and_parent_never_primary(pairs: Sequence[Mapping[str, Any]]) -> bool:
    for row in pairs:
        if row["relation_type"] not in {
            CLAIM_IS_CHILD_OF_QUERY,
            "claim_is_parent_of_query",
        }:
            continue
        for mode in POLICY_MODES:
            if row["by_mode"][mode]["primary_candidate_eligible"]:
                return False
    return True


__all__ = [
    "BIOMARKER_COMPATIBLE",
    "BIOMARKER_INCOMPATIBLE",
    "DECLARED_BIOMARKER_COMPATIBILITY",
    "FROZEN_QUERIES",
    "PHASE_VERSION",
    "REGRESSION_EVIDENCE",
    "SECTION_BY_DOMAIN",
    "UNTYPED_QUERY",
    "FrozenQuery",
    "child_and_parent_never_primary",
    "declared_biomarker_compatibility",
    "primary_bucket_is_mode_invariant",
    "regression_cases",
    "relation_coverage",
    "simulate_pairs",
    "simulate_queries",
]
