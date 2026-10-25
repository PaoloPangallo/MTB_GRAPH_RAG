from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.pipeline.evidence.qualified_retrieval_errors import (
    FingerprintMismatchError,
    InvalidQueryError,
    PrototypeQualifierAsHardFilterError,
)
from backend.pipeline.evidence.qualified_retrieval_policy import (
    assert_may_hard_filter,
    sentinel_treatment,
)
from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_NATIVE_ONLY,
    MODE_QUALIFIED_SOFT,
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.qualified_retrieval_scoring import ScoringConfig


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmarks" / "mtb_evidence" / "v3" / "qualification_corpus_v2"
CONFIG = ROOT / "backend" / "pipeline" / "evidence" / "qualified_retriever_scoring_config.json"
FINGERPRINT = "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"


@pytest.fixture(scope="module")
def retriever() -> QualifiedEvidenceRetriever:
    return QualifiedEvidenceRetriever.from_corpus(CORPUS, scoring_config_path=CONFIG)


def _query(**overrides: object) -> QualifiedRetrievalQuery:
    values = {
        "query_id": "q-alk",
        "disease": "Non-small cell lung cancer",
        "disease_aliases": ("Lung Non-small Cell Carcinoma",),
        "biomarkers": (QueryBiomarker(gene="ALK"),),
        "top_k": 20,
        "mode": MODE_QUALIFIED_SOFT,
        "corpus_fingerprint": FINGERPRINT,
    }
    values.update(overrides)
    return QualifiedRetrievalQuery(**values)


def test_loads_and_validates_frozen_corpus(retriever: QualifiedEvidenceRetriever) -> None:
    report = retriever.validate_corpus()
    assert report["statements"] == 147
    assert report["sources"] == 102
    assert report["active_profile_units"] == 109
    assert report["historical_profile_units"] == 14
    assert report["qualification_links"] == 201
    assert report["qualified_evidence_views"] == 147
    assert report["final_units"] == 0
    assert report["hard_filterable_qualifiers"] == 0
    assert report["qualification_corpus_fingerprint"] == FINGERPRINT
    assert not retriever.active_index_has_historical_units


def test_query_validation_and_fingerprint(retriever: QualifiedEvidenceRetriever) -> None:
    with pytest.raises(InvalidQueryError):
        retriever.retrieve(QualifiedRetrievalQuery(query_id="", disease="", biomarkers=()))
    with pytest.raises(FingerprintMismatchError):
        retriever.retrieve(_query(corpus_fingerprint="wrong"))


def test_scoring_config_hash_is_stable_and_self_describing(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    config = ScoringConfig.load(CONFIG)
    assert config.hash == retriever.get_scoring_config_hash()
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert payload["hash"] == config.hash
    assert payload["clinical_gold_used_for_weights"] is False


def test_policy_distinguishes_sentinels_and_blocks_prototype_filter() -> None:
    assert sentinel_treatment("unknown")[0] == "score"
    assert sentinel_treatment("not_applicable")[0] == "exclude_from_score"
    assert sentinel_treatment("not_separable")[0] == "warn"
    with pytest.raises(PrototypeQualifierAsHardFilterError):
        assert_may_hard_filter(
            "prototype_only", dimension="therapy_line", statement_id="ES-1"
        )


def test_retrieval_is_deterministic_and_score_is_decomposable(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    first = retriever.retrieve(_query())
    second = retriever.retrieve(_query())
    assert first.as_dict() == second.as_dict()
    for result in first.all_results:
        assert result.total_score == pytest.approx(
            sum(float(item["contribution"]) for item in result.score_breakdown)
        )
        assert result.provenance_references
        assert result.source_ids


def test_native_only_has_no_qualified_contribution(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    output = retriever.retrieve(_query(mode=MODE_NATIVE_ONLY))
    assert all(item.qualified_score == 0 for item in output.all_results)


def test_invalid_statement_is_kept_in_audit_for_31358542(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    output = retriever.retrieve(
        _query(
            query_id="q-31358542",
            biomarkers=(QueryBiomarker(gene="ALK"),),
            disease="Non-small cell lung cancer",
            top_k=500,
        )
    )
    by_id = {item.statement_id: item for item in output.audit_only_results}
    assert "ES-V2-evidence-100003" in by_id
    assert "candidate_invalid" in by_id["ES-V2-evidence-100003"].warnings


def test_pending_mappings_never_become_exact(retriever: QualifiedEvidenceRetriever) -> None:
    mappings = retriever.terminology_mappings
    pending = [
        item for item in mappings
        if str(item.get("mapping_status", "")).startswith("requires_")
    ]
    assert pending
    assert all(item["match_grade"] != "exact" for item in pending)
    assert any(item.get("source_term") == "CH5424802" for item in pending)
    assert any("copy number gain" in str(item.get("source_term", "")).casefold() for item in pending)
    assert any("less sensitive" in str(item.get("source_term", "")).casefold() for item in pending)


def test_negative_evidence_remains_negative(retriever: QualifiedEvidenceRetriever) -> None:
    output = retriever.retrieve(
        _query(
            query_id="q-negative",
            assertion_polarities=("does_not_support",),
            top_k=500,
        )
    )
    negatives = [item for item in output.all_results if item.assertion_polarity == "does_not_support"]
    assert negatives
    assert all(item.negative_evidence_information for item in negatives)
    assert all(item.native_matches["assertion_polarity"] for item in negatives)



def test_top_k_is_global_across_primary_buckets(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    output = retriever.retrieve(_query(query_id="q-top", top_k=3))
    assert len(output.ranked_results) + len(output.retained_with_warning) <= 3


def test_pending_mapping_warning_is_in_explanation(
    retriever: QualifiedEvidenceRetriever,
) -> None:
    output = retriever.retrieve(_query(query_id="q-mapping", top_k=500))
    pending = [item for item in output.all_results if item.terminology_mappings]
    assert all(
        "terminology_mapping_pending" in item.explanation_codes for item in pending
    )

def _units_for_pmid(retriever: QualifiedEvidenceRetriever, pmid: str):
    return [
        unit for unit in retriever.active_units.values()
        if unit.get("canonical_source_id") == f"PMID:{pmid}"
    ]


def test_regression_pmid_31358542(retriever: QualifiedEvidenceRetriever) -> None:
    units = _units_for_pmid(retriever, "31358542")
    assert units
    assert not any("preclinical" in str(unit.get("unit_type", "")) for unit in units)
    result = retriever.retrieve(_query(query_id="q-313-regression", top_k=500))
    invalid = {item.statement_id: item for item in result.audit_only_results}
    assert invalid["ES-V2-evidence-100003"].candidate_link_status == "candidate_invalid"
    partial = [item for item in result.all_results if item.statement_id == "ES-V2-evidence-100004"]
    assert partial and "candidate_partial" in partial[0].warnings


def test_regression_pmid_22235099(retriever: QualifiedEvidenceRetriever) -> None:
    links = [link for link in retriever.links if link.get("canonical_source_id") == "PMID:22235099"]
    negatives = [link for link in links if link.get("assertion_polarity") == "does_not_support"]
    assert negatives
    assert all(link.get("experiment_role") == "negative_experiment" for link in negatives)
    units = _units_for_pmid(retriever, "22235099")
    assert any("clinical" in str(unit.get("unit_type", "")) for unit in units)
    assert any("preclinical" in str(unit.get("unit_type", "")) for unit in units)
    assert all(not unit.get("is_hard_filterable") for unit in units)


def test_regression_pmid_23344087(retriever: QualifiedEvidenceRetriever) -> None:
    views = [
        view for statement_id, view in retriever.views.items()
        if any("23344087" in source for source in [str(ref.get("source_id", "")) for ref in (view["base_statement"].get("source_references") or [])])
    ]
    assert any(view.get("not_separable_dimensions") for view in views)
    units = _units_for_pmid(retriever, "23344087")
    assert any(unit.get("source_basis") == "abstract_only" for unit in units)
    pending = [item for item in retriever.terminology_mappings if item.get("canonical_source_id") == "PMID:23344087"]
    assert any("copy number gain" in str(item.get("source_term", "")).casefold() for item in pending)
    assert any(item.get("resistance_qualifier") == "relative_reduced_sensitivity" for item in pending)


def test_regression_pmid_22277784(retriever: QualifiedEvidenceRetriever) -> None:
    units = _units_for_pmid(retriever, "22277784")
    assert any("clinical" in str(unit.get("unit_type", "")) for unit in units)
    assert any("preclinical" in str(unit.get("unit_type", "")) for unit in units)
    mapping = next(item for item in retriever.terminology_mappings if item.get("source_term") == "CH5424802")
    assert mapping["match_grade"] == "pending_terminology_mapping"


def test_query_input_order_does_not_change_ranking(retriever: QualifiedEvidenceRetriever) -> None:
    forward = _query(
        query_id="q-order-a",
        biomarkers=(QueryBiomarker(gene="ALK"), QueryBiomarker(alteration="G1202R")),
    )
    reverse = _query(
        query_id="q-order-b",
        biomarkers=tuple(reversed(forward.biomarkers)),
    )
    left = retriever.retrieve(forward)
    right = retriever.retrieve(reverse)
    assert [item.statement_id for item in left.all_results] == [item.statement_id for item in right.all_results]