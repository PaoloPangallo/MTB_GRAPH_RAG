from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

import pytest

from benchmarks.mtb_evidence.evaluation.scripts import (
    multi_intervention_adapter_review as review,
)


ROOT = Path(__file__).resolve().parents[3]
# Questo modulo sta in `backend/tests_external/gold/`: il bundle e' un
# presupposto, non un'eventualita'. `require` invece di `resolve` perche'
# l'assenza qui e' un errore che deve dire dove ha cercato, non un `None` che
# si propaga fino a un TypeError trenta righe piu' sotto.
GOLD = EXTERNAL.require(EXTERNAL.GOLD_BUNDLE)


COMMITTED = (
    ROOT / "benchmarks/mtb_evidence/v3/multi_intervention_adapter_review"
)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("multi_intervention_review")
    review.generate_review(ROOT, output, GOLD)
    return output


def test_every_multi_row_group_is_classified(generated: Path) -> None:
    rows = _jsonl(generated / "multi_row_graph_evidence_inventory.jsonl")
    assert len(rows) == 36
    assert len({row["graph_evidence_id"] for row in rows}) == 36
    assert all(row["primary_classification"] for row in rows)
    assert {
        row["primary_classification"] for row in rows
    } == {
        "duplicated_serialization",
        "unresolved_without_document_review",
    }


def test_every_adapter_input_intervention_has_lineage(generated: Path) -> None:
    rows = _jsonl(generated / "intervention_lineage.jsonl")
    assert len(rows) == 199
    assert len({row["lineage_id"] for row in rows}) == 199
    assert all(row["graph_evidence_id"] for row in rows)
    assert all(row["statement_id"] for row in rows)
    assert all(row["qualification_corpus_present"] is True for row in rows)
    assert all(row["retrieval_index_present"] is True for row in rows)
    assert all(row["gold_used"] is False for row in rows)


def test_no_lost_intervention_lacks_a_first_loss_reason(generated: Path) -> None:
    rows = _jsonl(generated / "lost_interventions.jsonl")
    assert len(rows) == 15
    assert all(row["reason"] for row in rows)
    assert {
        row["first_loss_stage"] for row in rows
    } == {
        "v2_adapter.merge_duplicate_records.scalar_single_value_selection"
    }
    assert {
        row["lineage_status"] for row in rows
    } == {"dropped_by_single_value_selection"}


def test_alias_pending_mapping_and_distinct_drugs_are_not_conflated(
    generated: Path,
) -> None:
    groups = _jsonl(generated / "multi_intervention_groups.jsonl")
    assert len(groups) == 13
    assert all(
        len(row["v2_interventions_normalized"]) > 1 for row in groups
    )
    normalization = _jsonl(
        generated / "intervention_normalization_audit.jsonl"
    )
    pending = [
        row for row in normalization if row["normalization_relation"] == "pending_mapping"
    ]
    assert pending
    assert all(row["merge_allowed"] is False for row in pending)
    ch5424802 = [
        row
        for row in pending
        if str(row["v2_intervention"]).casefold() == "ch5424802"
    ]
    assert len(ch5424802) == 1
    assert ch5424802[0]["statement_intervention"] == "alectinib hydrochloride"
    assert ch5424802[0]["mapping_status"] == (
        "requires_source_or_terminology_verification"
    )


def test_regimen_and_aggregate_ambiguity_is_not_atomized(
    generated: Path,
) -> None:
    groups = _jsonl(generated / "multi_intervention_groups.jsonl")
    assert len(groups) == 13
    for row in groups:
        assert row["primary_classification"] == "unresolved_without_document_review"
        assert row["structurally_atomizable"] is False
        assert row["source_review_required"] is True
        assert row["aggregate_to_specific_attribution_forbidden"] is True


def test_named_multikinase_agent_is_not_turned_into_a_drug_class(
    generated: Path,
) -> None:
    group = next(
        row
        for row in _jsonl(generated / "multi_intervention_groups.jsonl")
        if row["graph_evidence_id"] == "evidence:3811"
    )
    assert "multikinase inhibitor aee788" in group["v2_interventions_normalized"]
    assert group["primary_classification"] == "unresolved_without_document_review"
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    assert manifest["metrics"]["drug_class_groups"] == 0


def test_egfr_and_fgfr2_expected_groups_are_fully_audited(
    generated: Path,
) -> None:
    egfr = _jsonl(generated / "egfr_multi_intervention_audit.jsonl")
    fgfr2 = _jsonl(generated / "fgfr2_multi_intervention_audit.jsonl")
    assert len(egfr) == 15
    assert len({row["graph_evidence_id"] for row in egfr}) == 7
    assert len(fgfr2) == 6
    assert len({row["graph_evidence_id"] for row in fgfr2}) == 3
    assert all(row["disease_alias_decision_applied"] is False for row in egfr + fgfr2)
    assert all(row["biomarker_matching_decision_applied"] is False for row in egfr + fgfr2)
    assert all(row["ranking_decision_applied"] is False for row in egfr + fgfr2)


def test_representation_simulation_is_non_operational(generated: Path) -> None:
    data = json.loads(
        (generated / "representation_option_simulation.json").read_text("utf-8")
    )
    assert data["current_single_intervention"]["statement_total"] == 147
    assert data["option_A_list_valued"]["statement_total"] == 147
    assert data["option_B_atomic_per_intervention"]["safe_statement_total"] == 147
    assert data["option_B_atomic_per_intervention"]["additional_statement_count"] == 0
    assert (
        data["option_B_atomic_per_intervention"][
            "maximal_unreviewed_statement_total_forbidden"
        ]
        == 162
    )
    assert data["option_C_parent_plus_atomic_children"]["safe_statement_total"] == 147
    assert data["recommended_architecture"] == "insufficient_evidence_for_decision"
    assert data["preferred_architecture_if_attribution_is_confirmed"] == (
        "option_C_parent_plus_atomic_children"
    )
    assert data["simulation_contract"]["aggregate_results_atomized"] is False


def test_id_strategy_is_evaluated_but_not_applied(generated: Path) -> None:
    data = json.loads(
        (generated / "representation_option_simulation.json").read_text("utf-8")
    )
    strategy = data["id_strategy"]
    assert strategy["recommended"] == "claim_hash"
    assert strategy["order_independent"] is True
    assert strategy["preserves_graph_evidence_id"] is True
    assert strategy["implemented"] is False
    statements = _jsonl(
        ROOT
        / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
        / "evidence_statements.jsonl"
    )
    assert len(statements) == 147


def test_gold_is_loaded_only_after_classification_and_never_decides(
    generated: Path,
) -> None:
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    gold = json.loads((generated / "affected_gold_records.json").read_text("utf-8"))
    assert manifest["classification_frozen_before_gold_access"] is True
    assert manifest["gold_loaded_after_classification"] is True
    assert manifest["gold_used_for_decision"] is False
    assert gold["classification_frozen_before_gold_content_load"] is True
    assert gold["classification_artifact_hash"] == manifest[
        "classification_artifact_hash"
    ]
    assert gold["quality_metrics_recomputed"] is False
    assert gold["pilot_case_records_in_scope"] == 3
    assert gold["gold_records_with_exact_lost_intervention_match"] == 0


def test_adapter_corpus_retriever_scoring_and_prior_audits_are_frozen(
    generated: Path,
) -> None:
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    integrity = manifest["input_integrity"]
    assert integrity["v2_adapter"]["file_sha256"] == review.EXPECTED_ADAPTER_HASH
    assert integrity["evidence_statement_repository"]["file_sha256"] == (
        review.EXPECTED_REPOSITORY_HASH
    )
    assert integrity["qualification_corpus"]["aggregate_sha256"] == (
        review.EXPECTED_CORPUS_DIRECTORY_HASH
    )
    assert integrity["raw_v2_adapter_inputs"]["aggregate_sha256"] == (
        review.EXPECTED_RAW_V2_INPUT_HASH
    )
    assert integrity["retriever"]["aggregate_sha256"] == review.EXPECTED_RETRIEVER_HASH
    assert integrity["scoring_config"]["canonical_hash"] == review.EXPECTED_SCORING_HASH
    assert integrity["gold_bundle"]["aggregate_sha256"] == review.EXPECTED_GOLD_HASH
    assert integrity["second_review_packets"]["aggregate_sha256"] == (
        review.EXPECTED_SECOND_REVIEW_HASH
    )
    assert integrity["candidate_coverage_audit"]["aggregate_sha256"] == (
        review.EXPECTED_CANDIDATE_AUDIT_HASH
    )
    assert integrity["conjunctive_biomarker_fix"]["aggregate_sha256"] == (
        review.EXPECTED_CONJUNCTIVE_FIX_HASH
    )
    assert integrity["disease_normalization_review"]["aggregate_sha256"] == (
        review.EXPECTED_DISEASE_REVIEW_HASH
    )
    assert integrity["verified_disease_alias_fix"]["aggregate_sha256"] == (
        review.EXPECTED_ALIAS_FIX_HASH
    )
    assert integrity["candidate_counts"] == review.EXPECTED_CANDIDATE_COUNTS


def test_committed_artifacts_are_fresh(generated: Path) -> None:
    expected = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in generated.iterdir()
        if path.is_file()
    }
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in COMMITTED.iterdir()
        if path.is_file()
    }
    assert actual == expected


def test_two_runs_and_reversed_input_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    reversed_output = tmp_path / "reversed"
    review.generate_review(ROOT, first, GOLD)
    review.generate_review(ROOT, second, GOLD)
    review.generate_review(ROOT, reversed_output, GOLD, reverse_inputs=True)
    first_bytes = {path.name: path.read_bytes() for path in first.iterdir()}
    assert {path.name: path.read_bytes() for path in second.iterdir()} == first_bytes
    assert {
        path.name: path.read_bytes() for path in reversed_output.iterdir()
    } == first_bytes


def test_raw_adapter_input_guard_rejects_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(review, "EXPECTED_RAW_V2_INPUT_HASH", "0" * 64)
    with pytest.raises(RuntimeError, match="raw_v2_adapter_inputs hash mismatch"):
        review.generate_review(ROOT, tmp_path / "mismatch", GOLD)


def test_uncontrolled_output_file_does_not_enter_manifest(tmp_path: Path) -> None:
    output = tmp_path / "prepopulated"
    output.mkdir()
    (output / "stale-uncontrolled.txt").write_text("stale", encoding="utf-8")
    manifest = review.generate_review(ROOT, output, GOLD)
    assert "stale-uncontrolled.txt" not in manifest["artifact_hashes"]
    assert set(manifest["artifact_hashes"]) == set(review.OUTPUT_ARTIFACT_NAMES)
    assert manifest["generator_source_sha256"] == hashlib.sha256(
        Path(review.__file__).read_bytes()
    ).hexdigest()


def test_review_requires_no_external_services(generated: Path) -> None:
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    assert manifest["network_used"] is False
    assert manifest["neo4j_used"] is False
    assert manifest["llm_used"] is False
    assert manifest["pmid_content_read"] is False
    assert manifest["adapter_modified"] is False
    assert manifest["corpus_modified"] is False
    assert manifest["retriever_modified"] is False
    assert manifest["scoring_modified"] is False


def test_readiness_stays_conservative(generated: Path) -> None:
    manifest = json.loads((generated / "review_manifest.json").read_text("utf-8"))
    readiness = manifest["readiness"]
    assert readiness["multi_intervention_root_causes_identified"] is True
    assert readiness["statement_atomicity_decision_ready"] is False
    assert readiness["adapter_schema_revision_required"] is True
    assert readiness["corpus_regeneration_required"] is True
    assert readiness["source_review_required"] is True
    assert readiness["ready_to_implement_adapter_decision"] is False
    assert readiness["ready_for_hierarchy_policy_implementation"] is False
    assert readiness["ready_for_full_exploratory_rerun"] is False
