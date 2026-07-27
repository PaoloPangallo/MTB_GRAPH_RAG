"""Genera il repository shadow 1.3: terminologia verificata piu' gate integrato.

Il generatore parte dalla 1.2 autenticata, applica il solo mapping verificato e
simula il gate integrato sulle query congelate delle due fasi precedenti. Non
scrive nel corpus, nei moduli operativi o nei repository shadow 1.0-1.2, non
esegue i piani di link e view, e non legge mai il gold.

Le query non vengono riscritte: quelle della disease policy arrivano dal modulo
di simulazione congelato, quelle del claim-type retrieval contract vengono
rilette dall'artefatto gia' emesso. Riscriverle a mano qui significherebbe poter
sbagliare a copiarle, e una query sbagliata produce una regressione che sembra
un cambiamento di comportamento.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import integrated_gates as GATE
from backend.pipeline.evidence.shadow import shadow_output_v12 as OUT
from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
)
from backend.pipeline.evidence.shadow.identity import CLAIM_ID_FORMULA_VERSION
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    MODEL_SCHEMA_VERSION_V11,
    SHADOW_REPOSITORY_VERSION,
    SHADOW_REPOSITORY_VERSION_V11,
)
from backend.pipeline.evidence.shadow.terminology_v13 import (
    CANONICALIZED_GRAPH_EVIDENCE_IDS,
    REPOSITORY_VERSION,
    UNRESOLVED_DECISION_ID,
    UNRESOLVED_SOURCE_LITERAL,
    VERIFIED_CANONICAL_LABEL,
    VERIFIED_DECISION_ID,
    VERIFIED_SOURCE_LITERAL,
    VERSION_BUMP_REASON,
    apply_verified_terminology,
    terminology_registry,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    DEFAULT_MODE,
    POLICY_MODES,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy_simulation import (
    FROZEN_QUERIES,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_diagnostic_disease_scope_narrowing_shadow import (
    run_update as run_v12,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
TERMINOLOGY = V3 / "terminology_mapping_closure"
DISEASE_POLICY = V3 / "disease_hierarchy_policy"
CLAIM_CONTRACT = V3 / "claim_type_retrieval_contract"
CORPUS = V3 / "qualification_corpus_v2"
DEFAULT_OUTPUT = V3 / "integrated_shadow_repository_1_3"
SCORING_CONFIG = (
    REPO_ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)

START_SHA = "c1ece7b900150abc69d8157e16372223e8e3ef57"

EXPECTED_NEW_CLAIM_IDS = {
    "evidence:1851": "CLM-90e863f00f134fc3cd3d",
    "evidence:1853": "CLM-5071bb2d8657ac0fbed0",
}
EXPECTED_OLD_CLAIM_IDS = {
    "evidence:1851": "CLM-a7c903cf8d423f015e29",
    "evidence:1853": "CLM-aae818bbc8ec735a255d",
}

EXPECTED_COUNTS = {
    "active_claims_total": 148,
    "aggregate_intervention_claim": 3,
    "atomic_intervention_claim": 140,
    "diagnostic_claims": 2,
    "parents": 147,
    "parents_without_claims": 3,
    "prognostic_claims": 0,
    "regimen_claim": 3,
    "therapeutic_claims": 146,
    "unresolved_associations": 6,
    "unsupported_associations": 6,
}

OPERATIONAL_QUERY_BASELINE_SHA256 = (
    "af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124"
)
CORPUS_FINGERPRINT = "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/qualification.py",
    "backend/pipeline/evidence/qualified_disease_matching.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/v2_adapter.py",
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

FROZEN_SCIENTIFIC_ARTIFACTS = (
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/contract_manifest.json",
    "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/policy_manifest.json",
    "benchmarks/mtb_evidence/v3/disease_normalization_review/review_manifest.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/adjudication_manifest.json",
    "benchmarks/mtb_evidence/v3/terminology_mapping_closure/terminology_review_manifest.json",
    "benchmarks/mtb_evidence/v3/verified_disease_alias_fix/fix_manifest.json",
)

# I dodici gruppi che la fase deve proteggere, con l'attesa dichiarata prima di
# osservare il risultato. L'attesa e' testo: serve a rendere leggibile che cosa
# la regressione sta proteggendo, non a decidere l'esito.
REGRESSION_EXPECTATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "evidence:1846",
        "diagnostic_icca_primary_and_cca_warning",
        "Query iCCA: diagnostico exact primary. Query Cholangiocarcinoma: il "
        "claim e' child della query, warning, mai primary.",
    ),
    (
        "evidence:1847",
        "diagnostic_icca_primary_and_cca_warning",
        "Stesso comportamento del gruppo gemello sull'altro partner di fusione.",
    ),
    (
        "evidence:8173",
        "sibling_audit_only",
        "Query iCCA: il claim su Cholangiolocellular Carcinoma e' sibling e resta "
        "audit-only in tutte le modalita'.",
    ),
    (
        "evidence:11219",
        "alias_primary_only_with_compatible_biomarker",
        "L'alias disease NSCLC rende primary soltanto se il biomarcatore e' "
        "compatibile.",
    ),
    (
        "evidence:11598",
        "alias_does_not_compensate_biomarker",
        "L'alias disease non compensa un biomarcatore incompatibile: eleggibilita' "
        "allo scoring interamente falsa.",
    ),
    (
        "evidence:11599",
        "alias_does_not_compensate_biomarker",
        "Come sopra, su una diversa combinazione di biomarcatore.",
    ),
    (
        "evidence:1867",
        "alias_does_not_compensate_biomarker",
        "Come sopra, su EGFR T790M isolato.",
    ),
    (
        "evidence:1851",
        "canonicalized_aggregate_never_atomic",
        "Nuovo claim ID, aggregate, canonical infigratinib, source literal BGJ398, "
        "mai atomico.",
    ),
    (
        "evidence:1853",
        "canonicalized_aggregate_never_atomic",
        "Come sopra, sull'altro partner di fusione.",
    ),
    (
        "evidence:841",
        "auy922_remains_unresolved",
        "AUY922/luminespib resta unresolved: nessun exact terminology match.",
    ),
    (
        "evidence:11240",
        "regimen_and_atomic_stay_distinct",
        "Regime e atomico restano distinti; il disease gate non li appiattisce.",
    ),
    (
        "evidence:347",
        "promotion_blocked_unchanged",
        "Nessun claim, promozione bloccata, invariato.",
    ),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _read_text(path).splitlines() if line.strip()]


def _sha256_file(path: Path) -> str:
    return sha256_text(_read_text(path))


def _folder_hash(path: Path) -> dict[str, str]:
    return {
        item.name: _sha256_file(item)
        for item in sorted(path.iterdir())
        if item.is_file()
    }


# --------------------------------------------------------------------------
# query
# --------------------------------------------------------------------------


def disease_policy_queries() -> list[dict[str, Any]]:
    """Le dieci query congelate della disease policy, riusate senza riscriverle."""
    return [
        {
            "biomarker": frozen.biomarker,
            "disease": frozen.disease,
            "expectation": frozen.expectation,
            "interventions": [],
            "query_domain": frozen.query_domain,
            "query_id": frozen.query_id,
            "query_source": "disease-hierarchy-policy/1.0",
            "scenario": frozen.scenario,
        }
        for frozen in FROZEN_QUERIES
    ]


def claim_contract_queries() -> list[dict[str, Any]]:
    """Le query del claim-type retrieval contract, rilette dall'artefatto emesso."""
    rows = _load_jsonl(CLAIM_CONTRACT / "adjudicated_claim_query_simulation.jsonl")
    seen: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        seen.setdefault(row["query_id"], row)
    queries: list[dict[str, Any]] = []
    for query_id in sorted(seen):
        row = seen[query_id]
        query: dict[str, Any] = {
            "biomarker": row["query_biomarker"],
            "direction": row["query_direction"],
            "disease": row["query_disease"],
            "expectation": "",
            "query_domain": "therapeutic_evidence_query",
            "query_id": query_id,
            "query_source": "claim-type-retrieval-contract/1.0",
            "scenario": row["query_scenario"],
        }
        if row["query_intervention_class"]:
            query["intervention_class"] = row["query_intervention_class"]
        else:
            query["interventions"] = list(row["query_interventions"])
        if row["query_type"] == "regimen_query":
            query["intervention_combination"] = True
        queries.append(query)
    return queries


def regression_probe_queries() -> list[dict[str, Any]]:
    """Sonde locali di fase, una per gruppo protetto.

    Le due famiglie congelate coprono le relazioni di malattia e i tipi di
    claim, ma non chiedono il biomarcatore di ogni gruppo che questa fase deve
    proteggere: su quei gruppi ogni query congelata finisce in
    `rejected_by_native_constraints` per mismatch di biomarcatore, e una
    regressione che osserva soltanto rifiuti non protegge nulla.

    Le sonde non introducono conoscenza nuova. Ogni biomarcatore e ogni disease
    scope sono copiati dai claim o dai parent del repository, e le due modalita'
    di ogni coppia — quella compatibile e quella incompatibile — servono a
    mostrare che l'alias di malattia non compensa il biomarcatore.
    """
    therapeutic = "therapeutic_evidence_query"
    diagnostic = "diagnostic_evidence_query"
    nsclc_egfr_pair = "EGFR L858R OR EGFR Exon 19 Deletion"
    icca = "Intrahepatic Cholangiocarcinoma"
    cca = "Cholangiocarcinoma"
    nsclc = "Lung Non-small Cell Carcinoma"
    alk_c1156y = "EML4::ALK Fusion AND ALK C1156Y"

    def probe(
        query_id: str,
        scenario: str,
        biomarker: str,
        disease: str,
        interventions: Sequence[str],
        domain: str,
        expectation: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "biomarker": biomarker,
            "disease": disease,
            "expectation": expectation,
            "interventions": list(interventions),
            "query_domain": domain,
            "query_id": query_id,
            "query_source": "integrated-shadow-repository/1.3",
            "scenario": scenario,
            **extra,
        }

    return [
        probe(
            "RP-1846-ICCA-DIAGNOSTIC",
            "diagnostic_exact_primary",
            "FGFR2::BICC1 Fusion",
            icca,
            (),
            diagnostic,
            "Il claim diagnostico su iCCA e' exact e primary.",
        ),
        probe(
            "RP-1846-CCA-DIAGNOSTIC",
            "diagnostic_child_warning_never_primary",
            "FGFR2::BICC1 Fusion",
            cca,
            (),
            diagnostic,
            "Il claim iCCA e' child della query generica: warning, mai primary.",
        ),
        probe(
            "RP-1847-ICCA-DIAGNOSTIC",
            "diagnostic_exact_primary",
            "FGFR2::AHCYL1 Fusion",
            icca,
            (),
            diagnostic,
            "Il claim diagnostico su iCCA e' exact e primary.",
        ),
        probe(
            "RP-1847-CCA-DIAGNOSTIC",
            "diagnostic_child_warning_never_primary",
            "FGFR2::AHCYL1 Fusion",
            cca,
            (),
            diagnostic,
            "Il claim iCCA e' child della query generica: warning, mai primary.",
        ),
        probe(
            "RP-8173-ICCA-SIBLING",
            "sibling_audit_only",
            "FGFR2::v Fusion OR FGFR2::? Fusion",
            icca,
            ("pemigatinib",),
            therapeutic,
            "Cholangiolocellular Carcinoma e iCCA sono sorelle: audit-only.",
        ),
        probe(
            "RP-11219-ALIAS-COMPATIBLE",
            "alias_primary_with_compatible_biomarker",
            nsclc_egfr_pair,
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "Alias disease verificato e biomarcatore compatibile: primary.",
        ),
        probe(
            "RP-11219-ALIAS-INCOMPATIBLE",
            "alias_does_not_compensate_biomarker",
            "EGFR L858R",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "Alias disease verificato ma biomarcatore incompatibile: rejected.",
        ),
        probe(
            "RP-11598-ALIAS-COMPATIBLE",
            "alias_primary_with_compatible_biomarker",
            "EGFR T790M AND EGFR Exon 19 Deletion",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "Alias disease verificato e biomarcatore compatibile: primary.",
        ),
        probe(
            "RP-11598-ALIAS-INCOMPATIBLE",
            "alias_does_not_compensate_biomarker",
            "EGFR L858R",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "L'alias di malattia non salva un biomarcatore diverso.",
        ),
        probe(
            "RP-11599-ALIAS-COMPATIBLE",
            "alias_primary_with_compatible_biomarker",
            "EGFR L858R AND EGFR T790M",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "Alias disease verificato e biomarcatore compatibile: primary.",
        ),
        probe(
            "RP-11599-ALIAS-INCOMPATIBLE",
            "alias_does_not_compensate_biomarker",
            "EGFR T790M",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "L'alias di malattia non salva un biomarcatore diverso.",
        ),
        probe(
            "RP-1867-ALIAS-COMPATIBLE",
            "alias_primary_with_compatible_biomarker",
            "EGFR T790M",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "Alias disease verificato e biomarcatore compatibile: primary.",
        ),
        probe(
            "RP-1867-ALIAS-INCOMPATIBLE",
            "alias_does_not_compensate_biomarker",
            "EGFR L858R AND EGFR T790M",
            "NSCLC",
            ("osimertinib",),
            therapeutic,
            "L'alias di malattia non salva un biomarcatore diverso.",
        ),
        probe(
            "RP-1851-CANONICAL-MEMBER",
            "canonicalized_aggregate_member_warning",
            "FGFR2::BICC1 Fusion",
            cca,
            (VERIFIED_CANONICAL_LABEL,),
            therapeutic,
            "Il membro canonico raggiunge l'aggregato: warning, mai atomico.",
        ),
        probe(
            "RP-1851-SOURCE-LITERAL",
            "source_literal_still_reaches_aggregate",
            "FGFR2::BICC1 Fusion",
            cca,
            (VERIFIED_SOURCE_LITERAL,),
            therapeutic,
            "Il letterale della fonte raggiunge lo stesso aggregato.",
        ),
        probe(
            "RP-1853-CANONICAL-MEMBER",
            "canonicalized_aggregate_member_warning",
            "FGFR2::AHCYL1 Fusion",
            cca,
            (VERIFIED_CANONICAL_LABEL,),
            therapeutic,
            "Il membro canonico raggiunge l'aggregato: warning, mai atomico.",
        ),
        probe(
            "RP-1853-SOURCE-LITERAL",
            "source_literal_still_reaches_aggregate",
            "FGFR2::AHCYL1 Fusion",
            cca,
            (VERIFIED_SOURCE_LITERAL,),
            therapeutic,
            "Il letterale della fonte raggiunge lo stesso aggregato.",
        ),
        probe(
            "RP-841-AUY922",
            "auy922_no_exact_terminology_match",
            alk_c1156y,
            nsclc,
            (UNRESOLVED_SOURCE_LITERAL,),
            therapeutic,
            "AUY922 non raggiunge alcun claim: il mapping resta irrisolto.",
            direction="resistance",
        ),
        probe(
            "RP-841-LUMINESPIB",
            "luminespib_not_canonicalized",
            alk_c1156y,
            nsclc,
            ("luminespib",),
            therapeutic,
            "Il termine del grafo non e' promosso ad alias exact di AUY922.",
            direction="resistance",
        ),
        probe(
            "RP-11240-ATOMIC",
            "atomic_stays_atomic",
            nsclc_egfr_pair,
            nsclc,
            ("erlotinib",),
            therapeutic,
            "Il claim atomico e' primary; il regime che lo contiene resta warning.",
        ),
        probe(
            "RP-11240-REGIMEN",
            "regimen_stays_regimen",
            nsclc_egfr_pair,
            nsclc,
            ("erlotinib", "ramucirumab"),
            therapeutic,
            "Il regime e' exact soltanto come combinazione dichiarata.",
            intervention_combination=True,
        ),
        probe(
            "RP-347-NO-CLAIM",
            "promotion_blocked_no_claim",
            "EGFR L858R",
            nsclc,
            (),
            therapeutic,
            "Il parent non ha claim: nessun risultato primario nasce da questo record.",
        ),
    ]


def all_queries(reverse: bool = False) -> list[dict[str, Any]]:
    queries = (
        disease_policy_queries() + claim_contract_queries() + regression_probe_queries()
    )
    ordered = sorted(queries, key=lambda row: row["query_id"])
    return list(reversed(ordered)) if reverse else ordered


def _gate_query(query: Mapping[str, Any]) -> dict[str, Any]:
    """La query nel vocabolario del gate: senza i campi descrittivi della fase."""
    return {
        key: value
        for key, value in query.items()
        if key not in ("expectation", "query_source", "scenario")
    }


# --------------------------------------------------------------------------
# repository
# --------------------------------------------------------------------------


def run_migration(reverse: bool = False):
    """Restituisce il risultato 1.3 senza scrivere file."""
    decisions = _load_jsonl(TERMINOLOGY / "mapping_decisions.jsonl")
    if reverse:
        decisions = list(reversed(decisions))
    result = apply_verified_terminology(run_v12(reverse), decisions)

    observed_new = {
        row["graph_evidence_id"]: row["new_claim_id"]
        for row in result.replacement_lineage
    }
    observed_old = {
        row["graph_evidence_id"]: row["old_claim_id"]
        for row in result.replacement_lineage
    }
    if observed_new != EXPECTED_NEW_CLAIM_IDS or observed_old != EXPECTED_OLD_CLAIM_IDS:
        raise RuntimeError(
            f"claim ID ricalcolati inattesi: {observed_old} -> {observed_new}"
        )
    return result


def _objects(result: Any) -> list[Any]:
    """Tutti gli oggetti interrogabili, claim ritirati compresi.

    I ritirati entrano perche' la fase deve poter dimostrare che restano fuori
    dal bucket primario, e cio' che non viene interrogato non puo' essere
    dimostrato.
    """
    retired = [
        replace(claim, deprecated=True)
        for claim in run_v12().therapeutic_claims
        if claim.claim_id in set(EXPECTED_OLD_CLAIM_IDS.values())
    ]
    return (
        list(result.evidence_claims)
        + retired
        + list(result.unsupported)
        + list(result.unresolved)
        + list(result.parents)
    )


def _claim_rows(result: Any) -> list[dict[str, Any]]:
    rows = []
    for claim in result.evidence_claims:
        payload = claim.to_dict()
        payload.setdefault("claim_domain", DOMAIN_THERAPEUTIC)
        payload["schema_version"] = MODEL_SCHEMA_VERSION_V11
        payload["repository_version"] = REPOSITORY_VERSION
        rows.append(payload)
    return rows


# --------------------------------------------------------------------------
# piani
# --------------------------------------------------------------------------


def _qualification_plan(result: Any) -> list[dict[str, Any]]:
    """Ritira i link ai due claim vecchi e ne crea due nuovi. Nulla viene eseguito."""
    old_ids = {row["old_claim_id"] for row in result.replacement_lineage}
    previous = _load_jsonl(
        SHADOW_V12 / "qualification_link_regeneration_plan_v1_2.jsonl"
    )
    rows = [
        row
        for row in previous
        if not (
            row.get("action") == "create_claim_link" and row.get("claim_id") in old_ids
        )
    ]
    by_new = {
        claim.claim_id: claim
        for claim in result.therapeutic_claims
        if claim.claim_id in {row["new_claim_id"] for row in result.replacement_lineage}
    }
    for lineage in result.replacement_lineage:
        claim = by_new[lineage["new_claim_id"]]
        shared = {
            "claim_domain": DOMAIN_THERAPEUTIC,
            "claim_type": claim.claim_type,
            "clinical_qualifiers_invented": False,
            "executed": False,
            "executed_at_promotion": True,
            "graph_evidence_id": lineage["graph_evidence_id"],
            "locator_count": len(claim.locators),
            "locators": [dict(item) for item in claim.locators],
            "propagation_policy": lineage["propagation_policy"],
            "qualification_status": "adjudicated_prototype_only",
            "review_status": lineage["review_status"],
            "reuses_therapeutic_link": False,
            "source_unit_ids": list(claim.source_unit_ids),
            "terminology_decision_id": lineage["terminology_decision_id"],
            # La canonicalizzazione non separa l'aggregato: nessun link per membro.
            "atomization_performed": False,
        }
        rows.append(
            shared
            | {
                "action": "retire_claim_link",
                "claim_id": lineage["old_claim_id"],
                "plan_id": f"RETIRE-CLAIM-LINK-{lineage['old_claim_id']}",
                "reason_code": lineage["reason_code"],
                "replacement_claim_id": lineage["new_claim_id"],
            }
        )
        rows.append(
            shared
            | {
                "action": "create_claim_link",
                "claim_id": lineage["new_claim_id"],
                "plan_id": f"CREATE-CLAIM-LINK-{lineage['new_claim_id']}",
                "reason_code": lineage["reason_code"],
                "replaces_claim_id": lineage["old_claim_id"],
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def _view_plan(result: Any) -> list[dict[str, Any]]:
    """Verifica sul corpus reale quali view siano coinvolte, invece di assumerlo.

    La terminology closure aveva simulato zero view coinvolte. Zero e' un numero
    plausibile e per questo va controllato: qui il controllo e' un conteggio di
    occorrenze dei due claim ID nel file delle view operative, e il suo esito
    viene scritto nel piano insieme al numero trovato.
    """
    views_text = _read_text(CORPUS / "qualified_evidence_views.jsonl")
    rows = _load_jsonl(SHADOW_V12 / "qualified_view_regeneration_plan_v1_2.jsonl")
    for row in rows:
        row["carried_from_repository_version"] = "qualified_claim_repository/1.2"
    for lineage in result.replacement_lineage:
        old_occurrences = views_text.count(lineage["old_claim_id"])
        new_occurrences = views_text.count(lineage["new_claim_id"])
        rows.append(
            {
                "action": "verify_no_view_references_replaced_claim",
                "carried_from_repository_version": REPOSITORY_VERSION,
                "claim_domain": DOMAIN_THERAPEUTIC,
                "checked_artifact": (
                    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/"
                    "qualified_evidence_views.jsonl"
                ),
                "checked_artifact_sha256": sha256_text(views_text),
                "executed": False,
                "graph_evidence_id": lineage["graph_evidence_id"],
                "new_claim_id": lineage["new_claim_id"],
                "new_claim_id_occurrences_in_views": new_occurrences,
                "old_claim_id": lineage["old_claim_id"],
                "old_claim_id_occurrences_in_views": old_occurrences,
                "operational_view_modified": False,
                "plan_id": (
                    f"VERIFY-VIEW-REFERENCES-{lineage['graph_evidence_id']}"
                ),
                "reason_code": (
                    "OPERATIONAL_VIEWS_ARE_KEYED_BY_LEGACY_STATEMENT_NOT_BY_CLAIM_ID"
                ),
                "regeneration_required": bool(old_occurrences),
                "terminology_decision_id": lineage["terminology_decision_id"],
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


# --------------------------------------------------------------------------
# simulazione
# --------------------------------------------------------------------------


def _gate_row(
    query: Mapping[str, Any],
    obj: Any,
    match: GATE.IntegratedStructuralMatchResult,
    by_mode: Mapping[str, GATE.IntegratedStructuralMatchResult],
) -> dict[str, Any]:
    disease = match.disease_match_result
    return {
        "audit_only": match.audit_only,
        "biomarker_compatible": match.biomarker_match_result["compatible"],
        "biomarker_match_type": match.biomarker_match_result["match_type"],
        "blocking_gates": list(match.blocking_gates),
        "by_mode": {
            mode: {
                "bucket": other.final_bucket,
                "final_ranking_eligible": other.final_ranking_eligible,
                "primary_candidate_eligible": other.primary_candidate_eligible,
                "qualified_score_eligible": other.qualified_score_eligible,
                "structural_score_eligible": other.structural_score_eligible,
            }
            for mode, other in sorted(by_mode.items())
        },
        "claim_domain": match.claim_domain,
        "claim_type": match.claim_type,
        "deprecated": bool(getattr(obj, "deprecated", False)),
        "direction_compatible": match.direction_match_result["compatible"],
        "direction_match_type": match.direction_match_result["direction_match_type"],
        "disease_relation_direction": disease.get("relation_direction", ""),
        "disease_relation_type": disease.get("relation_type", ""),
        "disease_relation_verified": disease.get("relation_verified", False),
        "domain_match": match.domain_match_result["domain_match"],
        "final_bucket": match.final_bucket,
        "final_ranking_eligible": match.final_ranking_eligible,
        "gate_version": match.gate_version,
        "intervention_match_type": match.intervention_match_result["match_type"],
        "object_id": match.claim_id,
        "object_kind": getattr(obj, "kind", None) or getattr(obj, "claim_type", ""),
        "policy_mode": match.policy_mode,
        "primary_candidate_eligible": match.primary_candidate_eligible,
        "qualified_score_eligible": match.qualified_score_eligible,
        "query_id": query["query_id"],
        "query_scenario": query.get("scenario", ""),
        "reason_codes": list(match.reason_codes),
        "rejected_by_native_constraints": match.rejected_by_native_constraints,
        "structural_score_eligible": match.structural_score_eligible,
        "warning_codes": list(match.warning_codes),
        "warning_eligible": match.warning_eligible,
    }


def _is_informative(row: Mapping[str, Any]) -> bool:
    """Vero se la riga dice qualcosa sul comportamento del gate.

    Un claim che parla di un altro biomarcatore e' fuori perimetro per la query,
    e la sua riga ripete un'unica informazione — "biomarcatore diverso" — una
    volta per ogni coppia. Il novantacinque per cento delle valutazioni ricade
    qui, e tenerle tutte renderebbe illeggibile cio' che invece va guardato: e'
    lo stesso argomento che il gate 1.0 usa per non riempire il bucket di audit
    con oggetti irrilevanti.

    Restano tutte le righe non respinte e tutte le righe respinte *dentro* il
    perimetro del biomarcatore: sono quelle in cui il rifiuto viene dal disease,
    dalla direzione o dalla polarita', cioe' esattamente le composizioni che
    questa fase deve dimostrare.
    """
    return (
        row["final_bucket"] != "rejected_by_native_constraints"
        or row["biomarker_compatible"]
    )


def simulate_gate(
    result: Any,
    queries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Matrice del gate integrato su claim e associazioni, nelle tre modalita'.

    Restituisce la matrice intera piu' i totali che la descrivono. La selezione
    delle righe da emettere avviene al momento della scrittura: le regressioni
    ragionano su tutte le valutazioni, il file ne porta la parte leggibile, e la
    differenza fra i due numeri e' dichiarata invece che nascosta.

    I parent restano fuori da questa matrice e sono coperti da una sonda
    dedicata: aggiungerli qui aggiungerebbe 147 righe di audit identiche per
    query, che dicono una cosa sola gia' detta una volta.
    """
    objects = [
        obj
        for obj in _objects(result)
        if getattr(obj, "kind", None) != "graph_evidence_record"
    ]
    rows: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for query in queries:
        gate_query = _gate_query(query)
        for obj in objects:
            by_mode = {
                mode: GATE.evaluate(gate_query, obj, mode=mode) for mode in POLICY_MODES
            }
            match = by_mode[DEFAULT_MODE]
            GATE.check_no_score_survives_a_blocking_gate(match, 999.0)
            row = _gate_row(query, obj, match, by_mode)
            totals[row["final_bucket"]] += 1
            rows.append(row)
    ordered = sorted(rows, key=lambda row: (row["query_id"], row["object_id"]))
    # Gli invarianti vengono contati qui, sulla matrice intera, e non a valle sul
    # sottoinsieme emesso: un invariante misurato su cio' che si e' scelto di
    # scrivere non dice nulla su cio' che si e' scelto di non scrivere.
    scope = {
        "bucket_totals_over_all_evaluations": dict(sorted(totals.items())),
        "primary_bucket_mode_invariant": all(
            len(
                {
                    detail["primary_candidate_eligible"]
                    for detail in row["by_mode"].values()
                }
            )
            == 1
            for row in ordered
        ),
        "primary_with_blocking_gate": sum(
            bool(row["primary_candidate_eligible"] and row["blocking_gates"])
            for row in ordered
        ),
        "score_flags_leaked_outside_rankable_buckets": sum(
            row["final_bucket"]
            in (GATE.AUDIT_BUCKET, GATE.REJECTED_BUCKET)
            and (
                row["structural_score_eligible"]
                or row["qualified_score_eligible"]
                or row["final_ranking_eligible"]
            )
            for row in ordered
        ),
        "emission_rule": (
            "Ogni valutazione non respinta, piu' ogni rifiuto dentro il perimetro "
            "del biomarcatore. I rifiuti per biomarcatore diverso sono contati e "
            "non emessi."
        ),
        "objects": len(objects),
        "pairs_emitted": sum(_is_informative(row) for row in ordered),
        "pairs_evaluated": len(ordered),
        "queries": len(queries),
    }
    return ordered, scope


def simulate_queries(
    result: Any,
    queries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Un output di retrieval shadow per ogni coppia query/modalita'."""
    objects = _objects(result)
    rows: list[dict[str, Any]] = []
    for query in queries:
        gate_query = _gate_query(query)
        for mode in POLICY_MODES:
            results = []
            for obj in objects:
                match = GATE.evaluate(gate_query, obj, mode=mode)
                results.append(OUT.build_result(obj, match))
            output = OUT.bucketed_output(query["query_id"], results, policy_mode=mode)
            rows.append(
                {
                    "bucket_counts": output["bucket_counts"],
                    "bucket_precedence": output["bucket_precedence"],
                    "contract_version": output["contract_version"],
                    "cross_domain_ranking": False,
                    "expectation": query.get("expectation", ""),
                    "audit_only_object_ids": sorted(
                        row["object_id"]
                        for row in output["audit_only_results"]
                        if row["object_kind"] != "graph_evidence_record"
                    ),
                    "parent_objects_in_primary": sum(
                        row["object_kind"] == "graph_evidence_record"
                        for row in output["primary_ranked_results"]
                    ),
                    "policy_mode": mode,
                    "primary_object_ids": sorted(
                        row["object_id"] for row in output["primary_ranked_results"]
                    ),
                    "query_biomarker": query.get("biomarker", ""),
                    "query_disease": query.get("disease", ""),
                    "query_domain": query.get("query_domain", ""),
                    "query_id": query["query_id"],
                    "query_scenario": query.get("scenario", ""),
                    "query_source": query.get("query_source", ""),
                    "repository_version": REPOSITORY_VERSION,
                    "retained_with_warning_object_ids": sorted(
                        row["object_id"] for row in output["retained_with_warning"]
                    ),
                    "scoring_applied": False,
                }
            )
    return sorted(rows, key=lambda row: (row["query_id"], row["policy_mode"]))


def simulate_regressions(
    result: Any,
    gate_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Un verdetto per gruppo protetto, derivato dalla matrice appena calcolata."""
    claims_by_evidence: dict[str, list[Any]] = {}
    for claim in result.evidence_claims:
        claims_by_evidence.setdefault(claim.graph_evidence_id, []).append(claim)
    ids_by_evidence = {
        evidence: {claim.claim_id for claim in claims}
        for evidence, claims in claims_by_evidence.items()
    }
    parents_without = {
        row["graph_evidence_id"] for row in result.parents_without_claims
    }

    rows: list[dict[str, Any]] = []
    for evidence, scenario, expectation in REGRESSION_EXPECTATIONS:
        object_ids = ids_by_evidence.get(evidence, set())
        observed = [row for row in gate_rows if row["object_id"] in object_ids]
        buckets = sorted({row["final_bucket"] for row in observed})
        # Le sonde dedicate al gruppo, piu' ogni valutazione che non sia un
        # rifiuto: sono le righe che dicono qualcosa. Il resto e' fuori
        # perimetro per biomarcatore e non descrive il comportamento protetto.
        probe_prefix = f"RP-{evidence.split(':')[1]}-"
        outcomes = [
            {
                "bucket": row["final_bucket"],
                "by_mode": {
                    mode: detail["bucket"] for mode, detail in row["by_mode"].items()
                },
                "disease_relation_direction": row["disease_relation_direction"],
                "disease_relation_type": row["disease_relation_type"],
                "intervention_match_type": row["intervention_match_type"],
                "object_id": row["object_id"],
                "primary_candidate_eligible": row["primary_candidate_eligible"],
                "qualified_score_eligible": row["qualified_score_eligible"],
                "query_id": row["query_id"],
                "structural_score_eligible": row["structural_score_eligible"],
            }
            for row in observed
            if row["query_id"].startswith(probe_prefix)
            or row["final_bucket"] != "rejected_by_native_constraints"
        ]
        primary_queries = sorted(
            {row["query_id"] for row in observed if row["primary_candidate_eligible"]}
        )
        relations = sorted({row["disease_relation_type"] for row in observed})
        claim_types = sorted({row["claim_type"] for row in observed})
        rows.append(
            {
                "buckets_observed": buckets,
                "case_id": f"REG-1-3-{evidence.replace(':', '-')}",
                "claim_ids": sorted(object_ids),
                "claim_types_observed": claim_types,
                "disease_relations_observed": relations,
                "evaluations": len(observed),
                "expectation": expectation,
                "graph_evidence_id": evidence,
                "has_claims": bool(object_ids),
                "is_parent_without_claim": evidence in parents_without,
                "positive_score_in_non_rankable_bucket": sum(
                    row["final_bucket"]
                    in ("audit_only_results", "rejected_by_native_constraints")
                    and (
                        row["structural_score_eligible"]
                        or row["qualified_score_eligible"]
                        or row["final_ranking_eligible"]
                    )
                    for row in observed
                ),
                "primary_in_queries": primary_queries,
                "probe_outcomes": sorted(
                    outcomes, key=lambda row: (row["query_id"], row["object_id"])
                ),
                "repository_version": REPOSITORY_VERSION,
                "scenario": scenario,
                "structural_score_ever_outside_primary": sum(
                    row["structural_score_eligible"]
                    and not row["primary_candidate_eligible"]
                    for row in observed
                ),
            }
        )
    return sorted(rows, key=lambda row: row["case_id"])


def parent_probe(result: Any, queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """I parent non entrano mai nel bucket primario. Verificato, non assunto."""
    primary = 0
    evaluated = 0
    for query in queries:
        gate_query = _gate_query(query)
        for parent in result.parents:
            match = GATE.evaluate(gate_query, parent)
            evaluated += 1
            primary += int(match.primary_candidate_eligible)
    return {
        "parents_evaluated": evaluated,
        "parents_ever_primary": primary,
        "queries": len(queries),
    }


# --------------------------------------------------------------------------
# integrita' operativa
# --------------------------------------------------------------------------


def _operational_query_sha256() -> tuple[str, int]:
    retriever = QualifiedEvidenceRetriever.from_corpus(
        CORPUS, scoring_config_path=SCORING_CONFIG
    )
    query = QualifiedRetrievalQuery(
        query_id="scope-narrowing-operational-parity",
        disease="Non-small cell lung cancer",
        disease_aliases=("Lung Non-small Cell Carcinoma",),
        biomarkers=(QueryBiomarker(gene="ALK"),),
        top_k=20,
        mode=MODE_QUALIFIED_SOFT,
        corpus_fingerprint=CORPUS_FINGERPRINT,
    )
    output = retriever.retrieve(query)
    text = (
        json.dumps(
            output.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(output.all_results)


def _inventory(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, Any]:
    query_hash, result_count = _operational_query_sha256()
    return {
        "authenticated_frozen_artifact_sha256": {
            path: _sha256_file(REPO_ROOT / path) for path in FROZEN_SCIENTIFIC_ARTIFACTS
        },
        "gold_artifacts_read": 0,
        "inventory_version": "operational_vs_shadow_inventory/1.3",
        "operational_artifact_sha256_after": dict(sorted(after.items())),
        "operational_artifact_sha256_before": dict(sorted(before.items())),
        "operational_hash_parity": dict(before) == dict(after),
        "operational_query": {
            "after_sha256": query_hash,
            "before_sha256": OPERATIONAL_QUERY_BASELINE_SHA256,
            "parity": query_hash == OPERATIONAL_QUERY_BASELINE_SHA256,
            "query_id": "scope-narrowing-operational-parity",
            "result_count": result_count,
        },
        "operational_statements_still_authoritative": True,
        "shadow_imports_into_operational_modules": 0,
        "shadow_objects_queryable_by_operational_pipeline": False,
        "shadow_repository_folder_sha256": {
            "1.0": _folder_hash(SHADOW_V10),
            "1.1": _folder_hash(SHADOW_V11),
            "1.2": _folder_hash(SHADOW_V12),
        },
        "shadow_repositories_modified": False,
    }


def _lineage() -> dict[str, Any]:
    return {
        "lineage_version": "repository_version_lineage/1.2",
        "versions": [
            {
                "artifact_sha256": _folder_hash(SHADOW_V10),
                "model_schema": MODEL_SCHEMA_VERSION,
                "modified_by_this_phase": False,
                "path": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
                "repository_schema": SHADOW_REPOSITORY_VERSION,
                "status": "superseded_but_preserved",
            },
            {
                "artifact_sha256": _folder_hash(SHADOW_V11),
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "modified_by_this_phase": False,
                "path": "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
                "repository_schema": SHADOW_REPOSITORY_VERSION_V11,
                "status": "superseded_but_preserved",
            },
            {
                "artifact_sha256": _folder_hash(SHADOW_V12),
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "modified_by_this_phase": False,
                "path": (
                    "benchmarks/mtb_evidence/v3/"
                    "diagnostic_disease_scope_narrowing_shadow"
                ),
                "repository_schema": "qualified_claim_repository/1.2",
                "status": "superseded_but_preserved",
            },
            {
                "disease_gate": DISEASE.GATE_VERSION,
                "integrated_structural_gate": GATE.GATE_VERSION,
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "output_contract": OUT.OUTPUT_CONTRACT_VERSION,
                "path": (
                    "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3"
                ),
                "promoted": False,
                "repository_schema": REPOSITORY_VERSION,
                "status": MIGRATION_STATUS,
                "supersedes": "qualified_claim_repository/1.2",
                "version_bump_reason": VERSION_BUMP_REASON,
            },
        ],
    }


# --------------------------------------------------------------------------
# conteggi
# --------------------------------------------------------------------------


def repository_counts(result: Any, plans: Mapping[str, Sequence[Any]]) -> dict[str, Any]:
    domains = Counter(
        getattr(claim, "claim_domain", None) or DOMAIN_THERAPEUTIC
        for claim in result.evidence_claims
    )
    types = Counter(claim.claim_type for claim in result.evidence_claims)
    parents_without = sorted(
        row["graph_evidence_id"] for row in result.parents_without_claims
    )
    counts = {
        "active_claims_total": result.total_claims,
        "aggregate_claims": types["aggregate_intervention_claim"],
        "atomic_claims": types["atomic_intervention_claim"],
        "by_claim_type": dict(sorted(types.items())),
        "deprecated_aggregate_claims": len(result.deprecated_aggregate_claims),
        "deprecated_diagnostic_claims_from_previous_versions": len(
            result.deprecated_diagnostic_claims
        ),
        "diagnostic_claims": domains[DOMAIN_DIAGNOSTIC],
        "parents": len(result.parents),
        "parents_without_claims": len(parents_without),
        "parents_without_claims_ids": parents_without,
        "prognostic_claims": domains[DOMAIN_PROGNOSTIC],
        "qualification_plan_actions_total": len(plans["qualification"]),
        "qualification_links_to_create_local": sum(
            row.get("action") == "create_claim_link"
            and row.get("graph_evidence_id") in CANONICALIZED_GRAPH_EVIDENCE_IDS
            for row in plans["qualification"]
        ),
        "qualification_links_to_retire_local": sum(
            row.get("action") == "retire_claim_link"
            and row.get("graph_evidence_id") in CANONICALIZED_GRAPH_EVIDENCE_IDS
            for row in plans["qualification"]
        ),
        "regimen_claims": types["regimen_claim"],
        "replacement_aggregate_claims": len(result.replacement_lineage),
        "therapeutic_claims": domains[DOMAIN_THERAPEUTIC],
        "unresolved_associations": len(result.unresolved),
        "unsupported_associations": len(result.unsupported),
        "view_plan_actions_total": len(plans["view"]),
    }
    observed = {
        "active_claims_total": counts["active_claims_total"],
        "aggregate_intervention_claim": counts["aggregate_claims"],
        "atomic_intervention_claim": counts["atomic_claims"],
        "diagnostic_claims": counts["diagnostic_claims"],
        "parents": counts["parents"],
        "parents_without_claims": counts["parents_without_claims"],
        "prognostic_claims": counts["prognostic_claims"],
        "regimen_claim": counts["regimen_claims"],
        "therapeutic_claims": counts["therapeutic_claims"],
        "unresolved_associations": counts["unresolved_associations"],
        "unsupported_associations": counts["unsupported_associations"],
    }
    if observed != EXPECTED_COUNTS:
        divergent = {
            key: (value, EXPECTED_COUNTS[key])
            for key, value in observed.items()
            if value != EXPECTED_COUNTS[key]
        }
        raise RuntimeError(f"conteggi divergenti dalle precondizioni: {divergent}")
    return counts


# --------------------------------------------------------------------------
# generazione
# --------------------------------------------------------------------------


def build_data_artifacts(reverse: bool = False) -> dict[str, str]:
    """Artefatti dati della 1.3, generati in memoria e in ordine canonico."""
    before = {path: _sha256_file(REPO_ROOT / path) for path in OPERATIONAL_ARTIFACTS}

    result = run_migration(reverse)
    queries = all_queries(reverse)

    qualification_plan = _qualification_plan(result)
    view_plan = _view_plan(result)
    gate_rows, gate_scope = simulate_gate(result, queries)
    query_rows = simulate_queries(result, queries)
    regression_rows = simulate_regressions(result, gate_rows)
    probe = parent_probe(result, queries)
    if probe["parents_ever_primary"]:
        raise RuntimeError("un contenitore di provenienza e' entrato nel bucket primario")

    claim_rows = _claim_rows(result)
    after = {path: _sha256_file(REPO_ROOT / path) for path in OPERATIONAL_ARTIFACTS}
    inventory = _inventory(before, after) | {
        "gate_simulation_scope": gate_scope,
        "parent_probe": probe,
    }

    by_domain = {
        domain: [row for row in claim_rows if row["claim_domain"] == domain]
        for domain in (DOMAIN_THERAPEUTIC, DOMAIN_DIAGNOSTIC, DOMAIN_PROGNOSTIC)
    }
    deprecated_rows = [
        row | {"deprecation_origin": "terminology_canonicalization"}
        for row in result.deprecated_aggregate_claims
    ] + [
        row | {"deprecation_origin": "diagnostic_disease_scope_narrowing"}
        for row in result.deprecated_diagnostic_claims
    ]

    artifacts = {
        "graph_evidence_parents_v1_3.jsonl": canonical_jsonl(
            [
                parent.to_dict()
                | {
                    "repository_version": REPOSITORY_VERSION,
                    "schema_version": MODEL_SCHEMA_VERSION_V11,
                }
                for parent in result.parents
            ],
            key="graph_evidence_id",
        ),
        "evidence_claims_v1_3.jsonl": canonical_jsonl(claim_rows, key="claim_id"),
        "therapeutic_claims_v1_3.jsonl": canonical_jsonl(
            by_domain[DOMAIN_THERAPEUTIC], key="claim_id"
        ),
        "diagnostic_claims_v1_3.jsonl": canonical_jsonl(
            by_domain[DOMAIN_DIAGNOSTIC], key="claim_id"
        ),
        "prognostic_claims_v1_3.jsonl": canonical_jsonl(
            by_domain[DOMAIN_PROGNOSTIC], key="claim_id"
        ),
        "deprecated_claims_v1_3.jsonl": canonical_jsonl(
            deprecated_rows, key="claim_id"
        ),
        "unsupported_associations_v1_3.jsonl": canonical_jsonl(
            [item.to_dict() for item in result.unsupported], key="association_id"
        ),
        "unresolved_associations_v1_3.jsonl": canonical_jsonl(
            [item.to_dict() for item in result.unresolved], key="association_id"
        ),
        "claim_replacement_lineage_v1_3.jsonl": canonical_jsonl(
            list(result.replacement_lineage), key="old_claim_id"
        ),
        "terminology_registry_v1_3.json": canonical_dumps(terminology_registry(result)),
        "qualification_link_regeneration_plan_v1_3.jsonl": canonical_jsonl(
            qualification_plan, key="plan_id"
        ),
        "qualified_view_regeneration_plan_v1_3.jsonl": canonical_jsonl(
            view_plan, key="plan_id"
        ),
        "integrated_structural_gate_simulation.jsonl": canonical_jsonl(
            [row for row in gate_rows if _is_informative(row)],
            key=["query_id", "object_id"],
        ),
        "query_retrieval_simulation_v1_3.jsonl": canonical_jsonl(
            query_rows, key=["query_id", "policy_mode"]
        ),
        "regression_case_simulation_v1_3.jsonl": canonical_jsonl(
            regression_rows, key="case_id"
        ),
        "operational_vs_shadow_inventory_v1_3.json": canonical_dumps(inventory),
        "repository_version_lineage.json": canonical_dumps(_lineage()),
    }
    return dict(sorted(artifacts.items()))


def build(reverse: bool = False) -> dict[str, str]:
    """Tutti gli artefatti della fase, documenti e manifest compresi."""
    artifacts = build_data_artifacts(reverse)
    try:
        from benchmarks.mtb_evidence.evaluation.integrated_shadow_repository_reports import (
            build_reports,
        )
    except ImportError:  # pragma: no cover - i report arrivano con il commit docs
        return artifacts
    return dict(sorted((artifacts | build_reports(artifacts, reverse)).items()))


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    unexpected = {
        path.name for path in output.iterdir() if path.is_file()
    } - set(artifacts)
    if unexpected:
        raise RuntimeError(
            f"output contiene artefatti non controllati: {sorted(unexpected)}"
        )
    for name, text in sorted(artifacts.items()):
        (output / name).write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    args = parser.parse_args()
    artifacts = build(reverse=args.reverse_input_order)
    write(args.output, artifacts)
    print(
        canonical_dumps(
            {
                "active_claims": EXPECTED_COUNTS["active_claims_total"],
                "artifacts": len(artifacts),
                "output": args.output.as_posix(),
                "repository_schema": REPOSITORY_VERSION,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
