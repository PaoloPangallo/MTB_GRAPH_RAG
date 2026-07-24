from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.mtb_evidence.evaluation.scripts.multi_intervention_source_review import (
    EXPECTED_AUTHOR_APPROVAL_HASH,
    EXPECTED_FULLTEXT_HASH,
    EXPECTED_GROUP_IDS,
    EXPECTED_PREVIOUS_REVIEW_HASH,
    REVIEW_METADATA,
    generate,
)


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"
COMMITTED = (
    ROOT / "benchmarks/mtb_evidence/v3/multi_intervention_source_review"
)


def _jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (COMMITTED / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _snapshot(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    output = tmp_path_factory.mktemp("multi-intervention-source-review")
    result = generate(ROOT, output, GOLD)
    return output, result


def test_all_thirteen_groups_and_every_intervention_are_reviewed() -> None:
    decisions = _jsonl("group_atomicity_decisions.jsonl")
    annotations = _jsonl("intervention_level_annotations.jsonl")
    assert tuple(row["graph_evidence_id"] for row in decisions) == EXPECTED_GROUP_IDS
    assert len(annotations) == 28
    assert all(row["all_interventions_classified"] for row in decisions)
    assert all(row["classification"] for row in annotations)
    assert all(row["review_status"] == "first_review_complete" for row in annotations)
    assert all(row["propagation_policy"] == "prototype_only" for row in annotations)
    assert not any(row["hard_filterable"] for row in annotations)
    assert not any(row["final_evaluable"] for row in annotations)


def test_every_decision_has_a_precise_or_explicitly_insufficient_locator() -> None:
    decisions = _jsonl("group_atomicity_decisions.jsonl")
    annotations = _jsonl("intervention_level_annotations.jsonl")
    assert all(row["locators"] for row in decisions)
    assert all(row["all_decisions_have_locator"] for row in decisions)
    assert all(row["locator"] for row in annotations)
    assert {row["locator_status"] for row in annotations} <= {
        "complete",
        "insufficient",
    }
    insufficient = [
        row for row in annotations if row["locator_status"] == "insufficient"
    ]
    assert {row["graph_evidence_id"] for row in insufficient} == {"evidence:3811"}


def test_no_aggregate_or_regimen_is_split_into_specific_children() -> None:
    decisions = {
        row["graph_evidence_id"]: row["atomicity_decision"]
        for row in _jsonl("group_atomicity_decisions.jsonl")
    }
    simulation = json.loads(
        (COMMITTED / "post_review_schema_simulation.json").read_text(
            encoding="utf-8"
        )
    )
    forbidden = {"aggregate_parent_only", "combination_regimen_required"}
    assert not any(
        decisions[row["parent_graph_evidence_id"]] in forbidden
        for row in simulation["simulated_child_statements"]
    )
    assert simulation["combination_regimen_group_count"] == 3


def test_mentions_comparators_and_pending_mappings_are_not_support() -> None:
    annotations = _jsonl("intervention_level_annotations.jsonl")
    children = {
        (row["parent_graph_evidence_id"], row["intervention"])
        for row in json.loads(
            (COMMITTED / "post_review_schema_simulation.json").read_text(
                encoding="utf-8"
            )
        )["simulated_child_statements"]
    }
    excluded_statuses = {
        "comparator_only",
        "mentioned_background_only",
        "possible_alias_not_verified",
        "drug_class_member_not_individually_tested",
    }
    assert not any(
        (row["graph_evidence_id"], row["intervention"]) in children
        for row in annotations
        if row["classification"] in excluded_statuses
    )
    pending = [
        row
        for row in annotations
        if row["classification"] == "possible_alias_not_verified"
    ]
    assert {(row["graph_evidence_id"], row["intervention"]) for row in pending} == {
        ("evidence:841", "luminespib"),
        ("evidence:1851", "infigratinib"),
        ("evidence:1853", "infigratinib"),
    }
    assert _jsonl("verified_aliases.jsonl") == []


def test_clinical_preclinical_and_negative_units_remain_separate() -> None:
    units = _jsonl("source_unit_annotations.jsonl")
    contexts = Counter(row["clinical_preclinical_context"] for row in units)
    assert contexts["clinical"] > 0
    assert contexts["preclinical"] > 0
    ceritinib = next(
        row
        for row in _jsonl("intervention_level_annotations.jsonl")
        if row["graph_evidence_id"] == "evidence:841"
        and row["intervention"] == "ceritinib"
    )
    assert "negative" in ceritinib["support_level"]
    assert "progression" in ceritinib["result_paraphrase"].casefold()


def test_parent_identity_and_simulated_child_ids_are_stable() -> None:
    simulation = json.loads(
        (COMMITTED / "post_review_schema_simulation.json").read_text(
            encoding="utf-8"
        )
    )
    children = simulation["simulated_child_statements"]
    identifiers = [row["simulated_child_statement_id"] for row in children]
    assert simulation["parent_statements_preserved"] == 13
    assert simulation["parent_graph_evidence_ids_preserved"] == 13
    assert len(children) == len(identifiers) == len(set(identifiers)) == 8
    assert all(row["parent_graph_evidence_id"] in EXPECTED_GROUP_IDS for row in children)
    assert simulation["id_strategy"]["order_independent"]
    assert simulation["id_strategy"]["collision_count"] == 0


def test_second_review_packets_are_blind_and_complete() -> None:
    packets = sorted((COMMITTED / "second_review_packets").glob("*.json"))
    assert len(packets) == 13
    prohibited_values = {
        "atomic_children_supported",
        "aggregate_parent_only",
        "combination_regimen_required",
        "mixed_parent_and_children",
        "should_not_materialize_missing_interventions",
        "insufficient_for_atomicity_decision",
        "first_review_complete",
        "mixed_policy",
    }
    for path in packets:
        payload = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, sort_keys=True)
        assert payload["blind_annotation_id"].startswith("MI-B-")
        assert "review_assignment" not in payload
        assert not any(value in serialized for value in prohibited_values)


def test_gold_is_not_used_and_operational_components_are_unchanged() -> None:
    manifest = json.loads(
        (COMMITTED / "review_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["decisions_frozen_before_gold_access"]
    assert not manifest["gold_content_loaded"]
    assert not manifest["gold_used_for_decision"]
    assert not manifest["adapter_modified"]
    assert not manifest["corpus_modified"]
    assert not manifest["retriever_modified"]
    assert not manifest["scoring_modified"]
    integrity = manifest["integrity"]
    assert (
        integrity["previous_multi_intervention_review"]["aggregate_sha256"]
        == EXPECTED_PREVIOUS_REVIEW_HASH
    )
    assert (
        integrity["previous_author_approvals"]["aggregate_sha256"]
        == EXPECTED_AUTHOR_APPROVAL_HASH
    )
    assert (
        integrity["local_fulltext_26698910"]["sha256"]
        == EXPECTED_FULLTEXT_HASH
    )


def test_regression_principles_are_encoded_without_modifying_approvals() -> None:
    recommendation = json.loads(
        (COMMITTED / "architectural_recommendation.json").read_text(
            encoding="utf-8"
        )
    )
    forbidden = recommendation["changes_forbidden_without_further_review"]
    assert "aggregate-to-specific attribution" in forbidden
    assert "pending mapping promotion" in forbidden
    assert "automatic atomization of regimen components" in forbidden
    assert recommendation["second_independent_review_required"]


def test_generation_matches_committed_machine_artifacts(generated: tuple[Path, dict]) -> None:
    output, _ = generated
    suffixes = {".json", ".jsonl"}
    committed = {
        path.relative_to(COMMITTED).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in COMMITTED.rglob("*")
        if path.is_file() and path.suffix in suffixes
    }
    actual = {
        path.relative_to(output).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in output.rglob("*")
        if path.is_file() and path.suffix in suffixes
    }
    assert actual == committed


def test_two_runs_and_reversed_input_are_byte_identical(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    reversed_output = tmp_path / "reversed"
    generate(ROOT, first, GOLD)
    generate(ROOT, second, GOLD)
    generate(ROOT, reversed_output, GOLD, reverse_inputs=True)
    assert _snapshot(first) == _snapshot(second) == _snapshot(reversed_output)


def test_outputs_have_no_machine_specific_paths() -> None:
    for path in COMMITTED.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "C:\\\\" not in text
        assert "Users\\\\" not in text
        assert "Desktop\\\\" not in text


def test_review_metadata_contract_is_frozen() -> None:
    assert REVIEW_METADATA == {
        "reviewer_role": "author_review",
        "review_independence": "non_independent",
        "review_status": "first_review_complete",
        "propagation_policy": "prototype_only",
        "hard_filterable": False,
        "final_evaluable": False,
    }
