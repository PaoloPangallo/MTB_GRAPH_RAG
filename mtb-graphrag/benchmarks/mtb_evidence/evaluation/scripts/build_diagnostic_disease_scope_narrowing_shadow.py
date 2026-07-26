"""Genera il repository shadow 1.2 con disease scope diagnostico ristretto.

La generazione parte dallo shadow 1.1 autenticato, applica soltanto le due
decisioni della source closure e mantiene modello, gate e output contract alla
versione 1.1. Non scrive nel corpus o nei moduli operativi e non esegue i piani
di link/view prodotti.
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
from backend.pipeline.evidence.shadow import domain_gates as GATE
from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
)
from backend.pipeline.evidence.shadow.identity import (
    NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
    NON_THERAPEUTIC_IDENTITY_FIELDS,
)
from backend.pipeline.evidence.shadow.migration_v12 import (
    CURRENT_DISEASE_SCOPE,
    DEPRECATION_REASON,
    DEPRECATION_STATUS,
    NARROWED_DISEASE_SCOPE,
    REPOSITORY_VERSION,
    REQUIRED_GRAPH_EVIDENCE_IDS,
    SCOPE_NARROWING_REASON,
    SOURCE_UNIT_ID,
    narrow_reviewed_diagnostic_claims,
)
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    MODEL_SCHEMA_VERSION_V11,
    OUTPUT_CONTRACT_VERSION_V11,
    SHADOW_REPOSITORY_VERSION,
    SHADOW_REPOSITORY_VERSION_V11,
    STRUCTURAL_GATE_VERSION_V11,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_non_therapeutic_shadow_update import (
    run_migration as run_v11,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SOURCE_CLOSURE = V3 / "non_therapeutic_source_closure"
DEFAULT_OUTPUT = V3 / "diagnostic_disease_scope_narrowing_shadow"
CORPUS = V3 / "qualification_corpus_v2"
SCORING_CONFIG = (
    REPO_ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)

EXPECTED_NEW_IDS = {
    "evidence:1846": "CLM-8941c177da91f66ff93a",
    "evidence:1847": "CLM-a7e1c40b794d2c4d4ca8",
}
OPERATIONAL_QUERY_BASELINE_SHA256 = (
    "af0389673a9a8b0566bce20bf68685b3abc04baf8542e183888d9a84cb365124"
)
CORPUS_FINGERPRINT = (
    "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"
)

OPERATIONAL_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
    "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/frozen_v2_results.jsonl",
)

FROZEN_SCIENTIFIC_ARTIFACTS = (
    "benchmarks/mtb_evidence/v3/non_therapeutic_source_closure/review_manifest.json",
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/contract_manifest.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/adjudication_erratum.json",
    "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/migration_specification_amended.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/adjudication_manifest.json",
    "benchmarks/mtb_evidence/v3/qualified_retriever_prototype/prototype_manifest.json",
)

# Autenticati nel preflight come byte, mai deserializzati dal generatore.
REFERENCE_EVALUATION_SHA256 = {
    "clinical_reference": (
        "c26e526883912b3613a795fb286dd602ff81204f3ca25bbecddf83886bc11c2d"
    ),
    "snapshot_reference": (
        "02b64780ddbbd3d5bd92326b39596c76f16644599bcdbccfd8c578c1d800c845"
    ),
}

FGFR2_BICC1 = "FGFR2::BICC1 Fusion"
FGFR2_AHCYL1 = "FGFR2::AHCYL1 Fusion"

SHADOW_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "query_id": "D-ICCA-BICC1",
        "scenario": "diagnostic_exact_icca_bicc1",
        "query_domain": "diagnostic_evidence_query",
        "disease": NARROWED_DISEASE_SCOPE,
        "biomarker": FGFR2_BICC1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "D-ICCA-AHCYL1",
        "scenario": "diagnostic_exact_icca_ahcyl1",
        "query_domain": "diagnostic_evidence_query",
        "disease": NARROWED_DISEASE_SCOPE,
        "biomarker": FGFR2_AHCYL1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "D-GENERIC-BICC1",
        "scenario": "diagnostic_generic_cholangiocarcinoma_not_exact",
        "query_domain": "diagnostic_evidence_query",
        "disease": CURRENT_DISEASE_SCOPE,
        "biomarker": FGFR2_BICC1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "T-ICCA-BICC1",
        "scenario": "therapeutic_query_excludes_diagnostic_primary",
        "query_domain": "therapeutic_evidence_query",
        "disease": NARROWED_DISEASE_SCOPE,
        "biomarker": FGFR2_BICC1,
        "polarity": "supports",
        "interventions": [],
    },
    {
        "query_id": "U-ICCA-FGFR2",
        "scenario": "untyped_fgfr2_family_sectioned",
        "query_domain": None,
        "disease": NARROWED_DISEASE_SCOPE,
        "biomarker": None,
        "biomarker_literal": "FGFR2 fusion",
        "polarity": "supports",
        "interventions": [],
    },
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _inputs(reverse: bool = False):
    base = run_v11(reverse)
    reviews = load_jsonl(SOURCE_CLOSURE / "diagnostic_claim_reviews.jsonl")
    if reverse:
        reviews = list(reversed(reviews))
    source_review = json.loads(
        (SOURCE_CLOSURE / "pmid_24122810_source_unit_review.json").read_text(
            encoding="utf-8"
        )
    )
    result = narrow_reviewed_diagnostic_claims(base, reviews, source_review)
    actual = {
        claim.graph_evidence_id: claim.claim_id
        for claim in result.diagnostic_claims
    }
    if actual != EXPECTED_NEW_IDS:
        raise RuntimeError(
            f"claim ID ricalcolati inattesi: attesi {EXPECTED_NEW_IDS}, trovati {actual}"
        )
    return base, result, {row["graph_evidence_id"]: row for row in reviews}


def run_update(reverse: bool = False):
    """Restituisce il risultato 1.2 senza scrivere file."""
    return _inputs(reverse)[1]


def _claim_row(claim: Any, result: Any) -> dict[str, Any]:
    payload = claim.to_dict()
    payload.setdefault("claim_domain", DOMAIN_THERAPEUTIC)
    payload["schema_version"] = MODEL_SCHEMA_VERSION_V11
    if payload["claim_domain"] != DOMAIN_DIAGNOSTIC:
        return payload

    replacement = next(
        row
        for row in result.replacement_map
        if row["replacement_claim_id"] == claim.claim_id
    )
    payload.update(
        {
            "review_independence": result.source_review["review_independence"],
            "access_type": "abstract_only",
            "full_text_available": False,
            "diagnostic_utility_asserted": False,
            "validated_clinical_test_asserted": False,
            "identity_payload_fields": list(NON_THERAPEUTIC_IDENTITY_FIELDS),
            "prevalence": {
                "value_percent": 13.6,
                "level": "aggregate_fgfr2_fusions",
                "partner_specific": False,
                "source_population": NARROWED_DISEASE_SCOPE,
            },
            "scope_narrowing_reason_code": SCOPE_NARROWING_REASON,
            "source_review_id": replacement["source_review_id"],
        }
    )
    return payload


def _qualification_plan(
    result: Any,
    reviews: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_ids = {row["legacy_or_shadow_claim_id"] for row in result.replacement_map}
    previous = load_jsonl(
        SHADOW_V11 / "qualification_link_regeneration_plan_v1_1.jsonl"
    )
    rows = [
        row
        for row in previous
        if not (
            row.get("action") == "create_claim_link"
            and row.get("claim_id") in old_ids
        )
    ]
    active = {
        claim.graph_evidence_id: claim for claim in result.diagnostic_claims
    }
    deprecated = {
        row["graph_evidence_id"]: row
        for row in result.deprecated_diagnostic_claims
    }
    for graph_evidence_id in REQUIRED_GRAPH_EVIDENCE_IDS:
        new = active[graph_evidence_id]
        old = deprecated[graph_evidence_id]
        shared = {
            "graph_evidence_id": graph_evidence_id,
            "claim_domain": DOMAIN_DIAGNOSTIC,
            "claim_type": "diagnostic_claim",
            "source_unit_id": SOURCE_UNIT_ID,
            "locators": [dict(locator) for locator in new.locators],
            "qualification_status": "source_reviewed_prototype_only",
            "review_status": result.source_review["review_status"],
            "propagation_policy": result.source_review["propagation_policy"],
            "therapeutic_qualifiers_created": False,
            "executed": False,
        }
        rows.append(
            shared
            | {
                "plan_id": f"RETIRE-CLAIM-LINK-{old['claim_id']}",
                "action": "retire_claim_link",
                "claim_id": old["claim_id"],
                "replacement_claim_id": new.claim_id,
                "reason_code": DEPRECATION_REASON,
            }
        )
        rows.append(
            shared
            | {
                "plan_id": f"CREATE-CLAIM-LINK-{new.claim_id}",
                "action": "create_claim_link",
                "claim_id": new.claim_id,
                "replaces_claim_id": old["claim_id"],
                "reason_code": SCOPE_NARROWING_REASON,
                "review_locator": reviews[graph_evidence_id]["required_narrowing"][0][
                    "locator"
                ],
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def _view_plan(result: Any) -> list[dict[str, Any]]:
    rows = []
    old_by_parent = {
        row["graph_evidence_id"]: row for row in result.deprecated_diagnostic_claims
    }
    for claim in result.diagnostic_claims:
        old = old_by_parent[claim.graph_evidence_id]
        rows.append(
            {
                "plan_id": f"REGENERATE-DIAGNOSTIC-VIEW-{claim.graph_evidence_id}",
                "action": "regenerate_diagnostic_view",
                "graph_evidence_id": claim.graph_evidence_id,
                "parent_id": claim.parent_id,
                "old_claim_id": old["claim_id"],
                "claim_id": claim.claim_id,
                "claim_domain": DOMAIN_DIAGNOSTIC,
                "disease_scope": claim.disease_scope,
                "therapy_score_present": False,
                "intervention_representation": None,
                "cross_domain_ranking": False,
                "operational_view_unchanged": True,
                "executed": False,
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def _gate_simulation(
    base: Any,
    result: Any,
    queries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    active = list(result.diagnostic_claims)
    deprecated = [replace(claim, deprecated=True) for claim in base.diagnostic_claims]
    old_ids = {claim.claim_id for claim in deprecated}
    rows: list[dict[str, Any]] = []
    for query in sorted(queries, key=lambda row: row["query_id"]):
        for claim in sorted(active + deprecated, key=lambda item: item.claim_id):
            match = GATE.evaluate(query, claim)
            row = match.to_dict()
            row.update(
                {
                    "query_id": query["query_id"],
                    "scenario": query["scenario"],
                    "query": dict(query),
                    "object_id": claim.claim_id,
                    "retirement_status": (
                        "deprecated_replaced"
                        if claim.claim_id in old_ids
                        else "active"
                    ),
                    "disease_hierarchy_applied": False,
                    "alias_rule_applied": False,
                    "strict_disease_policy": True,
                    "scoring_applied": False,
                    "family_literal_candidate_enumeration_only": (
                        query["query_id"] == "U-ICCA-FGFR2"
                    ),
                }
            )
            rows.append(row)
    return sorted(rows, key=lambda row: (row["query_id"], row["object_id"]))


def _scope_audit(
    result: Any,
    reviews: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_by_parent = {
        row["graph_evidence_id"]: row for row in result.deprecated_diagnostic_claims
    }
    rows = []
    for claim in result.diagnostic_claims:
        old = old_by_parent[claim.graph_evidence_id]
        rows.append(
            {
                "audit_id": f"DSN-{claim.graph_evidence_id}",
                "graph_evidence_id": claim.graph_evidence_id,
                "parent_id": claim.parent_id,
                "old_claim_id": old["claim_id"],
                "new_claim_id": claim.claim_id,
                "old_disease_scope": CURRENT_DISEASE_SCOPE,
                "new_disease_scope": NARROWED_DISEASE_SCOPE,
                "source_review_id": reviews[claim.graph_evidence_id]["review_id"],
                "source_unit_id": SOURCE_UNIT_ID,
                "source_id": "PMID:24122810",
                "reason_code": SCOPE_NARROWING_REASON,
                "prevalence_percent": 13.6,
                "prevalence_scope": "aggregate_fgfr2_fusions_only",
                "partner_specific_prevalence_asserted": False,
                "diagnostic_utility_asserted": False,
                "validated_clinical_test_asserted": False,
                "prognosis_asserted": False,
                "therapy_choice_asserted": False,
                "review_status": result.source_review["review_status"],
                "review_independence": result.source_review["review_independence"],
                "propagation_policy": result.source_review["propagation_policy"],
                "local_narrowing_only": True,
                "disease_hierarchy_modified": False,
                "terminology_mapping_resolved": False,
            }
        )
    return sorted(rows, key=lambda row: row["audit_id"])


def _audit_associations(result: Any) -> list[dict[str, Any]]:
    rows = []
    claims = {
        claim.graph_evidence_id: claim for claim in result.diagnostic_claims
    }
    for replacement in result.replacement_map:
        claim = claims[replacement["parent_id"]]
        rows.append(
            {
                "association_id": f"AUDIT-{replacement['legacy_or_shadow_claim_id']}",
                "association_type": "diagnostic_claim_replacement",
                "parent_id": replacement["parent_id"],
                "graph_parent_id": replacement["graph_parent_id"],
                "deprecated_claim_id": replacement["legacy_or_shadow_claim_id"],
                "active_claim_id": replacement["replacement_claim_id"],
                "source_unit_id": SOURCE_UNIT_ID,
                "locators": [dict(locator) for locator in claim.locators],
                "source_review_id": replacement["source_review_id"],
                "reversible": True,
            }
        )
    return sorted(rows, key=lambda row: row["association_id"])


def _folder_hash(path: Path) -> dict[str, str]:
    return {
        file.name: sha256_text(file.read_text(encoding="utf-8"))
        for file in sorted(path.iterdir())
        if file.is_file()
    }


def _lineage() -> dict[str, Any]:
    return {
        "lineage_version": "repository_version_lineage/1.1",
        "versions": [
            {
                "model_schema": MODEL_SCHEMA_VERSION,
                "repository_schema": SHADOW_REPOSITORY_VERSION,
                "path": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
                "status": "superseded_but_preserved",
                "modified_by_this_phase": False,
                "artifact_sha256": _folder_hash(SHADOW_V10),
            },
            {
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "repository_schema": SHADOW_REPOSITORY_VERSION_V11,
                "path": "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
                "status": "superseded_but_preserved",
                "modified_by_this_phase": False,
                "artifact_sha256": _folder_hash(SHADOW_V11),
            },
            {
                "model_schema": MODEL_SCHEMA_VERSION_V11,
                "repository_schema": REPOSITORY_VERSION,
                "path": (
                    "benchmarks/mtb_evidence/v3/"
                    "diagnostic_disease_scope_narrowing_shadow"
                ),
                "status": MIGRATION_STATUS,
                "supersedes": SHADOW_REPOSITORY_VERSION_V11,
                "version_bump_reason": (
                    "documentary disease-scope narrowing of reviewed diagnostic claims"
                ),
                "promoted": False,
            },
        ],
    }


def _operational_query_sha256() -> tuple[str, int]:
    retriever = QualifiedEvidenceRetriever.from_corpus(
        CORPUS,
        scoring_config_path=SCORING_CONFIG,
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


def _inventory() -> dict[str, Any]:
    after_hashes = {
        path: sha256_text((REPO_ROOT / path).read_text(encoding="utf-8"))
        for path in OPERATIONAL_ARTIFACTS
    }
    previous_manifest = json.loads(
        (SHADOW_V11 / "shadow_update_manifest.json").read_text(encoding="utf-8")
    )
    before_hashes = previous_manifest["operational_artifact_sha256"]
    query_hash, result_count = _operational_query_sha256()
    return {
        "inventory_version": "operational_vs_shadow_inventory/1.2",
        "operational_artifact_sha256_before": dict(sorted(before_hashes.items())),
        "operational_artifact_sha256_after": dict(sorted(after_hashes.items())),
        "operational_hash_parity": before_hashes == after_hashes,
        "operational_query": {
            "query_id": "scope-narrowing-operational-parity",
            "before_sha256": OPERATIONAL_QUERY_BASELINE_SHA256,
            "after_sha256": query_hash,
            "result_count": result_count,
            "parity": query_hash == OPERATIONAL_QUERY_BASELINE_SHA256,
        },
        "frozen_scientific_artifact_sha256": {
            path: sha256_text((REPO_ROOT / path).read_text(encoding="utf-8"))
            for path in FROZEN_SCIENTIFIC_ARTIFACTS
        },
        "shadow_repository_manifest_sha256": {
            "1.0": sha256_text(
                (SHADOW_V10 / "shadow_repository_manifest.json").read_text(
                    encoding="utf-8"
                )
            ),
            "1.1": sha256_text(
                (SHADOW_V11 / "shadow_update_manifest.json").read_text(
                    encoding="utf-8"
                )
            ),
        },
        "authenticated_evaluation_reference_sha256": REFERENCE_EVALUATION_SHA256,
        "evaluation_reference_authentication_only": True,
        "evaluation_reference_deserialized": False,
        "shadow_imports_into_operational_modules": 0,
        "operational_statements_still_authoritative": True,
        "shadow_objects_queryable_by_operational_pipeline": False,
    }


def _evidence_347_audit() -> dict[str, Any]:
    path = SHADOW_V11 / "evidence_347_promotion_audit.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(
        {
            "source_artifact": (
                "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update/"
                "evidence_347_promotion_audit.json"
            ),
            "source_artifact_sha256": sha256_text(path.read_text(encoding="utf-8")),
            "unchanged_by_repository_v1_2": True,
            "intervention_invented": False,
            "predictive_claim_created": False,
            "prognostic_claim_created": False,
        }
    )
    return payload


def _manifest(
    artifacts: Mapping[str, str],
    result: Any,
    qualification_plan: Sequence[Mapping[str, Any]],
    view_plan: Sequence[Mapping[str, Any]],
    simulation: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    domains = Counter(
        getattr(claim, "claim_domain", DOMAIN_THERAPEUTIC)
        for claim in result.evidence_claims
    )
    types = Counter(claim.claim_type for claim in result.evidence_claims)
    all_ids = [claim.claim_id for claim in result.evidence_claims]
    deprecated_ids = [
        row["claim_id"] for row in result.deprecated_diagnostic_claims
    ]
    collisions = len(all_ids + deprecated_ids) - len(set(all_ids + deprecated_ids))
    parents_without = sorted(
        row["graph_evidence_id"] for row in result.parents_without_claims
    )
    retired_primary = sum(
        row["object_id"] in deprecated_ids and row["primary_candidate_eligible"]
        for row in simulation
    )
    readiness = {
        "diagnostic_scope_narrowing_applied": True,
        "old_diagnostic_claims_retired": len(deprecated_ids) == 2,
        "replacement_claims_created": len(result.diagnostic_claims) == 2,
        "claim_ids_recomputed": all(
            claim.claim_id == EXPECTED_NEW_IDS[claim.graph_evidence_id]
            for claim in result.diagnostic_claims
        ),
        "repository_v1_2_ready": (
            result.total_claims == 148
            and collisions == 0
            and not retired_primary
            and inventory["operational_hash_parity"]
            and inventory["operational_query"]["parity"]
        ),
        "source_review_status_preserved": (
            result.source_review["review_status"] == "first_review_complete"
            and result.source_review["review_independence"] == "non_independent"
        ),
        "evidence_347_unchanged": True,
        "operational_artifacts_unchanged": inventory["operational_hash_parity"],
        "terminology_review_required": True,
        "disease_hierarchy_policy_required": True,
        "corpus_promotion_ready": False,
        "operational_retriever_migration_ready": False,
        "full_exploratory_rerun_ready": False,
    }
    return {
        "model_schema": MODEL_SCHEMA_VERSION_V11,
        "repository_schema": REPOSITORY_VERSION,
        "structural_gate": STRUCTURAL_GATE_VERSION_V11,
        "output_contract": OUTPUT_CONTRACT_VERSION_V11,
        "migration_status": MIGRATION_STATUS,
        "supersedes": SHADOW_REPOSITORY_VERSION_V11,
        "version_bump_reason": (
            "documentary disease-scope narrowing of reviewed diagnostic claims"
        ),
        "counts": {
            "parents": len(result.parents),
            "therapeutic_claims": domains[DOMAIN_THERAPEUTIC],
            "diagnostic_claims_active": domains[DOMAIN_DIAGNOSTIC],
            "diagnostic_claims_deprecated": len(deprecated_ids),
            "prognostic_claims": domains[DOMAIN_PROGNOSTIC],
            "active_claims_total": result.total_claims,
            "parents_without_claims": len(parents_without),
            "parents_without_claims_ids": parents_without,
            "qualification_plan_actions_total": len(qualification_plan),
            "qualification_links_to_retire_local": sum(
                row.get("action") == "retire_claim_link"
                and row.get("graph_evidence_id") in REQUIRED_GRAPH_EVIDENCE_IDS
                for row in qualification_plan
            ),
            "qualification_links_to_create_local": sum(
                row.get("action") == "create_claim_link"
                and row.get("graph_evidence_id") in REQUIRED_GRAPH_EVIDENCE_IDS
                for row in qualification_plan
            ),
            "diagnostic_views_to_regenerate_local": len(view_plan),
            "by_claim_type": dict(sorted(types.items())),
            "expected_count_forced": False,
        },
        "claim_id_formula": {
            "version": NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
            "fields": list(NON_THERAPEUTIC_IDENTITY_FIELDS),
            "separator": "|",
            "collisions": collisions,
            "new_ids": dict(sorted(EXPECTED_NEW_IDS.items())),
        },
        "source_review": {
            "source_unit_id": SOURCE_UNIT_ID,
            "review_status": result.source_review["review_status"],
            "review_independence": result.source_review["review_independence"],
            "propagation_policy": result.source_review["propagation_policy"],
            "hard_filterable": result.source_review["hard_filterable"],
            "final_evaluable": result.source_review["final_evaluable"],
            "access_type": "abstract_only",
            "full_text_available": False,
        },
        "invariants": {
            "local_narrowing_only": True,
            "aggregate_prevalence_remains_non_partner_specific": True,
            "subtype_defining_is_not_validated_diagnostic_test": True,
            "diagnostic_evidence_is_not_therapy_evidence": True,
            "deprecated_claims_primary": retired_primary,
            "disease_hierarchy_applied": False,
            "terminology_mapping_resolved": False,
            "operational_artifacts_modified": False,
            "shadow_1_0_modified": False,
            "shadow_1_1_modified": False,
            "repository_promoted": False,
            "plans_executed": False,
        },
        "readiness": readiness,
        "operational_query_sha256": inventory["operational_query"],
        "evaluation_reference_used_for_decisions": False,
        "evaluation_reference_deserialized": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
    }


def _narrowing_doc(manifest: Mapping[str, Any]) -> str:
    counts = manifest["counts"]
    return f"""# Diagnostic disease-scope narrowing

Repository: `{REPOSITORY_VERSION}`
Stato: `{MIGRATION_STATUS}`

La source closure richiede che i claim di `evidence:1846` e `evidence:1847`
descrivano **Intrahepatic Cholangiocarcinoma**, non il colangiocarcinoma
generico. I due claim 1.1 restano leggibili nell'audit e sono sostituiti da ID
ricalcolati con `{NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION}`.

## Esito

- parent: {counts['parents']}
- claim terapeutici: {counts['therapeutic_claims']}
- claim diagnostici attivi: {counts['diagnostic_claims_active']}
- claim diagnostici ritirati: {counts['diagnostic_claims_deprecated']}
- claim prognostici: {counts['prognostic_claims']}
- claim attivi totali: {counts['active_claims_total']}
- parent senza claim: {counts['parents_without_claims']}

Il 13,6% resta una prevalenza aggregata delle fusioni FGFR2 e non viene
attribuito né a BICC1 né ad AHCYL1. Non vengono affermati utilità clinica, test
diagnostico validato, prognosi, intervento o scelta terapeutica.

## Perimetro

La relazione iCCA/colangiocarcinoma non viene promossa ad alias o gerarchia
operativa. Il match resta strict: la query generica non è exact. I piani di link
e view hanno `executed = false`; corpus, adapter, repository, retriever, scoring
e QualifiedEvidenceView operative restano invariati.
"""


def _readiness_doc(manifest: Mapping[str, Any]) -> str:
    readiness = manifest["readiness"]
    lines = "\n".join(
        f"| `{name}` | **{str(value).lower()}** |"
        for name, value in sorted(readiness.items())
    )
    return f"""# Shadow repository 1.2 readiness

Repository: `{REPOSITORY_VERSION}`
Motivazione: documentary disease-scope narrowing of reviewed diagnostic claims

| Gate | Valore |
|---|---:|
{lines}

La 1.2 è pronta come repository shadow riproducibile, non come corpus
operativo. Restano richieste una review terminologica, una policy esplicita per
la disease hierarchy e una successiva decisione di promozione. Per questo
promozione del corpus, migrazione del retriever e rerun esplorativo restano
false.
"""


def _legacy_statement_deprecation_map(result: Any) -> list[dict[str, Any]]:
    """Mantiene lo schema legacy e risolve ogni statement al claim attivo."""
    replacement_by_evidence = {
        row["parent_id"]: row for row in result.replacement_map
    }
    rows = [
        json.loads(line)
        for line in (
            SHADOW_V11 / "legacy_statement_deprecation_map_v1_1.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    for row in rows:
        previous = list(row.get("replacement_claim_ids") or ())
        row["previous_replacement_claim_ids"] = previous
        replacement = replacement_by_evidence.get(row["graph_evidence_id"])
        if replacement is None:
            continue
        if previous != [replacement["legacy_or_shadow_claim_id"]]:
            raise RuntimeError(
                f"{row['graph_evidence_id']}: lineage legacy inattesa"
            )
        row["replacement_claim_ids"] = [replacement["replacement_claim_id"]]
    return rows


def build(reverse: bool = False) -> dict[str, str]:
    """Genera tutti gli artefatti in memoria, in ordine canonico."""
    base, result, reviews = _inputs(reverse)
    queries = list(reversed(SHADOW_QUERIES)) if reverse else list(SHADOW_QUERIES)

    active_rows = [_claim_row(claim, result) for claim in result.evidence_claims]
    diagnostic_rows = [
        row for row in active_rows if row["claim_domain"] == DOMAIN_DIAGNOSTIC
    ]
    qualification_plan = _qualification_plan(result, reviews)
    view_plan = _view_plan(result)
    simulation = _gate_simulation(base, result, queries)
    scope_audit = _scope_audit(result, reviews)
    inventory = _inventory()

    artifacts: dict[str, str] = {
        "graph_evidence_parents_v1_2.jsonl": canonical_jsonl(
            [
                parent.to_dict() | {"schema_version": MODEL_SCHEMA_VERSION_V11}
                for parent in result.parents
            ],
            key="graph_evidence_id",
        ),
        "evidence_claims_v1_2.jsonl": canonical_jsonl(
            active_rows,
            key="claim_id",
        ),
        "therapeutic_claims_v1_2.jsonl": (
            SHADOW_V11 / "therapeutic_claims_v1_1.jsonl"
        ).read_text(encoding="utf-8"),
        "diagnostic_claims_v1_2.jsonl": canonical_jsonl(
            diagnostic_rows,
            key="claim_id",
        ),
        "prognostic_claims_v1_2.jsonl": canonical_jsonl([], key="claim_id"),
        "deprecated_diagnostic_claims.jsonl": canonical_jsonl(
            list(result.deprecated_diagnostic_claims),
            key="claim_id",
        ),
        "diagnostic_claim_replacement_map.jsonl": canonical_jsonl(
            list(result.replacement_map),
            key="legacy_or_shadow_claim_id",
        ),
        "parent_without_claim_v1_2.jsonl": (
            SHADOW_V11 / "parent_without_claim_v1_1.jsonl"
        ).read_text(encoding="utf-8"),
        "audit_associations_v1_2.jsonl": canonical_jsonl(
            _audit_associations(result),
            key="association_id",
        ),
        "qualification_link_regeneration_plan_v1_2.jsonl": canonical_jsonl(
            qualification_plan,
            key="plan_id",
        ),
        "qualified_view_regeneration_plan_v1_2.jsonl": canonical_jsonl(
            view_plan,
            key="plan_id",
        ),
        "disease_scope_gate_simulation.jsonl": canonical_jsonl(
            simulation,
            key=["query_id", "object_id"],
        ),
        "repository_version_lineage.json": canonical_dumps(_lineage()),
        "scope_narrowing_audit.jsonl": canonical_jsonl(
            scope_audit,
            key="audit_id",
        ),
        "operational_vs_shadow_inventory_v1_2.json": canonical_dumps(inventory),
        "evidence_347_audit_v1_2.json": canonical_dumps(_evidence_347_audit()),
    }
    artifacts["legacy_statement_deprecation_map_v1_2.jsonl"] = canonical_jsonl(
        _legacy_statement_deprecation_map(result),
        key="legacy_statement_id",
    )

    repository_manifest = _manifest(
        artifacts,
        result,
        qualification_plan,
        view_plan,
        simulation,
        inventory,
    )
    artifacts["repository_v1_2_manifest.json"] = canonical_dumps(
        repository_manifest
    )
    artifacts["shadow_update_manifest.json"] = canonical_dumps(
        {
            "phase": "diagnostic_disease_scope_narrowing_shadow/1.0",
            "repository_schema": REPOSITORY_VERSION,
            "migration_status": MIGRATION_STATUS,
            "version_bump_reason": (
                "documentary disease-scope narrowing of reviewed diagnostic claims"
            ),
            "source_repository": SHADOW_REPOSITORY_VERSION_V11,
            "source_closure": "non-therapeutic-source-closure/1.0",
            "applied_claims": list(REQUIRED_GRAPH_EVIDENCE_IDS),
            "artifact_sha256": {
                name: sha256_text(text)
                for name, text in sorted(artifacts.items())
            },
            "operational_artifacts_modified": False,
            "shadow_1_0_modified": False,
            "shadow_1_1_modified": False,
            "evaluation_reference_used": False,
            "promoted": False,
        }
    )
    artifacts["DIAGNOSTIC_DISEASE_SCOPE_NARROWING.md"] = _narrowing_doc(
        repository_manifest
    )
    artifacts["SHADOW_REPOSITORY_V1_2_READINESS.md"] = _readiness_doc(
        repository_manifest
    )
    return dict(sorted(artifacts.items()))


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    expected = set(artifacts)
    existing = {path.name for path in output.iterdir() if path.is_file()}
    unexpected = existing - expected
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
                "output": args.output.as_posix(),
                "artifacts": len(artifacts),
                "repository_schema": REPOSITORY_VERSION,
                "active_claims": 148,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
