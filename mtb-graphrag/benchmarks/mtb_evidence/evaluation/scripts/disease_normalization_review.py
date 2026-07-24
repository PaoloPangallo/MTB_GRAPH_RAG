"""Review deterministica e read-only della normalizzazione disease V2/V3."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.pipeline.evidence._normalize import normalize_text
from backend.pipeline.evidence.qualified_retrieval_query import build_query
from backend.pipeline.evidence.qualified_retriever import (
    _native_match,
    match_biomarker,
)
from benchmarks.mtb_evidence.evaluation.scripts.candidate_coverage_audit import (
    EXPECTED_AUTHOR_APPROVAL_HASH,
    EXPECTED_CORPUS_DIRECTORY_HASH,
    EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
    EXPECTED_GOLD_HASH,
    EXPECTED_PRIOR_EXPLORATION_HASH,
    EXPECTED_RETRIEVER_HASH,
    EXPECTED_SCORING_FILE_HASH,
    EXPECTED_SECOND_REVIEW_HASH,
    _aggregate,
)
from benchmarks.mtb_evidence.evaluation.scripts.v2_v3a_exploratory import (
    EXPECTED_CORPUS_FINGERPRINT,
    EXPECTED_FROZEN_KG_FINGERPRINT,
    EXPECTED_GOLD_FILES,
    EXPECTED_SCORING_HASH,
    _bundle_guard,
)
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    DIFFERENT_SPECIFICITY,
    IDENTICAL,
    SAME_ENTITY,
    _SUBTYPE_OF,
    disease_relation,
    split_disease,
)


REVIEW_VERSION = "disease-normalization-review/1.0"
SOURCE_SHA = "1262b4484e132f0c8ff96593b04db82bb3eee876"
EXPECTED_CANDIDATE_AUDIT_HASH = (
    "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
)
EXPECTED_CONJUNCTIVE_FIX_HASH = (
    "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41d88638d"
)
EXPECTED_AFTER_COUNTS = {
    "PILOT-A2-ALK-G1202R": 9,
    "PILOT-C1-EGFR-L858R-CONTEXT": 10,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}
TARGET_CASES = (
    "PILOT-C1-EGFR-L858R-CONTEXT",
    "PILOT-K1-FGFR2-iCCA",
)
EXPLICIT_EVIDENCE_IDS = (
    "evidence:11219",
    "evidence:11598",
    "evidence:11599",
    "evidence:1867",
    "evidence:8173",
)
TRAVERSAL_SEMANTICS = {
    "evidence_containing_l858r": "biomarker_only",
    "evidence_for_osimertinib": "intervention_neighborhood",
    "evidence_citing_expected_pmids": "source_neighborhood",
    "evidence_fusion_profiles_only": "biomarker_only",
    "evidence_by_gene_traversal": "gene_neighborhood",
    "evidence_for_expected_drugs": "intervention_neighborhood",
}
POLICY_RELATIONS = {
    "exact_string_match",
    "normalized_exact_match",
    "verified_alias_match",
    "explicit_same_identifier",
}
POLICY_B_HIERARCHY = {
    "explicit_parent_child_relation",
    "explicit_ancestor_descendant_relation",
    "broader_disease_label",
    "narrower_disease_label",
}


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_statement(statement: Mapping[str, Any]) -> Mapping[str, Any]:
    return statement.get("base_statement") or statement


def _statement_id(statement: Mapping[str, Any]) -> str:
    base = _base_statement(statement)
    return str(
        statement.get("statement_id")
        or base.get("evidence_statement_id")
        or base.get("statement_id")
        or ""
    )


def _label(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("label") or "")
    return str(value or "")


def _canonical_core(value: Any) -> str:
    # Lo slash in "advanced/metastatic NSCLC" separa qualificatori, non entità.
    # La trasformazione è soltanto di punteggiatura e non introduce sinonimi.
    return split_disease(str(value or "").replace("/", " ")).core


def _parent(core: str) -> str | None:
    if core in _SUBTYPE_OF:
        return _SUBTYPE_OF[core]
    for candidate in sorted(_SUBTYPE_OF):
        if disease_relation(core, candidate) == SAME_ENTITY:
            return _SUBTYPE_OF[candidate]
    return None


def _relation_evidence(
    query_core: str, statement_core: str
) -> tuple[str, dict[str, Any] | None]:
    query_parent = _parent(query_core)
    statement_parent = _parent(statement_core)
    artifact = "benchmarks/mtb_evidence/pilot/audit_lib/disease.py"
    if query_parent and disease_relation(query_parent, statement_core) in {
        IDENTICAL,
        SAME_ENTITY,
    }:
        return "broader_disease_label", {
            "artifact": artifact,
            "edge": f"{query_core} -> {query_parent}",
            "direction": "statement_is_parent_of_query",
        }
    if statement_parent and disease_relation(statement_parent, query_core) in {
        IDENTICAL,
        SAME_ENTITY,
    }:
        return "narrower_disease_label", {
            "artifact": artifact,
            "edge": f"{statement_core} -> {statement_parent}",
            "direction": "statement_is_child_of_query",
        }
    if (
        query_parent
        and statement_parent
        and disease_relation(query_parent, statement_parent)
        in {IDENTICAL, SAME_ENTITY}
    ):
        return "same_organ_different_subtype", {
            "artifact": artifact,
            "edges": [
                f"{query_core} -> {query_parent}",
                f"{statement_core} -> {statement_parent}",
            ],
            "direction": "explicit_siblings_not_equivalent",
        }
    return "", None


def _classify_disease(
    query_payload: Mapping[str, Any],
    statement_disease: str,
    statement_disease_id: str,
) -> dict[str, Any]:
    query_raw = str(query_payload.get("disease") or "")
    aliases = [str(item) for item in query_payload.get("disease_aliases") or []]
    query_core = _canonical_core(query_raw)
    statement_core = _canonical_core(statement_disease)
    query_id = str(query_payload.get("disease_id") or "")
    alias_contract_match = next(
        (
            alias
            for alias in aliases
            if disease_relation(alias, statement_disease)
            in {IDENTICAL, SAME_ENTITY}
        ),
        None,
    )
    alias_contract_relation = (
        disease_relation(query_core, alias_contract_match)
        if alias_contract_match
        else None
    )
    if not query_raw:
        classification = "disease_missing_in_query"
        relation = "missing"
        evidence = None
        alias_source = None
    elif not statement_disease or statement_core in {"", "unknown"}:
        classification = "disease_missing_in_statement"
        relation = "missing"
        evidence = None
        alias_source = None
    elif query_id and statement_disease_id and query_id == statement_disease_id:
        classification = "explicit_same_identifier"
        relation = "same_identifier"
        evidence = {"query_id": query_id, "statement_id": statement_disease_id}
        alias_source = None
    elif query_raw == statement_disease:
        classification = "exact_string_match"
        relation = IDENTICAL
        evidence = None
        alias_source = None
    elif query_core and query_core == statement_core:
        classification = "normalized_exact_match"
        relation = IDENTICAL
        evidence = None
        alias_source = None
    else:
        verified_alias = (
            alias_contract_match
            if alias_contract_relation in {IDENTICAL, SAME_ENTITY}
            else None
        )
        if verified_alias:
            classification = "verified_alias_match"
            relation = SAME_ENTITY
            evidence = {
                "artifacts": [
                    (
                        "benchmarks/mtb_evidence/v3/v2_v3a_exploratory_pilot/"
                        "evaluation_queries.jsonl"
                    ),
                    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
                ],
                "alias": verified_alias,
                "alias_to_primary_relation": alias_contract_relation,
            }
            alias_source = "existing_local_normalizer"
        elif disease_relation(query_core, statement_core) == SAME_ENTITY:
            classification = "verified_alias_match"
            relation = SAME_ENTITY
            evidence = {
                "artifact": "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
                "relation": SAME_ENTITY,
            }
            alias_source = "existing_local_normalizer"
        else:
            hierarchy, evidence = _relation_evidence(query_core, statement_core)
            if hierarchy:
                classification = hierarchy
                relation = DIFFERENT_SPECIFICITY
                alias_source = None
            elif statement_core in {"cancer", "malignancy", "pan cancer", "pan-cancer"}:
                classification = "pan_cancer_or_unspecified_context"
                relation = "unspecified"
                alias_source = None
            else:
                classification = "ontology_relation_not_available"
                relation = "unresolved_without_external_or_document_review"
                evidence = None
                alias_source = None
    return {
        "disease_relation_classification": classification,
        "disease_relation": relation,
        "local_relation_evidence": evidence,
        "alias_source": alias_source,
        "query_disease_raw": query_raw,
        "query_disease_normalized": query_core,
        "query_disease_id": query_id or None,
        "query_disease_aliases": aliases,
        "query_alias_contract_match": alias_contract_match,
        "query_alias_to_primary_relation": alias_contract_relation,
        "statement_disease_raw": statement_disease,
        "statement_disease_normalized": statement_core,
        "statement_disease_id": statement_disease_id or None,
    }


def _integrity(root: Path, gold_bundle: Path) -> dict[str, Any]:
    v3 = root / "benchmarks" / "mtb_evidence" / "v3"
    paths = {
        "qualification_corpus": v3 / "qualification_corpus_v2",
        "candidate_coverage_audit": v3 / "candidate_coverage_audit",
        "conjunctive_biomarker_fix": v3 / "conjunctive_biomarker_fix",
        "previous_exploration": v3 / "v2_v3a_exploratory_pilot",
        "second_review_packets": (
            v3 / "priority_curation" / "annotation_packets" / "second_review"
        ),
    }
    approvals = [
        v3 / "author_approval",
        v3 / "author_approval_22235099",
        v3 / "author_approval_23344087",
    ]
    retriever_files = sorted(
        (root / "backend" / "pipeline" / "evidence").glob("qualified_retriev*"),
        key=lambda item: item.name.casefold(),
    )
    actual = {name: _aggregate(root, [path]) for name, path in paths.items()}
    actual["author_approval"] = _aggregate(root, approvals)
    actual["retriever"] = _aggregate(root, retriever_files)
    frozen_serialization = _aggregate(
        root,
        sorted(
            (
                root / "benchmarks" / "mtb_evidence" / "pilot" / "audit"
            ).glob("*/normalized_records.jsonl"),
            key=lambda item: item.as_posix().casefold(),
        ),
    )
    actual["frozen_v2_serialization"] = frozen_serialization
    config = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    scoring = json.loads(config.read_text(encoding="utf-8"))
    manifest = json.loads(
        (
            v3
            / "qualification_corpus_v2"
            / "qualification_corpus_manifest.json"
        ).read_text(encoding="utf-8")
    )
    expected = {
        "qualification_corpus": EXPECTED_CORPUS_DIRECTORY_HASH,
        "candidate_coverage_audit": EXPECTED_CANDIDATE_AUDIT_HASH,
        "conjunctive_biomarker_fix": EXPECTED_CONJUNCTIVE_FIX_HASH,
        "previous_exploration": EXPECTED_PRIOR_EXPLORATION_HASH,
        "second_review_packets": EXPECTED_SECOND_REVIEW_HASH,
        "author_approval": EXPECTED_AUTHOR_APPROVAL_HASH,
        "retriever": EXPECTED_RETRIEVER_HASH,
        "frozen_v2_serialization": EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
    }
    mismatches = {
        name: {
            "actual": actual[name]["aggregate_sha256"],
            "expected": digest,
        }
        for name, digest in expected.items()
        if actual[name]["aggregate_sha256"] != digest
    }
    if _sha(config) != EXPECTED_SCORING_FILE_HASH:
        mismatches["scoring_file"] = {
            "actual": _sha(config),
            "expected": EXPECTED_SCORING_FILE_HASH,
        }
    if scoring.get("hash") != EXPECTED_SCORING_HASH:
        mismatches["scoring_hash"] = {
            "actual": scoring.get("hash"),
            "expected": EXPECTED_SCORING_HASH,
        }
    if (
        manifest.get("qualification_corpus_fingerprint")
        != EXPECTED_CORPUS_FINGERPRINT
    ):
        mismatches["corpus_fingerprint"] = {
            "actual": manifest.get("qualification_corpus_fingerprint"),
            "expected": EXPECTED_CORPUS_FINGERPRINT,
        }
    if (
        manifest.get("frozen_kg_snapshot_fingerprint")
        != EXPECTED_FROZEN_KG_FINGERPRINT
    ):
        mismatches["frozen_kg_fingerprint"] = {
            "actual": manifest.get("frozen_kg_snapshot_fingerprint"),
            "expected": EXPECTED_FROZEN_KG_FINGERPRINT,
        }
    if mismatches:
        raise RuntimeError(f"frozen input mismatch: {mismatches}")
    gold = _bundle_guard(gold_bundle, EXPECTED_GOLD_HASH)
    if set(gold["file_sha256"]) != set(EXPECTED_GOLD_FILES):
        raise RuntimeError("gold member inventory mismatch")
    after = _read_jsonl(
        v3 / "conjunctive_biomarker_fix" / "candidate_set_after.jsonl"
    )
    after_counts = Counter(str(row["case_id"]) for row in after)
    if dict(sorted(after_counts.items())) != {
        key: value for key, value in EXPECTED_AFTER_COUNTS.items() if value
    }:
        raise RuntimeError(
            f"post-fix candidate count mismatch: {dict(after_counts)}"
        )
    return {
        **actual,
        "scoring_config": {
            "file_sha256": _sha(config),
            "canonical_hash": scoring["hash"],
        },
        "gold_bundle": gold,
        "corpus_fingerprint": manifest["qualification_corpus_fingerprint"],
        "frozen_kg_fingerprint": manifest["frozen_kg_snapshot_fingerprint"],
        "post_fix_candidate_counts": EXPECTED_AFTER_COUNTS,
    }


def _correction_for(row: Mapping[str, Any]) -> dict[str, Any]:
    classification = str(row["disease_relation_classification"])
    biomarker_match = bool(row["biomarker_match_after_fix"])
    if not biomarker_match:
        correction = "should_remain_excluded"
        safe = True
        rationale = "Il record non soddisfa il contratto biomarcatore congiuntivo."
    elif classification in POLICY_RELATIONS:
        correction = (
            "safe_verified_alias"
            if classification == "verified_alias_match"
            else "no_correction_needed"
        )
        safe = True
        rationale = "La relazione è già dimostrata da dati locali verificati."
    elif classification in POLICY_B_HIERARCHY:
        correction = "explicit_hierarchy_support"
        safe = False
        rationale = "La relazione locale è esplicita ma richiede una policy non-equivalente."
    elif classification == "same_organ_different_subtype":
        correction = "domain_review_required"
        safe = False
        rationale = "I termini sono fratelli espliciti, non equivalenti."
    elif classification == "pan_cancer_or_unspecified_context":
        correction = "candidate_generation_policy_change"
        safe = False
        rationale = "Un contesto generico richiede una decisione di retrieval."
    else:
        correction = "external_ontology_required"
        safe = False
        rationale = "I dati locali non rappresentano la relazione."
    return {
        "correction_class": correction,
        "safe_without_semantic_decision": safe,
        "correction_applied": False,
        "rationale": rationale,
    }


def _policy_simulation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    definitions = [
        (
            "A",
            "strict_exact",
            lambda row: row["biomarker_match_after_fix"]
            and row["disease_relation_classification"] in POLICY_RELATIONS,
        ),
        (
            "B",
            "explicit_ontology_aware",
            lambda row: row["biomarker_match_after_fix"]
            and row["disease_relation_classification"]
            in POLICY_RELATIONS | POLICY_B_HIERARCHY,
        ),
        (
            "C",
            "broad_candidate_generation_soft_disease_ranking",
            lambda row: row["biomarker_match_after_fix"],
        ),
        ("D", "v2_high_recall_v3_qualification", lambda row: True),
    ]
    policy_rows: list[dict[str, Any]] = []
    for policy_id, name, predicate in definitions:
        queries: list[dict[str, Any]] = []
        for case_id in TARGET_CASES:
            source = [row for row in rows if row["case_id"] == case_id]
            selected = [row for row in source if predicate(row)]
            queries.append(
                {
                    "case_id": case_id,
                    "row_count": len(selected),
                    "unique_graph_evidence_count": len(
                        {row["graph_evidence_id"] for row in selected}
                    ),
                    "cross_disease_row_count": sum(
                        row["disease_relation_classification"]
                        not in POLICY_RELATIONS
                        for row in selected
                    ),
                    "biomarker_mismatch_row_count": sum(
                        not row["biomarker_match_after_fix"] for row in selected
                    ),
                    "cross_gene_row_count": sum(
                        row["query_gene_normalized"]
                        != normalize_text(row["statement_gene"])
                        for row in selected
                    ),
                }
            )
        policy_rows.append(
            {
                "policy_id": policy_id,
                "name": name,
                "queries": queries,
                "false_positive_risk": (
                    "low"
                    if policy_id == "A"
                    else "bounded_but_requires_review"
                    if policy_id == "B"
                    else "elevated"
                ),
                "explainability": (
                    "high" if policy_id in {"A", "B"} else "high_with_warnings"
                ),
                "graphrag_compatibility": True,
                "clinical_review_required": policy_id != "A",
                "corpus_impact": "none",
                "retriever_impact": (
                    "verified_alias_contract_and_local_normalizer"
                    if policy_id == "A"
                    else "candidate_generation_policy"
                    if policy_id in {"B", "C"}
                    else "hybrid_candidate_provider"
                ),
            }
        )
    return {
        "version": "disease-policy-simulation/1.0",
        "unit_of_count": ["frozen_v2_row", "unique_graph_evidence_id"],
        "policy_contract_frozen_before_results": True,
        "policies": policy_rows,
        "gold_used": False,
        "clinical_metrics_computed": False,
        "p_values_computed": False,
    }


def generate_review(
    root: Path,
    output: Path,
    gold_bundle: Path,
    *,
    reverse_input_order: bool = False,
) -> dict[str, Any]:
    """Genera artefatti senza leggere record gold o contenuti PMID."""
    integrity = _integrity(root, gold_bundle)
    v3 = root / "benchmarks" / "mtb_evidence" / "v3"
    queries = _read_jsonl(
        v3 / "v2_v3a_exploratory_pilot" / "evaluation_queries.jsonl"
    )
    query_by_case = {str(row["case_id"]): row for row in queries}
    statements_raw = _read_jsonl(
        v3 / "qualification_corpus_v2" / "evidence_statements.jsonl"
    )
    statement_by_id = {
        _statement_id(statement): _base_statement(statement)
        for statement in statements_raw
    }
    active_units = {
        str(row["profile_unit_id"]): row
        for row in _read_jsonl(
            v3
            / "qualification_corpus_v2"
            / "active_source_profile_units.jsonl"
        )
    }
    lineage = [
        row
        for row in _read_jsonl(
            v3 / "candidate_coverage_audit" / "candidate_lineage.jsonl"
        )
        if row["case_id"] in TARGET_CASES
    ]
    if reverse_input_order:
        lineage.reverse()
    output.mkdir(parents=True, exist_ok=True)
    audited: list[dict[str, Any]] = []
    traversal_rows: list[dict[str, Any]] = []
    for lineage_row in lineage:
        case_id = str(lineage_row["case_id"])
        query_payload = query_by_case[case_id]
        query = build_query(query_payload)
        statement = statement_by_id[str(lineage_row["statement_id"])]
        disease = statement.get("disease") or {}
        statement_disease = _label(disease)
        statement_disease_id = str(
            disease.get("ontology_id") or disease.get("identifier") or ""
        )
        relation = _classify_disease(
            query_payload, statement_disease, statement_disease_id
        )
        biomarker = match_biomarker(query.biomarkers, statement)
        current_disease_match = _native_match(
            query.disease_keys(), statement_disease
        )
        duplicate_count = int(lineage_row.get("duplicate_group_size") or 1)
        unit_ids = list(lineage_row.get("active_profile_unit_ids") or [])
        unit_diseases = sorted(
            {
                str(active_units[unit_id].get("disease") or "")
                for unit_id in unit_ids
                if unit_id in active_units
            }
        )
        first_filter = (
            "biomarker"
            if not biomarker.matched
            else "disease"
            if not current_disease_match
            else "none"
        )
        audit_row = {
            "lineage_id": lineage_row["lineage_id"],
            "query_id": query_payload["query_id"],
            "case_id": case_id,
            "v2_rank": lineage_row["v2_rank"],
            "graph_evidence_id": lineage_row["graph_evidence_id"],
            "statement_id": lineage_row["statement_id"],
            "source_ids": lineage_row.get("source_ids") or [],
            "v2_disease_serialized": lineage_row.get("disease"),
            "v2_disease_field_state": "normalized_serialized_value",
            **relation,
            "statement_disease_ontology": disease.get("ontology"),
            "statement_disease_parent_concept": disease.get("parent_concept"),
            "qualified_unit_diseases": unit_diseases,
            "active_profile_unit_ids": unit_ids,
            "query_gene_normalized": normalize_text(
                query_payload["biomarkers"][0]["gene"]
            ),
            "query_alteration_normalized": normalize_text(
                query_payload["biomarkers"][0]["alteration"]
            ),
            "statement_gene": lineage_row.get("gene") or "",
            "statement_alteration": lineage_row.get("alteration") or "",
            "biomarker_match_after_fix": biomarker.matched,
            "biomarker_match_mode": biomarker.mode,
            "biomarker_reason_code": biomarker.reason_code,
            "disease_match_current_v3": current_disease_match,
            "disease_mismatch": not current_disease_match,
            "biomarker_mismatch": not biomarker.matched,
            "multi_intervention": duplicate_count > 1,
            "duplicate_group_size": duplicate_count,
            "first_excluding_filter": first_filter,
            "survives_current_disease_and_biomarker": (
                biomarker.matched and current_disease_match
            ),
            "v2_traversal_origins": lineage_row.get("v2_traversal_origins") or [],
            "v2_disease_constraint_applied": False,
            "different_counting_unit": duplicate_count > 1,
        }
        audit_row.update(_correction_for(audit_row))
        audited.append(audit_row)
        for origin in sorted(lineage_row.get("v2_traversal_origins") or []):
            tool_name = str(origin).rsplit(":", 1)[-1]
            traversal_rows.append(
                {
                    "lineage_id": lineage_row["lineage_id"],
                    "query_id": query_payload["query_id"],
                    "case_id": case_id,
                    "graph_evidence_id": lineage_row["graph_evidence_id"],
                    "traversal_origin": origin,
                    "traversal_tool": tool_name,
                    "semantic_classification": TRAVERSAL_SEMANTICS.get(
                        tool_name, "unknown_traversal_semantics"
                    ),
                    "disease_constraint_applied": False,
                    "would_survive_disease_and_biomarker": (
                        biomarker.matched and current_disease_match
                    ),
                }
            )
    audited.sort(
        key=lambda row: (
            row["query_id"],
            int(row["v2_rank"]),
            row["graph_evidence_id"],
            row["lineage_id"],
        )
    )
    traversal_rows.sort(
        key=lambda row: (
            row["query_id"],
            row["graph_evidence_id"],
            row["traversal_origin"],
            row["lineage_id"],
        )
    )
    inventory: list[dict[str, Any]] = []
    for case_id in TARGET_CASES:
        query = query_by_case[case_id]
        case_rows = [row for row in audited if row["case_id"] == case_id]
        by_disease: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in case_rows:
            by_disease[str(row["statement_disease_raw"])].append(row)
        for disease_label in sorted(by_disease, key=str.casefold):
            values = by_disease[disease_label]
            inventory.append(
                {
                    "query_id": query["query_id"],
                    "case_id": case_id,
                    "query_disease_raw": query["disease"],
                    "query_disease_normalized": _canonical_core(query["disease"]),
                    "query_disease_id": query.get("disease_id"),
                    "query_disease_aliases": query.get("disease_aliases") or [],
                    "statement_disease_raw": disease_label,
                    "statement_disease_normalized": _canonical_core(disease_label),
                    "v2_row_count": len(values),
                    "unique_graph_evidence_count": len(
                        {row["graph_evidence_id"] for row in values}
                    ),
                    "missing_count": sum(
                        not row["statement_disease_normalized"] for row in values
                    ),
                    "ontology_ids": sorted(
                        {
                            row["statement_disease_id"]
                            for row in values
                            if row["statement_disease_id"]
                        }
                    ),
                    "qualified_unit_disease_values": sorted(
                        {
                            value
                            for row in values
                            for value in row["qualified_unit_diseases"]
                        }
                    ),
                    "relation_classifications": sorted(
                        {
                            row["disease_relation_classification"]
                            for row in values
                        }
                    ),
                    "current_v3_match_count": sum(
                        row["disease_match_current_v3"] for row in values
                    ),
                }
            )
    gaps: list[dict[str, Any]] = []
    for (case_id, disease_label), values in sorted(
        {
            (row["case_id"], row["statement_disease_raw"]): [
                candidate
                for candidate in audited
                if candidate["case_id"] == row["case_id"]
                and candidate["statement_disease_raw"]
                == row["statement_disease_raw"]
            ]
            for row in audited
        }.items()
    ):
        first = values[0]
        gaps.append(
            {
                "case_id": case_id,
                "query_id": first["query_id"],
                "query_disease": first["query_disease_raw"],
                "statement_disease": disease_label,
                "classification": first["disease_relation_classification"],
                "v2_row_count": len(values),
                "unique_graph_evidence_count": len(
                    {row["graph_evidence_id"] for row in values}
                ),
                "biomarker_compatible_count": sum(
                    row["biomarker_match_after_fix"] for row in values
                ),
                "current_v3_disease_match_count": sum(
                    row["disease_match_current_v3"] for row in values
                ),
                "safe_resolution_available": all(
                    row["safe_without_semantic_decision"] for row in values
                ),
                "proposed_correction_classes": sorted(
                    {row["correction_class"] for row in values}
                ),
            }
        )
    corrections = [
        {
            "case_id": row["case_id"],
            "query_disease": row["query_disease"],
            "statement_disease": row["statement_disease"],
            "classification": row["classification"],
            "record_count": row["v2_row_count"],
            "correction_class": row["proposed_correction_classes"][0],
            "safe_without_semantic_decision": row["safe_resolution_available"],
            "applied": False,
            "gold_used": False,
        }
        for row in gaps
    ]
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audited:
        if row["disease_mismatch"] and row["multi_intervention"]:
            category = "disease + multi-intervention"
        elif row["disease_mismatch"] and row["biomarker_match_after_fix"]:
            category = "disease-only"
        elif row["disease_match_current_v3"] and row["multi_intervention"]:
            category = "multi-intervention-only"
        elif row["biomarker_mismatch"]:
            category = "traversal-semantics-only"
        else:
            category = "no-interaction"
        category_rows[category].append(row)
    category_names = (
        "disease-only",
        "multi-intervention-only",
        "disease + multi-intervention",
        "traversal-semantics-only",
        "no-interaction",
    )
    interaction = {
        "version": "disease-multi-intervention-interaction/1.0",
        "categories": {
            category: {
                "row_count": len(category_rows[category]),
                "unique_graph_evidence_count": len(
                    {
                        row["graph_evidence_id"]
                        for row in category_rows[category]
                    }
                ),
            }
            for category in category_names
        },
        "flags_are_independently_recorded": True,
        "adapter_modified": False,
        "gold_used": False,
    }
    _write_jsonl(output / "disease_inventory.jsonl", inventory)
    _write_jsonl(output / "disease_pair_classification.jsonl", audited)
    _write_jsonl(
        output / "egfr_disease_audit.jsonl",
        [row for row in audited if row["case_id"] == TARGET_CASES[0]],
    )
    _write_jsonl(
        output / "fgfr2_disease_audit.jsonl",
        [row for row in audited if row["case_id"] == TARGET_CASES[1]],
    )
    _write_jsonl(output / "v2_traversal_semantics.jsonl", traversal_rows)
    _write_jsonl(output / "disease_normalization_gaps.jsonl", gaps)
    _write_json(output / "policy_simulation.json", _policy_simulation(audited))
    _write_jsonl(output / "proposed_disease_corrections.jsonl", corrections)
    _write_json(output / "multi_intervention_interaction.json", interaction)
    data_names = (
        "disease_inventory.jsonl",
        "disease_pair_classification.jsonl",
        "egfr_disease_audit.jsonl",
        "fgfr2_disease_audit.jsonl",
        "v2_traversal_semantics.jsonl",
        "disease_normalization_gaps.jsonl",
        "policy_simulation.json",
        "proposed_disease_corrections.jsonl",
        "multi_intervention_interaction.json",
    )
    manifest = {
        "review_version": REVIEW_VERSION,
        "branch": "eval/v3-disease-normalization-review",
        "source_sha": SOURCE_SHA,
        "corpus_version": "qualification_corpus/2.0",
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "frozen_kg_fingerprint": integrity["frozen_kg_fingerprint"],
        "scoring_config_hash": integrity["scoring_config"]["canonical_hash"],
        "input_integrity": integrity,
        "target_cases": list(TARGET_CASES),
        "post_fix_candidate_counts": EXPECTED_AFTER_COUNTS,
        "gold_bundle": {
            "aggregate_identity": EXPECTED_GOLD_HASH,
            "member_hashes": integrity["gold_bundle"]["file_sha256"],
        },
        "gold_records_loaded": False,
        "gold_used_for_classification": False,
        "pmid_content_read": False,
        "retriever_modified": False,
        "corpus_modified": False,
        "normalizers_modified": False,
        "aliases_or_mappings_added": False,
        "corrections_applied": False,
        "external_services_used": [],
        "artifact_hashes": {name: _sha(output / name) for name in data_names},
    }
    _write_json(output / "review_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path, required=True)
    parser.add_argument("--reverse-input-order", action="store_true")
    args = parser.parse_args()
    generate_review(
        args.root,
        args.output,
        args.gold_bundle,
        reverse_input_order=args.reverse_input_order,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
