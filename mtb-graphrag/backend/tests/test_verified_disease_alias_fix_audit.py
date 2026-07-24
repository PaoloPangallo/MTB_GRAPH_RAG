from __future__ import annotations

import json
from pathlib import Path

from benchmarks.mtb_evidence.evaluation.scripts.verified_disease_alias_fix import (
    EXPECTED_AFTER_COUNTS,
    EXPECTED_BEFORE_COUNTS,
    generate_audit,
)


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _bytes(path: Path) -> dict[str, bytes]:
    return {
        item.name: item.read_bytes()
        for item in sorted(path.iterdir(), key=lambda item: item.name)
        if item.is_file()
    }


def test_fix_audit_has_expected_candidate_diff(tmp_path: Path) -> None:
    manifest = generate_audit(ROOT, tmp_path, GOLD)
    diff = json.loads((tmp_path / "per_query_diff.json").read_text("utf-8"))
    by_case = {row["case_id"]: row for row in diff["queries"]}

    assert manifest["candidate_counts_before"] == EXPECTED_BEFORE_COUNTS
    assert manifest["candidate_counts_after"] == EXPECTED_AFTER_COUNTS
    assert by_case["PILOT-C1-EGFR-L858R-CONTEXT"][
        "expected_hierarchy_not_applied_count"
    ] == 10
    assert diff["totals"]["added"] == 32
    assert diff["totals"]["removed"] == 10
    assert diff["totals"]["unexpected_candidate_additions"] == 0
    assert diff["totals"]["unexpected_candidate_removals"] == 0


def test_all_new_candidates_are_verified_alias_recoveries(tmp_path: Path) -> None:
    generate_audit(ROOT, tmp_path, GOLD)
    rows = _jsonl(tmp_path / "newly_matched_verified_aliases.jsonl")

    assert len(rows) == 32
    assert {row["change_classification"] for row in rows} == {
        "expected_verified_alias_recovery"
    }
    assert {
        row["disease_match"]["match_type"] for row in rows
    } == {"verified_alias"}
    assert all(
        row["disease_match"]["hard_match_allowed"] is True for row in rows
    )


def test_required_evidence_ids_preserve_first_failure(tmp_path: Path) -> None:
    generate_audit(ROOT, tmp_path, GOLD)
    rows = _jsonl(tmp_path / "alias_match_audit.jsonl")
    egfr = {
        row["graph_evidence_ids"][0]: row
        for row in rows
        if row["case_id"] == "PILOT-C1-EGFR-L858R-CONTEXT"
        and row["graph_evidence_ids"]
    }
    fgfr2 = {
        row["graph_evidence_ids"][0]: row
        for row in rows
        if row["case_id"] == "PILOT-K1-FGFR2-iCCA"
        and row["graph_evidence_ids"]
    }

    assert egfr["evidence:11219"]["in_primary_candidate_set"] is True
    for graph_id in ("evidence:11598", "evidence:11599", "evidence:1867"):
        assert egfr[graph_id]["in_primary_candidate_set"] is False
        assert egfr[graph_id]["first_failing_native_constraint"] == "biomarker"
        assert egfr[graph_id]["disease_match"]["match_type"] == "verified_alias"
    assert fgfr2["evidence:8173"]["in_primary_candidate_set"] is False
    assert fgfr2["evidence:8173"]["first_failing_native_constraint"] == "disease"
    assert fgfr2["evidence:8173"]["disease_match"]["match_type"] == (
        "explicit_sibling"
    )


def test_manifest_proves_no_gold_or_external_use(tmp_path: Path) -> None:
    manifest = generate_audit(ROOT, tmp_path, GOLD)

    assert manifest["gold_bundle"]["aggregate_sha256"] == (
        "05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133"
    )
    assert manifest["gold_content_loaded"] is False
    assert manifest["gold_used_for_fix"] is False
    assert manifest["new_aliases_introduced"] == []
    assert manifest["hierarchy_policy_implemented"] is False
    assert manifest["multi_intervention_adapter_changed"] is False
    assert manifest["network_used"] is False
    assert manifest["neo4j_used"] is False
    assert manifest["llm_used"] is False


def test_audit_is_byte_deterministic_and_query_order_invariant(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_audit(ROOT, first, GOLD)
    generate_audit(ROOT, second, GOLD, reverse_query_order=True)

    assert _bytes(first) == _bytes(second)
    payload = b"".join(_bytes(first).values())
    assert str(ROOT).encode("utf-8") not in payload


def test_manifest_ignores_uncontrolled_preexisting_output_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "populated"
    generate_audit(ROOT, output, GOLD)
    clean_manifest = (output / "fix_manifest.json").read_bytes()
    (output / "MANUAL_REPORT.md").write_text(
        "not controlled by the generator\n",
        encoding="utf-8",
    )

    generate_audit(ROOT, output, GOLD)

    assert (output / "fix_manifest.json").read_bytes() == clean_manifest
    manifest = json.loads(clean_manifest)
    assert "MANUAL_REPORT.md" not in manifest["artifact_hashes"]


def test_frozen_inputs_are_authenticated(tmp_path: Path) -> None:
    manifest = generate_audit(ROOT, tmp_path, GOLD)
    integrity = manifest["input_integrity"]

    assert integrity["qualification_corpus"]["aggregate_sha256"] == (
        "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827"
    )
    assert integrity["second_review_packets"]["file_count"] == 70
    assert integrity["candidate_coverage_audit"]["aggregate_sha256"] == (
        "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
    )
    assert integrity["conjunctive_biomarker_fix"]["aggregate_sha256"] == (
        "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41d88638d"
    )
    assert integrity["disease_normalization_review"]["aggregate_sha256"] == (
        "1084763a50e63cfe4c19b72defca5c73788a826f5227a0fd4378c7bc1020b71c"
    )
    assert integrity["disease_normalizer"] == {
        "file_sha256": (
            "7e3ab30006ba9c7ccdc80b1d2a4bd544159b3fa0044aee87e3501847986593b7"
        ),
        "semantic_tables_sha256": (
            "6372a0b0f4b24e505266bd061d3997e75aee9cde4a01558ea57e9c3755c9abd4"
        ),
        "synonym_group_count": 4,
        "hierarchy_edge_count": 6,
    }
    assert manifest["scoring_config"]["canonical_hash"] == (
        "ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00"
    )
