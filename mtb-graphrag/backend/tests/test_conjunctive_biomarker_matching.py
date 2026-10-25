from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.pipeline.evidence.qualified_retrieval_query import (
    BIOMARKER_MATCH_ALTERATION_SPECIFIC,
    BIOMARKER_MATCH_GENE_LEVEL,
    MODE_NATIVE_ONLY,
    QualifiedRetrievalQuery,
    QueryBiomarker,
    build_query,
)
from backend.pipeline.evidence.qualified_retrieval_result import (
    X_ALTERATION_MISMATCH_WITH_MATCHING_GENE,
)
from backend.pipeline.evidence.qualified_retriever import (
    QualifiedEvidenceRetriever,
    match_biomarker,
)


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmarks" / "mtb_evidence" / "v3" / "qualification_corpus_v2"
CONFIG = (
    ROOT
    / "backend"
    / "pipeline"
    / "evidence"
    / "qualified_retriever_scoring_config.json"
)
QUERIES = (
    ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "qualified_retriever_prototype"
    / "queries.jsonl"
)
FROZEN_NATIVE_RESULTS = (
    ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "v2_v3a_exploratory_pilot"
    / "native_only_results.jsonl"
)


def _statement(
    *,
    gene: str = "",
    label: str = "",
    components: tuple[str, ...] = (),
    alteration_type: str = "unknown",
) -> dict[str, object]:
    return {
        "biomarker": {
            "gene": gene or None,
            "label": label,
            "component_biomarkers": list(components),
        },
        "alteration_type": alteration_type,
    }


def _query_marker(gene: str, alteration: str = "", normalized: str = ""):
    return (QueryBiomarker(gene=gene, alteration=alteration, normalized=normalized),)


@pytest.fixture(scope="module")
def retriever() -> QualifiedEvidenceRetriever:
    return QualifiedEvidenceRetriever.from_corpus(CORPUS, scoring_config_path=CONFIG)


def _pilot_queries() -> list[QualifiedRetrievalQuery]:
    rows = [
        json.loads(line)
        for line in QUERIES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        build_query({**row, "mode": MODE_NATIVE_ONLY, "top_k": 500})
        for row in rows
    ]


def test_gene_only_query_uses_explicit_gene_level_mode() -> None:
    result = match_biomarker(
        _query_marker("ALK"),
        _statement(label="EML4::ALK Fusion AND ALK G1269A", components=("G1269A",)),
    )
    assert result.mode == BIOMARKER_MATCH_GENE_LEVEL
    assert result.matched
    assert result.gene_match
    assert result.alteration_match is None


def test_gene_and_alteration_are_conjunctive() -> None:
    matching = match_biomarker(
        _query_marker("ALK", "G1202R (single mutation)"),
        _statement(label="EML4::ALK Fusion AND ALK G1202R", components=("G1202R",)),
    )
    mismatching = match_biomarker(
        _query_marker("ALK", "G1202R (single mutation)"),
        _statement(label="EML4::ALK Fusion AND ALK G1269A", components=("G1269A",)),
    )
    assert matching.mode == BIOMARKER_MATCH_ALTERATION_SPECIFIC
    assert matching.matched
    assert matching.gene_match and matching.alteration_match
    assert not mismatching.matched
    assert mismatching.gene_match and not mismatching.alteration_match
    assert mismatching.reason_code == X_ALTERATION_MISMATCH_WITH_MATCHING_GENE


def test_same_alteration_cannot_compensate_for_different_gene() -> None:
    result = match_biomarker(
        _query_marker("ALK", "G1202R"),
        _statement(gene="EGFR", label="EGFR G1202R", components=("G1202R",)),
    )
    assert not result.matched
    assert not result.gene_match
    assert result.alteration_match


def test_missing_statement_alteration_is_not_an_exact_match() -> None:
    result = match_biomarker(
        _query_marker("ALK", "G1202R"),
        _statement(gene="ALK", label="ALK"),
    )
    assert not result.matched
    assert result.statement_alterations == ()
    assert not result.alteration_match


def test_normalized_exact_alteration_and_explicit_query_disjunction() -> None:
    normalized = match_biomarker(
        _query_marker("ALK", normalized="ALK G1202R"),
        _statement(label="ALK G1202R", components=("G1202R",)),
    )
    fusion = match_biomarker(
        _query_marker("FGFR2", "Fusion/Rearrangement"),
        _statement(gene="FGFR2", label="FGFR2::BICC1 Fusion", alteration_type="fusion"),
    )
    assert normalized.matched and normalized.alteration_match
    assert fusion.matched and fusion.alteration_match


def test_pending_mapping_does_not_create_exact_alteration_match() -> None:
    result = match_biomarker(
        _query_marker("EGFR", "amplification"),
        _statement(
            gene="EGFR",
            label="EGFR copy-number gain",
            components=("copy-number gain",),
            alteration_type="copy_number_gain",
        ),
    )
    assert not result.matched
    assert result.reason_code == X_ALTERATION_MISMATCH_WITH_MATCHING_GENE


def test_query_marker_order_does_not_change_conjunctive_result() -> None:
    forward = (
        QueryBiomarker(gene="ALK"),
        QueryBiomarker(alteration="G1202R"),
    )
    reverse = tuple(reversed(forward))
    statement = _statement(label="ALK G1202R", components=("G1202R",))
    assert match_biomarker(forward, statement) == match_biomarker(reverse, statement)


def test_frozen_alk_overreach_is_removed_without_fgfr2_or_rmi2_change(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    outputs = {query.case_id: retriever.retrieve(query) for query in _pilot_queries()}
    assert outputs["PILOT-A2-ALK-G1202R"].candidate_count == 9
    # The downstream verified-alias fix safely recovers the local NSCLC aliases.
    assert outputs["PILOT-C1-EGFR-L858R-CONTEXT"].candidate_count == 32
    assert outputs["PILOT-K1-FGFR2-iCCA"].candidate_count == 1
    assert outputs["PILOT-N1-RMI2-SNAPSHOT"].candidate_count == 0

    alk = outputs["PILOT-A2-ALK-G1202R"]
    frozen_alk = next(
        json.loads(line)
        for line in FROZEN_NATIVE_RESULTS.read_text(encoding="utf-8").splitlines()
        if '"query_id":"PILOT-A2-ALK-G1202R:qualified-retrieval"' in line
    )
    frozen_statement_ids = {
        item["statement_id"]
        for item in frozen_alk["complete_candidate_results"]
    }
    removed = [
        item
        for item in alk.rejected_by_native_constraints
        if item.reason_code == X_ALTERATION_MISMATCH_WITH_MATCHING_GENE
        and "ALK" in item.query_gene
        and item.statement_id in frozen_statement_ids
    ]
    assert len(removed) == 23
    assert all(item.query_alteration for item in removed)
    assert all(item.statement_gene for item in removed)
    assert all(item.statement_alteration for item in removed)


def test_candidate_set_is_deterministic_under_repository_order(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    query = next(
        query for query in _pilot_queries() if query.case_id == "PILOT-A2-ALK-G1202R"
    )
    first = retriever.retrieve(query)
    second = retriever.retrieve(query)
    assert [item.statement_id for item in first.all_results] == [
        item.statement_id for item in second.all_results
    ]
