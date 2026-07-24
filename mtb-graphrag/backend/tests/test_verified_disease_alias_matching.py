from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.pipeline.evidence.qualified_disease_matching import (
    DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED,
    DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED,
    DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED,
    DISEASE_INCOMPATIBLE,
    DISEASE_NORMALIZED_EXACT_MATCH,
    DISEASE_RELATION_UNRESOLVED,
    DISEASE_VERIFIED_ALIAS_MATCH,
    MATCH_EXACT_STRING,
    MATCH_EXPLICIT_CHILD,
    MATCH_EXPLICIT_PARENT,
    MATCH_EXPLICIT_SIBLING,
    MATCH_INCOMPATIBLE,
    MATCH_NORMALIZED_EXACT,
    MATCH_PAN_CANCER_OR_UNSPECIFIED,
    MATCH_UNRESOLVED,
    MATCH_VERIFIED_ALIAS,
    match_disease,
)
from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_NATIVE_ONLY,
    build_query,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
SCORING = (
    ROOT / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
)
QUERIES = (
    ROOT
    / "benchmarks/mtb_evidence/v3/qualified_retriever_prototype/queries.jsonl"
)
DISEASE_REVIEW = (
    ROOT
    / "benchmarks/mtb_evidence/v3/disease_normalization_review"
    / "disease_pair_classification.jsonl"
)
QUERY_LABELS = {
    "PILOT-A2-ALK-G1202R:qualified-retrieval": "ALK-G1202R",
    "PILOT-C1-EGFR-L858R-CONTEXT:qualified-retrieval": "EGFR-L858R",
    "PILOT-K1-FGFR2-iCCA:qualified-retrieval": "FGFR2-iCCA",
    "PILOT-N1-RMI2-SNAPSHOT:qualified-retrieval": "RMI2",
}


def _query_payloads() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in QUERIES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def retriever() -> QualifiedEvidenceRetriever:
    return QualifiedEvidenceRetriever.from_corpus(
        CORPUS,
        scoring_config_path=SCORING,
    )


@pytest.fixture(scope="module")
def retrieved(
    retriever: QualifiedEvidenceRetriever,
) -> dict[str, object]:
    output: dict[str, object] = {}
    for payload in _query_payloads():
        item = dict(payload)
        item["retrieval_mode"] = MODE_NATIVE_ONLY
        item["top_k"] = 500
        query = build_query(item)
        output[QUERY_LABELS[query.query_id]] = retriever.retrieve(query)
    return output


def test_exact_string_match_is_hard_allowed() -> None:
    match = match_disease("NSCLC", "NSCLC")

    assert match.match_type == MATCH_EXACT_STRING
    assert match.matched is True
    assert match.hard_match_allowed is True


def test_qualified_nsclc_is_normalized_exact() -> None:
    match = match_disease("Advanced/metastatic NSCLC", "NSCLC")

    assert match.match_type == MATCH_NORMALIZED_EXACT
    assert match.hard_match_allowed is True
    assert match.canonical_disease_key == "nsclc"
    assert match.explanation_code == DISEASE_NORMALIZED_EXACT_MATCH


def test_local_nsclc_synonym_is_verified_alias() -> None:
    match = match_disease(
        "Advanced/metastatic NSCLC",
        "Lung Non-small Cell Carcinoma",
    )

    assert match.match_type == MATCH_VERIFIED_ALIAS
    assert match.matched is True
    assert match.hard_match_allowed is True
    assert match.alias_source
    assert match.alias_version
    assert match.canonical_disease_key == "nsclc"
    assert match.explanation_code == DISEASE_VERIFIED_ALIAS_MATCH


def test_lung_adenocarcinoma_is_explicit_child_not_alias() -> None:
    match = match_disease(
        "Advanced/metastatic NSCLC",
        "Lung Adenocarcinoma",
    )

    assert match.match_type == MATCH_EXPLICIT_CHILD
    assert match.matched is False
    assert match.hard_match_allowed is False
    assert match.warning_code == DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED


def test_cholangiocarcinoma_is_explicit_parent_not_alias() -> None:
    match = match_disease(
        "Intrahepatic Cholangiocarcinoma",
        "Cholangiocarcinoma",
    )

    assert match.match_type == MATCH_EXPLICIT_PARENT
    assert match.matched is False
    assert match.hard_match_allowed is False
    assert match.warning_code == DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED


def test_cholangiolocellular_is_explicit_sibling_not_alias() -> None:
    match = match_disease(
        "Intrahepatic Cholangiocarcinoma",
        "Cholangiolocellular Carcinoma",
    )

    assert match.match_type == MATCH_EXPLICIT_SIBLING
    assert match.matched is False
    assert match.hard_match_allowed is False
    assert match.warning_code == DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED


def test_pan_cancer_is_not_a_hard_match() -> None:
    match = match_disease("NSCLC", "Pan-cancer")

    assert match.match_type == MATCH_PAN_CANCER_OR_UNSPECIFIED
    assert match.hard_match_allowed is False


def test_unresolved_relation_is_not_a_hard_match() -> None:
    match = match_disease("NSCLC", "Unclassified Thoracic Neoplasm")

    assert match.match_type == MATCH_UNRESOLVED
    assert match.hard_match_allowed is False
    assert match.warning_code == DISEASE_RELATION_UNRESOLVED


def test_conflicting_explicit_ids_are_incompatible() -> None:
    match = match_disease(
        "NSCLC",
        "NSCLC",
        query_canonical_id="DOID:3908",
        statement_canonical_id="DOID:1234",
    )

    assert match.match_type == MATCH_INCOMPATIBLE
    assert match.hard_match_allowed is False
    assert match.warning_code == DISEASE_INCOMPATIBLE


def test_unverified_lung_nsclc_spelling_is_not_promoted() -> None:
    match = match_disease("Advanced/metastatic NSCLC", "Lung NSCLC")

    assert match.match_type == MATCH_UNRESOLVED
    assert match.hard_match_allowed is False


def test_candidate_counts_follow_strict_verified_alias_policy(
    retrieved: dict[str, object],
) -> None:
    counts = {
        query_id: len(result.all_results)
        for query_id, result in retrieved.items()
    }

    assert counts == {
        "ALK-G1202R": 9,
        "EGFR-L858R": 32,
        "FGFR2-iCCA": 1,
        "RMI2": 0,
    }


def test_egfr_candidate_set_equals_review_alias_safe_subset(
    retrieved: dict[str, object],
) -> None:
    expected = {
        row["graph_evidence_id"]
        for row in (
            json.loads(line)
            for line in DISEASE_REVIEW.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row["query_id"]
        == "PILOT-C1-EGFR-L858R-CONTEXT:qualified-retrieval"
        and row["biomarker_match_after_fix"]
        and row["disease_relation_classification"]
        in {"exact_string_match", "normalized_exact_match", "verified_alias_match"}
    }
    actual = {
        graph_id
        for result in retrieved["EGFR-L858R"].all_results
        for graph_id in result.graph_evidence_ids
    }

    assert len(expected) == 32
    assert actual == expected


def test_required_egfr_evidence_keeps_biomarker_as_first_constraint(
    retrieved: dict[str, object],
) -> None:
    result = retrieved["EGFR-L858R"]
    included = {
        graph_id
        for item in result.all_results
        for graph_id in item.graph_evidence_ids
    }
    exclusions = {
        item.statement_id: item for item in result.rejected_by_native_constraints
    }

    assert "evidence:11219" in included
    for graph_id in ("evidence:11598", "evidence:11599", "evidence:1867"):
        exclusion = exclusions[f"ES-V2-{graph_id.replace(':' , '-')}"]
        assert exclusion.field_name == "biomarker"
        assert (
            "BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS"
            in exclusion.explanation_codes
        )
        assert exclusion.disease_match["match_type"] == MATCH_VERIFIED_ALIAS


def test_lung_adenocarcinoma_never_enters_egfr_primary_candidates(
    retrieved: dict[str, object],
) -> None:
    result = retrieved["EGFR-L858R"]

    assert all(
        item.disease_match["match_type"]
        in {MATCH_EXACT_STRING, MATCH_NORMALIZED_EXACT, MATCH_VERIFIED_ALIAS}
        for item in result.all_results
    )
    assert all(
        item.disease_match["statement_raw"] != "Lung Adenocarcinoma"
        for item in result.all_results
    )


def test_fgfr2_sibling_and_parent_remain_native_exclusions(
    retrieved: dict[str, object],
) -> None:
    result = retrieved["FGFR2-iCCA"]
    exclusions = {
        item.statement_id: item for item in result.rejected_by_native_constraints
    }

    sibling = exclusions["ES-V2-evidence-8173"]
    assert sibling.field_name == "disease"
    assert sibling.disease_match["match_type"] == MATCH_EXPLICIT_SIBLING
    assert sibling.disease_match["hard_match_allowed"] is False
    assert all(
        item.disease_match["statement_raw"] != "Cholangiocarcinoma"
        for item in result.all_results
    )


def test_retrieval_is_order_invariant_and_deterministic(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    payloads = _query_payloads()

    def run(items: list[dict[str, object]]) -> dict[str, str]:
        output: dict[str, str] = {}
        for payload in items:
            item = dict(payload)
            item["retrieval_mode"] = MODE_NATIVE_ONLY
            item["top_k"] = 500
            query = build_query(item)
            result = retriever.retrieve(query)
            serialized = json.dumps(
                result.as_dict(),
                sort_keys=True,
                separators=(",", ":"),
            )
            output[query.query_id] = serialized
        return output

    assert run(payloads) == run(list(reversed(payloads)))
