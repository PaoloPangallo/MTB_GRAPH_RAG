from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

import pytest

from benchmarks.mtb_evidence.evaluation.scripts import (
    disease_normalization_review as disease_review,
)

EXPLICIT_EVIDENCE_IDS = disease_review.EXPLICIT_EVIDENCE_IDS
generate_review = disease_review.generate_review
POST_ALIAS_FIX_RETRIEVER_HASH = (
    "b78ce4ea79e1ac090d29d4dc1c9cbc865bedc91dbdf3d77b469bdfde3f2cfd4c"
)


ROOT = Path(__file__).resolve().parents[3]
# Questo modulo sta in `backend/tests_external/gold/`: il bundle e' un
# presupposto, non un'eventualita'. `require` invece di `resolve` perche'
# l'assenza qui e' un errore che deve dire dove ha cercato, non un `None` che
# si propaga fino a un TypeError trenta righe piu' sotto.
GOLD = EXTERNAL.require(EXTERNAL.GOLD_BUNDLE)




def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _aggregate(path: Path) -> str:
    files = sorted(
        (item for item in path.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(ROOT).as_posix().casefold(),
    )
    payload = "\n".join(
        f"{item.relative_to(ROOT).as_posix()}:{hashlib.sha256(item.read_bytes()).hexdigest()}"
        for item in files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.fixture()
def generated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        disease_review,
        "EXPECTED_RETRIEVER_HASH",
        POST_ALIAS_FIX_RETRIEVER_HASH,
    )
    generate_review(ROOT, tmp_path, GOLD)
    return tmp_path


def test_every_egfr_and_fgfr2_record_is_classified(generated: Path) -> None:
    egfr = _jsonl(generated / "egfr_disease_audit.jsonl")
    fgfr2 = _jsonl(generated / "fgfr2_disease_audit.jsonl")
    assert len(egfr) == 81
    assert len(fgfr2) == 28
    assert len({row["graph_evidence_id"] for row in egfr}) == 73
    assert len({row["graph_evidence_id"] for row in fgfr2}) == 25
    assert all(row["disease_relation_classification"] for row in egfr + fgfr2)
    assert all(row["first_excluding_filter"] for row in egfr + fgfr2)
    assert all(row["biomarker_match_after_fix"] in {True, False} for row in egfr + fgfr2)
    assert all(row["disease_match_current_v3"] in {True, False} for row in egfr + fgfr2)


def test_five_requested_evidence_ids_are_explicit(generated: Path) -> None:
    rows = _jsonl(generated / "disease_pair_classification.jsonl")
    explicit = {
        row["graph_evidence_id"]: row
        for row in rows
        if row["graph_evidence_id"] in EXPLICIT_EVIDENCE_IDS
    }
    assert set(explicit) == set(EXPLICIT_EVIDENCE_IDS)
    assert explicit["evidence:11219"]["biomarker_match_after_fix"] is True
    assert explicit["evidence:11219"]["disease_relation_classification"] == (
        "verified_alias_match"
    )
    assert explicit["evidence:11598"]["biomarker_match_after_fix"] is False
    assert explicit["evidence:11599"]["biomarker_match_after_fix"] is False
    assert explicit["evidence:1867"]["biomarker_match_after_fix"] is False
    assert explicit["evidence:8173"]["disease_relation_classification"] == (
        "same_organ_different_subtype"
    )


def test_no_hierarchy_or_alias_is_invented(generated: Path) -> None:
    rows = _jsonl(generated / "disease_pair_classification.jsonl")
    hierarchy = {
        "explicit_parent_child_relation",
        "explicit_ancestor_descendant_relation",
        "broader_disease_label",
        "narrower_disease_label",
        "same_organ_different_subtype",
    }
    assert all(
        row["local_relation_evidence"]
        for row in rows
        if row["disease_relation_classification"] in hierarchy
    )
    assert all(
        row["alias_source"] in {"query_contract", "existing_local_normalizer"}
        for row in rows
        if row["disease_relation_classification"] == "verified_alias_match"
    )
    unresolved = [
        row
        for row in rows
        if row["disease_relation_classification"]
        in {"ontology_relation_not_available", "unresolved_other"}
    ]
    assert all(
        row["disease_relation"]
        == "unresolved_without_external_or_document_review"
        for row in unresolved
    )


def test_query_contract_alias_is_not_automatically_semantic_equivalence(
    generated: Path,
) -> None:
    rows = _jsonl(generated / "disease_pair_classification.jsonl")
    lung_adenocarcinoma = [
        row
        for row in rows
        if row["case_id"] == "PILOT-C1-EGFR-L858R-CONTEXT"
        and row["statement_disease_raw"] == "Lung Adenocarcinoma"
    ]
    assert len(lung_adenocarcinoma) == 17
    assert {row["disease_relation_classification"] for row in lung_adenocarcinoma} == {
        "narrower_disease_label"
    }
    assert {row["query_alias_contract_match"] for row in lung_adenocarcinoma} == {
        "Lung Adenocarcinoma"
    }
    assert {row["query_alias_to_primary_relation"] for row in lung_adenocarcinoma} == {
        "different_specificity"
    }
    assert all(
        row["safe_without_semantic_decision"] is False
        for row in lung_adenocarcinoma
        if row["biomarker_match_after_fix"] is True
    )


def test_v2_traversals_are_classified_without_disease_constraint(
    generated: Path,
) -> None:
    rows = _jsonl(generated / "v2_traversal_semantics.jsonl")
    assert rows
    allowed = {
        "disease_and_biomarker_constrained",
        "biomarker_only",
        "gene_neighborhood",
        "intervention_neighborhood",
        "source_neighborhood",
        "trial_neighborhood",
        "broad_evidence_expansion",
        "unknown_traversal_semantics",
    }
    assert {row["semantic_classification"] for row in rows} <= allowed
    assert all(row["disease_constraint_applied"] is False for row in rows)
    assert {row["semantic_classification"] for row in rows} >= {
        "biomarker_only",
        "gene_neighborhood",
        "intervention_neighborhood",
        "source_neighborhood",
    }


def test_disease_and_multi_intervention_dimensions_stay_separate(
    generated: Path,
) -> None:
    rows = _jsonl(generated / "egfr_disease_audit.jsonl") + _jsonl(
        generated / "fgfr2_disease_audit.jsonl"
    )
    assert all("disease_mismatch" in row for row in rows)
    assert all("biomarker_mismatch" in row for row in rows)
    assert all("multi_intervention" in row for row in rows)
    summary = json.loads(
        (generated / "multi_intervention_interaction.json").read_text("utf-8")
    )
    assert set(summary["categories"]) == {
        "disease-only",
        "multi-intervention-only",
        "disease + multi-intervention",
        "traversal-semantics-only",
        "no-interaction",
    }


def test_policy_contract_is_frozen_and_descriptive(generated: Path) -> None:
    policies = json.loads((generated / "policy_simulation.json").read_text("utf-8"))
    assert policies["policy_contract_frozen_before_results"] is True
    assert [row["policy_id"] for row in policies["policies"]] == ["A", "B", "C", "D"]
    by_policy = {row["policy_id"]: row for row in policies["policies"]}
    a_queries = {row["case_id"]: row for row in by_policy["A"]["queries"]}
    b_queries = {row["case_id"]: row for row in by_policy["B"]["queries"]}
    assert a_queries["PILOT-C1-EGFR-L858R-CONTEXT"]["row_count"] == 38
    assert a_queries["PILOT-C1-EGFR-L858R-CONTEXT"]["cross_disease_row_count"] == 0
    assert b_queries["PILOT-C1-EGFR-L858R-CONTEXT"]["row_count"] == 48
    assert a_queries["PILOT-K1-FGFR2-iCCA"]["row_count"] == 1
    assert b_queries["PILOT-K1-FGFR2-iCCA"]["row_count"] == 11
    assert policies["clinical_metrics_computed"] is False
    assert policies["gold_used"] is False
    assert all("row_count" in query for row in policies["policies"] for query in row["queries"])
    assert all(
        "unique_graph_evidence_count" in query
        for row in policies["policies"]
        for query in row["queries"]
    )


def test_review_is_byte_deterministic_and_order_invariant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        disease_review,
        "EXPECTED_RETRIEVER_HASH",
        POST_ALIAS_FIX_RETRIEVER_HASH,
    )
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_review(ROOT, first, GOLD)
    generate_review(ROOT, second, GOLD, reverse_input_order=True)
    names = {
        "disease_inventory.jsonl",
        "disease_pair_classification.jsonl",
        "egfr_disease_audit.jsonl",
        "fgfr2_disease_audit.jsonl",
        "v2_traversal_semantics.jsonl",
        "disease_normalization_gaps.jsonl",
        "policy_simulation.json",
        "proposed_disease_corrections.jsonl",
        "multi_intervention_interaction.json",
        "review_manifest.json",
    }
    assert {name: (first / name).read_bytes() for name in names} == {
        name: (second / name).read_bytes() for name in names
    }


def test_gold_is_authenticated_but_never_loaded_for_classification(
    generated: Path,
) -> None:
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    assert manifest["gold_bundle"]["aggregate_identity"] == (
        "05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133"
    )
    assert manifest["gold_records_loaded"] is False
    assert manifest["gold_used_for_classification"] is False
    assert manifest["pmid_content_read"] is False
    assert manifest["external_services_used"] == []


def test_frozen_inputs_remain_byte_identical() -> None:
    v3 = ROOT / "benchmarks" / "mtb_evidence" / "v3"
    assert _aggregate(v3 / "qualification_corpus_v2") == (
        "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827"
    )
    assert _aggregate(v3 / "candidate_coverage_audit") == (
        "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
    )
    assert _aggregate(v3 / "conjunctive_biomarker_fix") == (
        "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41d88638d"
    )
    retriever = sorted(
        (ROOT / "backend" / "pipeline" / "evidence").glob("qualified_retriev*")
    )
    payload = "\n".join(
        f"{item.relative_to(ROOT).as_posix()}:{hashlib.sha256(item.read_bytes()).hexdigest()}"
        for item in retriever
    )
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == (
        POST_ALIAS_FIX_RETRIEVER_HASH
    )
    assert _aggregate(v3 / "disease_normalization_review") == (
        "1084763a50e63cfe4c19b72defca5c73788a826f5227a0fd4378c7bc1020b71c"
    )
