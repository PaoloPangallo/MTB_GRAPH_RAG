from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.mtb_evidence.evaluation.scripts import (
    candidate_coverage_audit as coverage_audit,
)

EXPECTED_GOLD_HASH = coverage_audit.EXPECTED_GOLD_HASH
GOLD_EVIDENCE_IDS = coverage_audit.GOLD_EVIDENCE_IDS
annotate_gold_records = coverage_audit.annotate_gold_records
run_no_gold_audit = coverage_audit.run_no_gold_audit
POST_ALIAS_FIX_RETRIEVER_HASH = (
    "b78ce4ea79e1ac090d29d4dc1c9cbc865bedc91dbdf3d77b469bdfde3f2cfd4c"
)


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"
FROZEN = ROOT / "benchmarks" / "mtb_evidence" / "v3" / "v2_v3a_exploratory_pilot"


@pytest.fixture(autouse=True)
def _accept_intentional_downstream_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        coverage_audit,
        "EXPECTED_RETRIEVER_HASH",
        POST_ALIAS_FIX_RETRIEVER_HASH,
    )


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _aggregate(paths: list[Path]) -> str:
    files = sorted(
        (item for path in paths for item in path.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(ROOT).as_posix().casefold(),
    )
    payload = "\n".join(
        f"{item.relative_to(ROOT).as_posix()}:{hashlib.sha256(item.read_bytes()).hexdigest()}"
        for item in files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_no_gold_audit_classifies_every_historical_record(tmp_path: Path) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    lineage = _jsonl(tmp_path / "candidate_lineage.jsonl")
    assert len(lineage) == 122
    assert len({row["lineage_id"] for row in lineage}) == 122
    allowed = {
        "ranked",
        "retained_with_warning",
        "audit_only",
        "rejected_by_native_constraints",
        "absent_before_candidate_generation",
    }
    assert {row["final_category"] for row in lineage} <= allowed
    missing = _jsonl(tmp_path / "missing_v2_candidates.jsonl")
    assert all(row["primary_cause"] for row in missing)
    assert all(row["first_divergence_stage"] for row in missing)
    assert all(row["cause_evidence"]["gold_used"] is False for row in missing)


def test_frozen_candidate_counts_and_extra_alk_are_preserved(tmp_path: Path) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    coverage = json.loads((tmp_path / "per_query_coverage.json").read_text("utf-8"))
    counts = {
        row["case_id"]: row["candidate_counts"] for row in coverage["queries"]
    }
    assert counts["PILOT-C1-EGFR-L858R-CONTEXT"] == {
        "historical_v2_records": 81,
        "historical_v2_unique_graph_evidence": 73,
        "v2_compatibility": 17,
        "native_only": 17,
        "qualified_soft": 17,
    }
    assert counts["PILOT-K1-FGFR2-iCCA"] == {
        "historical_v2_records": 28,
        "historical_v2_unique_graph_evidence": 25,
        "v2_compatibility": 1,
        "native_only": 1,
        "qualified_soft": 1,
    }
    assert counts["PILOT-A2-ALK-G1202R"] == {
        "historical_v2_records": 13,
        "historical_v2_unique_graph_evidence": 13,
        "v2_compatibility": 32,
        "native_only": 32,
        "qualified_soft": 32,
    }
    assert counts["PILOT-N1-RMI2-SNAPSHOT"] == {
        "historical_v2_records": 0,
        "historical_v2_unique_graph_evidence": 0,
        "v2_compatibility": 0,
        "native_only": 0,
        "qualified_soft": 0,
    }
    extras = _jsonl(tmp_path / "extra_v3_candidates.jsonl")
    alk_extras = [
        row for row in extras if row["case_id"] == "PILOT-A2-ALK-G1202R"
    ]
    assert len(alk_extras) == 23
    assert {row["classification"] for row in alk_extras} == {
        "normalization_overreach"
    }


def test_lineage_preserves_record_statement_source_and_dedup_units(
    tmp_path: Path,
) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    lineage = _jsonl(tmp_path / "candidate_lineage.jsonl")
    assert all(row["statement_present_in_repository"] is True for row in lineage)
    assert all(row["statement_present_in_corpus"] is True for row in lineage)
    assert all(row["graph_evidence_id"] for row in lineage)
    assert all("source_ids" in row for row in lineage)
    assert all("v2_traversal_origins" in row for row in lineage)
    duplicate_rows = [row for row in lineage if row["duplicate_group_size"] > 1]
    assert duplicate_rows
    assert all(
        row["lineage_outcome"] in {"deduplicated", "transformed", "excluded"}
        for row in duplicate_rows
    )
    fgfr1 = next(
        row
        for row in lineage
        if row["query_id"].startswith("PILOT-K1")
        and row["graph_evidence_id"] == "evidence:10325"
    )
    assert fgfr1["gene"] == "FGFR1"
    assert fgfr1["evidence_scope"] == "unknown"
    assert fgfr1["v2_source_kind"] == "evidence"


def test_filter_and_normalization_audits_expose_first_failure(tmp_path: Path) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    filters = _jsonl(tmp_path / "filter_stage_audit.jsonl")
    assert len(filters) == 147 * 4
    assert all(len(row["stages"]) == 6 for row in filters)
    assert all("first_failing_stage" in row for row in filters)
    normalization = _jsonl(tmp_path / "normalization_audit.jsonl")
    alk_extra = next(
        row
        for row in normalization
        if row["query_id"].startswith("PILOT-A2")
        and row["graph_evidence_id"] == "evidence:765"
    )
    assert alk_extra["gene_match"] is True
    assert alk_extra["alteration_match"] is False
    assert alk_extra["combined_native_biomarker_match"] is True
    assert alk_extra["pending_mapping_promoted"] is False


@pytest.mark.skipif(not GOLD.exists(), reason="bundle gold esterno non disponibile")
def test_gold_annotation_is_late_and_does_not_change_root_causes(
    tmp_path: Path,
) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    before = {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in (
            "candidate_lineage.jsonl",
            "missing_v2_candidates.jsonl",
            "root_cause_counts.json",
        )
    }
    annotate_gold_records(
        ROOT,
        tmp_path,
        GOLD,
        expected_gold_hash=EXPECTED_GOLD_HASH,
    )
    after = {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in before
    }
    assert before == after
    rows = _jsonl(tmp_path / "gold_missing_candidate_audit.jsonl")
    assert {row["graph_evidence_id"] for row in rows} == set(GOLD_EVIDENCE_IDS)
    assert all(row["cause_assigned_before_gold_access"] is True for row in rows)
    assert all(row["gold_changed_cause"] is False for row in rows)
    assert all(
        row["serialized_snapshot_evidence"]["origin"] == "frozen_kg"
        for row in rows
    )


@pytest.mark.skipif(not GOLD.exists(), reason="bundle gold esterno non disponibile")
def test_gold_phase_authenticates_every_causal_artifact_first(
    tmp_path: Path,
) -> None:
    run_no_gold_audit(ROOT, tmp_path)
    target = tmp_path / "missing_v2_candidates.jsonl"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="causal artifact hash mismatch"):
        annotate_gold_records(
            ROOT,
            tmp_path,
            GOLD,
            expected_gold_hash=EXPECTED_GOLD_HASH,
        )
    assert not (tmp_path / "gold_missing_candidate_audit.jsonl").exists()


def test_audit_is_byte_deterministic_and_order_invariant(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_no_gold_audit(ROOT, first)
    run_no_gold_audit(ROOT, second, reverse_input_order=True)
    names = {
        "v2_candidate_inventory.jsonl",
        "v3_candidate_inventory.jsonl",
        "candidate_lineage.jsonl",
        "missing_v2_candidates.jsonl",
        "extra_v3_candidates.jsonl",
        "per_query_coverage.json",
        "coverage_by_identity_level.json",
        "root_cause_counts.json",
        "normalization_audit.jsonl",
        "filter_stage_audit.jsonl",
        "proposed_corrections.jsonl",
    }
    assert {name: (first / name).read_bytes() for name in names} == {
        name: (second / name).read_bytes() for name in names
    }


def test_frozen_inputs_and_previous_results_are_byte_identical() -> None:
    v3 = ROOT / "benchmarks" / "mtb_evidence" / "v3"
    assert _aggregate([v3 / "qualification_corpus_v2"]) == (
        "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827"
    )
    assert _aggregate(
        [v3 / "priority_curation" / "annotation_packets" / "second_review"]
    ) == "6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6"
    config = (
        ROOT
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    assert hashlib.sha256(config.read_bytes()).hexdigest() == (
        "57d76d377029ba5c92cf4785d8143e2d06d02b6dc0e0c1d7ef57ea118e553fd4"
    )
    assert _aggregate([FROZEN]) == (
        "f0ca36d81024170a5fe51b32763333468091a1d3b3a15f822bf57694c7f711cd"
    )
    generated = ROOT / "benchmarks" / "mtb_evidence" / "v3" / "candidate_coverage_audit"
    manifest = json.loads(
        (generated / "audit_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["baseline_sha"] == (
        "ec2293baed1202edc9027fdb173a0aa25c1961f4"
    )
    assert manifest["source_kind"] == "canonical_generator_script_sha256"
    assert len(manifest["source_sha"]) == 64
    assert manifest["gold_annotation"][
        "all_causal_artifacts_authenticated"
    ] is True
    root_causes = json.loads(
        (generated / "root_cause_counts.json").read_text(encoding="utf-8")
    )
    assert root_causes["secondary_cause_record_counts"][
        "duplicate_canonicalization"
    ] == 11
    assert root_causes["secondary_cause_record_counts"][
        "adapter_conversion_loss"
    ] == 11


def test_audit_source_has_no_network_neo4j_llm_or_tuning_surface() -> None:
    source = (
        ROOT
        / "benchmarks"
        / "mtb_evidence"
        / "evaluation"
        / "scripts"
        / "candidate_coverage_audit.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()
    assert "requests." not in lowered
    assert "neo4j" not in lowered
    assert "openai" not in lowered
    assert "tuning" not in lowered
