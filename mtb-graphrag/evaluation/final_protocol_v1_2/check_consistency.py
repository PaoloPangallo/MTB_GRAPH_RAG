"""Fail-closed static consistency checker for Final Evaluation Protocol 1.2.

The checker reads protocol artifacts and Git objects only. It never executes
the final runtime, selector, models, or network operations.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
GIT_ROOT = REPO_ROOT.parent

RUNTIME = "3d2251f82a586535f79f3d0b3725c16330c365ba"
PARENT_SHA = "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889"
A01_SHA = "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf"
S01_RAW_SHA = "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99"
S01_PACKAGE_SHA = "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15"
DESIGN_COMMIT = "fdf5e29d549a80ac351b08eb3b0ed05b64985c80"
BASE_COMMIT = "ae117ebcc1c75383b60e9266c0a7443bf9216245"

NORMATIVE_FILES = (
    "ablation_contract.json",
    "dataset_registry.json",
    "execution_contract.json",
    "latency_contract.json",
    "lineage.json",
    "metric_registry.json",
    "protocol_manifest.json",
    "reliability_contract.json",
    "result_schemas.json",
    "statistical_plan.json",
    "success_criteria.json",
)
REQUIRED_FILES = NORMATIVE_FILES + ("protocol_hash.json",)

DATASET_HASHES = {
    "dataset_bundle_sha256": "8ab387cbe65d0231e37be8f27a9b5ca81a29b14ae8d12e5df1b316695e553991",
    "gca_repository_2_0_46864": "62edc6907cf982eb2ed050d44a9e8218377a32daaf0c8847c98048b67be9ce54",
    "gca_repository_3_0_shadow": "59c47c893b2357fb110c9d2c82aa438bb22624ceea14af33aeef1c0cd0f0ac33",
    "sourceunit_selector_independent_20": "2a78d860dab9ac8d8277a39421ac2e60a2a05e2572ca26f29156591166efa03f",
    "s01_raw": S01_RAW_SHA,
    "s01_package": S01_PACKAGE_SHA,
    "rq4_development": "3eb2ee79c46dcbbf2fddf0385a2ed8189bcaf017e8a130265c7dea54a69353fc",
    "quote_battery": "9ceb959a0784bf466278fa420cca8d02321e3f51d54f6cde8a019b75d93a3d88",
    "dossier_narrator": "00bc29eac3bc3b03279b9f3dbf28268c1933ebb2628295ec3704da96cf359d04",
    "narrator_adversarial": "4ce813e5ffc9a6f4782b2fe9894b35217321ecf62d105825613d31e6e9d74bed",
    "heldout_architectural": "b621ef82bffa5a0bd73b2e60c0a2bd9c657258d3cdfd8404feb3586d0c8bf019",
    "narrative_heldout": "002f48042315b82a70eb3788eba3c5e9431fe16c30980d5b68803b85195c513e",
    "narrative_controls": "4e6a7800a653efd7c945944b68e59864e7aa15f240d627cbf188130f41171478",
    "heldout_bundle": "17583e218595f574931dfe0c71f8822f393ceb76c3a98bcf3f179369f053b313",
    "reliability_file": "9329b3836feab483ebfcacc70eee6c27fef2f911cf52c6237a8cc1d891ffdc38",
    "reliability_ids": "9d69478392a9df96187827a1130d59f78747453fdaa070256f910a937a720fd3",
    "operational_corpus": "d9e4d9d680b30ed2e7d8463bd708c4f83518472624fd3b5c37ec56bb06bf35e9",
    "operational_manifest": "ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b",
    "a01_cache_contract": "6b5f5858422b3e000c7fa29640a9cc6448c353db7066a938c14629ada88d04bd",
    "historical_regression": "ece8707f282dd865fc45d648e4b502ab88731e3148bb911c5ff400d4165a613e",
}


class CheckResults:
    """Collect checks without allowing a partial pass to be mistaken for success."""

    def __init__(self) -> None:
        self.items: list[tuple[str, bool, str]] = []

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.items.append((name, passed, detail))

    def emit(self) -> int:
        for name, passed, detail in self.items:
            print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")
        failures = sum(not passed for _, passed, _ in self.items)
        print(f"SUMMARY | checks={len(self.items)} | failed={failures}")
        return int(bool(failures))


def load_json(name: str) -> dict[str, Any]:
    value = json.loads((HERE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_ancestor_seal(
    record: dict[str, Any], base: Path, digest_field: str
) -> tuple[bool, str]:
    observed = {name: sha256_normalized(base / name) for name in record["files"]}
    joined = "\n".join(f"{name}:{observed[name]}" for name in sorted(observed))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return observed == record["files"] and digest == record[digest_field], digest


def git_changed(paths: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(GIT_ROOT), "diff", "--name-only", BASE_COMMIT, "--", *paths],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return [line for line in result.stdout.splitlines() if line]


def git_worktree_changed(paths: list[str]) -> list[str]:
    """Include tracked and untracked paths when protecting frozen ancestors."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(GIT_ROOT),
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            *paths,
        ],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    changed: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        changed.append(line[3:])
    return changed


def compute_protocol_hash() -> tuple[str, dict[str, str]]:
    files = {name: sha256_bytes(HERE / name) for name in NORMATIVE_FILES}
    joined = "\n".join(f"{name}:{files[name]}" for name in sorted(files))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), files


def validate() -> CheckResults:
    results = CheckResults()
    missing = [name for name in REQUIRED_FILES if not (HERE / name).is_file()]
    results.add(
        "required normative artifacts",
        not missing,
        "complete" if not missing else f"PROTOCOL_INCOMPLETE missing={','.join(missing)}",
    )
    if missing:
        return results

    manifest = load_json("protocol_manifest.json")
    lineage = load_json("lineage.json")
    metrics = load_json("metric_registry.json")
    criteria = load_json("success_criteria.json")
    schemas = load_json("result_schemas.json")
    stats = load_json("statistical_plan.json")
    execution = load_json("execution_contract.json")
    latency = load_json("latency_contract.json")
    ablations = load_json("ablation_contract.json")
    reliability = load_json("reliability_contract.json")
    datasets = load_json("dataset_registry.json")
    seal = load_json("protocol_hash.json")

    results.add("protocol version", manifest.get("protocol_version") == "1.2", str(manifest.get("protocol_version")))
    results.add("protocol ID", manifest.get("protocol_id") == "mtb-graphrag-final-evaluation/1.2", str(manifest.get("protocol_id")))
    results.add("accepted status", manifest.get("status") == manifest.get("review_status") == "ACCEPTED", str(manifest.get("review_status")))
    results.add("frozen", manifest.get("frozen") is True and isinstance(manifest.get("freeze_timestamp"), str) and manifest.get("freeze_scope") == "FINAL_EVALUATION_PROTOCOL_1_2_FINAL_FREEZE", str(manifest.get("frozen")))
    review = manifest.get("human_review", {})
    decisions = review.get("decision_set", {})
    results.add("human review", review.get("reviewer") == "Paolo Pangallo" and review.get("review_date") == "2026-08-11" and review.get("review_verdict") == "ACCEPTED" and decisions == {f"D{i:02d}": "APPROVED" for i in range(2, 17)}, "ACCEPTED D02-D16")
    results.add("freeze boundary", manifest.get("final_results_observed_before_protocol_1_2_freeze") is False and manifest.get("final_runs_executed_before_protocol_1_2_freeze") is False, "false/false")
    results.add("runtime identity", manifest.get("runtime_commit") == RUNTIME, str(manifest.get("runtime_commit")))
    results.add("no pre-v1.2 results", manifest.get("final_results_observed_before_v1_2") is False and manifest.get("final_runs_executed_before_v1_2") is False, "false/false")
    results.add("normative file set", tuple(manifest.get("normative_files", ())) == NORMATIVE_FILES, str(manifest.get("normative_files")))
    results.add("JSON-only authority", manifest.get("normative_authority") == "JSON_ONLY" and manifest.get("markdown_role") == "EXPLANATION_ONLY", "JSON_ONLY")
    results.add("decision map D02-D16", set(manifest.get("decision_resolution_map", {})) == {f"D{i:02d}" for i in range(2, 17)}, "15/15")

    parent_record = json.loads((REPO_ROOT / "evaluation/final_protocol/protocol_hash.json").read_text(encoding="utf-8"))
    a01_record = json.loads((REPO_ROOT / "evaluation/final_protocol/amendments/A01/amendment_hash.json").read_text(encoding="utf-8"))
    s01_record = json.loads((REPO_ROOT / "evaluation/final_protocol/supplements/S01/supplement_hash.json").read_text(encoding="utf-8"))
    parent_ok, parent_digest = verify_ancestor_seal(parent_record, REPO_ROOT, "protocol_sha256")
    a01_ok, a01_digest = verify_ancestor_seal(a01_record, REPO_ROOT / "evaluation/final_protocol/amendments/A01", "amendment_sha256")
    s01_digest, _ = compute_s01_hash(s01_record)
    results.add("parent 1.1 seal", parent_ok and parent_digest == PARENT_SHA, parent_digest)
    results.add("A01 seal", a01_ok and a01_digest == A01_SHA, a01_digest)
    results.add("S01 raw", sha256_bytes(REPO_ROOT / "evaluation/final_protocol/supplements/S01/sourceunits_1697.jsonl") == S01_RAW_SHA, S01_RAW_SHA)
    results.add("S01 package seal", s01_digest == S01_PACKAGE_SHA == s01_record.get("supplement_sha256"), s01_digest)
    results.add("lineage identities", lineage.get("runtime_commit") == RUNTIME and lineage.get("protocol_1_1", {}).get("sha256") == PARENT_SHA and lineage.get("A01", {}).get("sha256") == A01_SHA and lineage.get("S01", {}).get("raw_sha256") == S01_RAW_SHA and lineage.get("S01", {}).get("package_sha256") == S01_PACKAGE_SHA and lineage.get("design_commit") == DESIGN_COMMIT, "all exact")
    results.add("D16 precedence", lineage.get("freeze_precedence", {}).get("classification_of_stale_markers") == "STALE_PRE_FREEZE_PROSE" and lineage.get("freeze_precedence", {}).get("ordered_authorities") == ["evaluation/final_protocol/protocol_hash.json", "7b0b396b10d10794ac802325f8e7e2ff5ce33e28", "generated heldout_manifest.json and reliability_subset.json", "A01 frozen record"], "ordered 1..4")

    rq1 = metrics.get("RQ1", {})
    core = rq1.get("core_fields", [])
    results.add("D02 core fields", len(core) == 16 and len(set(core)) == 16, str(len(core)))
    results.add("D02 candidate precision", rq1.get("candidate_structural_precision") == {"unit": "materialized_candidate", "numerator": "non_spurious_structurally_valid_materialized_candidates", "denominator": "materialized_candidates"}, "candidate denominator")
    results.add("D02 path coverage", rq1.get("materialization_recall") == {"report_alias": "path_coverage", "unit": "eligible_KG_path", "numerator": "eligible_paths_with_corresponding_candidate", "denominator": 46864}, "46864 paths")
    results.add("D02 completeness required", rq1.get("core_field_completeness_micro", {}).get("required") is True and rq1.get("core_field_completeness_micro", {}).get("denominator") == "46864*16" and rq1.get("all_16_core_fields_correct_rate", {}).get("required") is True and rq1.get("all_16_core_fields_correct_rate", {}).get("denominator") == 46864, "both required")
    results.add("D02 identity separate", rq1.get("payload_identity_integrity", {}).get("separate_from_semantic_completeness") is True, "separate")
    results.add("D02 H-E/H-F", rq1.get("negative_polarity", {}).get("H-E") == {"primary_denominator": 1936, "target": "0/1936", "optional_full_corpus_companion": "0/46864"} and rq1.get("negative_polarity", {}).get("H-F") == {"primary_denominator": 1936, "target": "0/1936"}, "1936 primary")

    rq2 = metrics.get("RQ2", {})
    results.add("D03 population", rq2.get("primary_positive_population") == {"relevance": "DIRECTLY_RELEVANT", "N": 9, "unit": "candidate_document_pair", "aggregation": "MACRO"}, "N=9 macro")
    results.add("D03 K and formulas", rq2.get("K") == 5 and rq2.get("precision_at_k", {}).get("denominator") == "K" and rq2.get("mrr", {}).get("miss_contribution") == 0 and rq2.get("mean_first_relevant_rank") == {"condition": "HITS_ONLY", "N_hits_required": True}, "K=5 exact")
    results.add("D03 companion/zero-direct", rq2.get("overall_direct_hit_coverage", {}).get("N") == 20 and rq2.get("zero_direct_behavior", {}).get("N") == 11 and rq2.get("zero_direct_behavior", {}).get("selector_no_relevance_detection_claim_allowed") is False, "20 companion / 11 separate")
    gold = rq2.get("gold_context_contract", {})
    results.add("D04 GOLD", gold.get("positive_units") == ["DIRECTLY_RELEVANT"] and gold.get("zero_direct_units") == ["DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"] and gold.get("order") == "source_unit_id_ASC" and gold.get("truncation") == "NONE" and gold.get("context_budget_equalized") is False and gold.get("comparison_classification") == "FULL_GOLD_CONTEXT_VS_BOUNDED_SELECTOR_FIDELITY", "full context")
    results.add("D04 report label", gold.get("required_report_label") == "Full annotated GOLD context vs bounded K=5 selector context; not an equal-context-budget comparison.", "exact")

    results.add("D05 ablation A", ablations.get("A") == {"name": "PRE_RETRIEVAL_AUTHORITY_BOUNDARY_BYPASS", "remove_stages": ["3", "3b"], "parser_output": "UNCHANGED", "retrieval": "UNCHANGED", "mechanism": "HARNESS_SIDE_STAGE_BYPASS"}, "stages 3/3b")
    results.add("D06 ablation C", ablations.get("C", {}).get("name") == "QUOTE_VALIDATOR_BYPASS" and ablations.get("C", {}).get("transport_validation") == "RETAINED" and ablations.get("C", {}).get("schema_validation") == "RETAINED" and ablations.get("C", {}).get("schema_valid_QUOTE") == "IDENTITY_SEMANTIC_VALIDATOR" and ablations.get("C", {}).get("ABSTAIN") == "UNCHANGED" and ablations.get("C", {}).get("transport_failure") == "UNCHANGED" and ablations.get("C", {}).get("schema_invalid") == "UNCHANGED", "identity validator only")
    results.add("D07 ablation D", ablations.get("D", {}).get("name") == "NARRATIVE_VERIFIER_BYPASS" and ablations.get("D", {}).get("narrator") == "EXECUTED_NORMALLY" and ablations.get("D", {}).get("narrative_verifier") == "NOT_CALLED" and ablations.get("D", {}).get("transport_valid_narrative") == "PRESENTED_IN_OFFLINE_ABLATION" and ablations.get("D", {}).get("canonical_dossier") == "UNCHANGED" and ablations.get("D", {}).get("fabricated_output_allowed") is False, "offline only")
    results.add("ablation B", ablations.get("B", {}).get("replacements") == ["FIRST_K", "BM25"] and ablations.get("B", {}).get("same") == ["document", "SourceUnits", "gold"] and ablations.get("B", {}).get("K") == 5, "same K=5")

    results.add("D08 totals", reliability.get("n_cases") == 10 and reliability.get("repetitions") == ["r01", "r02", "r03"] and reliability.get("n_executions") == 30 and reliability.get("rounds") == 3 and reliability.get("case_order_per_round") == "case_id_LEXICOGRAPHIC", "10x3")
    stratum_a = reliability.get("strata", {}).get("A", {})
    results.add("D08 stratum A cache", stratum_a.get("n_cases") == 7 and stratum_a.get("arm") == "CANONICAL_FULL_SYSTEM" and stratum_a.get("cache") == {"source": "AUTHORIZED_DOCUMENT_CACHE_43", "operational_corpus_sha256": DATASET_HASHES["operational_corpus"], "manifest_sha256": DATASET_HASHES["operational_manifest"], "initialization": "FRESH_ISOLATED_EPHEMERAL_CACHE_PER_RUN", "shared_mutable_cache": False, "cross_run_state_flow": False} and stratum_a.get("network_policy") == "CANONICAL_RUNTIME_POLICY", "fresh per run")
    stratum_b = reliability.get("strata", {}).get("B", {})
    results.add("D08 stratum B direct S01", stratum_b.get("n_cases") == 3 and stratum_b.get("input_source") == "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01" and stratum_b.get("cache") == "NOT_APPLICABLE" and stratum_b.get("document_resolver") == "NOT_CALLED" and stratum_b.get("network") == "PROHIBITED" and stratum_b.get("arm") == "DETERMINISTIC_SELECTOR_K5_TO_SAME_GEMMA_TO_SAME_QUOTE_VALIDATOR", "no resolver/network")
    results.add("D08 separate reporting", reliability.get("reporting") == "REPORT_STRATA_SEPARATELY_NEVER_AGGREGATE", "separate")

    retry = execution.get("retry_policy", {})
    results.add("D09 retry", execution.get("scientific_repetition_equals_infrastructure_attempt") is False and retry.get("runtime_native_timeout_5xx") == "SAME_ATTEMPT" and retry.get("terminal_4xx_404") == "NO_SEMANTIC_RETRY_PRESERVE" and retry.get("provider_unavailable") == "INFRASTRUCTURE_FAILED" and retry.get("schema_invalid_model_output") == "PRESERVE_NO_SEMANTIC_RETRY" and retry.get("controlled_canonical_failure") == "VALID_RESULT_NO_RETRY", "complete")
    results.add("D09 reconciliation", retry.get("process_crash") == {"orphan_state": "ATTEMPT_RESERVED", "detector": "RECONCILIATION_RECOVERY_PASS", "action": "APPEND_INCOMPLETE", "crashed_process_writes_event": False, "new_attempt_allowed": True}, "append INCOMPLETE")

    bootstrap = stats.get("paired_percentile_bootstrap", {})
    results.add("D10 no p-values", stats.get("p_values_planned") is False and "hypothesis_test" not in json.dumps(stats).lower(), "global false")
    results.add("D10 bootstrap", bootstrap.get("samples") == 10000 and bootstrap.get("seed") == 20260809 and bootstrap.get("confidence_level") == 0.95 and bootstrap.get("ci_type") == "PERCENTILE" and bootstrap.get("statistic") == "MEAN_PAIRED_DIFFERENCE_OF_PER_CASE_CONTRIBUTION" and bootstrap.get("ties") == 0 and bootstrap.get("infrastructure_failed_pair") == "EXCLUDE_PRESERVE_SEPARATELY_REPORT_N_EFFECTIVE" and bootstrap.get("imputation") == "NONE", "10000/20260809")
    results.add("Wilson", stats.get("proportions") == {"interval": "WILSON", "confidence_level": 0.95, "zero_event_format": "0/N"}, "95%")

    stage_model = latency.get("stage_model", {})
    results.add("D11 stages", stage_model.get("stage_record_count") == 16 and stage_model.get("stage_ids") == ["1", "2", "3", "3b", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"], "16")
    results.add("D11 E2E", latency.get("primary") == {"metric": "end_to_end_latency_ms", "clock": "MONOTONIC_WALL_CLOCK", "start": "IMMEDIATELY_BEFORE_CANONICAL_RUNTIME_ENTRY", "end": "TERMINAL_RETURN"} and latency.get("sum_stage_durations") == "DIAGNOSTIC_ONLY", "wall clock")
    pair = latency.get("same_document_cache_latency_pair", {})
    results.add("D12 latency pair", pair.get("fixture_id") == "SAME-DOCUMENT CACHE LATENCY PAIR" and pair.get("case_id") == "GCA-0000980ba01970f893f8e4d7" and pair.get("document_id") == "pmid:15705718" and pair.get("LAT-HIT") == "TARGET_SEEDED" and pair.get("LAT-MISS") == "SAME_PLAN_TARGET_EXCLUDED" and pair.get("replacement_after_outcome") == "PROHIBITED", "exact GCA/document")

    identifiers = execution.get("identifiers", {})
    results.add("D13 canonical JSON", identifiers.get("canonical_json") == {"encoding": "UTF-8", "sorted_keys": True, "separators": [",", ":"]}, "canonical")
    results.add("D13 IDs", identifiers.get("evaluation_id", {}).get("prefix") == "fe_" and identifiers.get("evaluation_id", {}).get("fields") == ["runtime_commit", "protocol_version", "protocol_sha256", "inherited_A01_sha256", "S01_package_sha256", "harness_commit"] and identifiers.get("run_id", {}).get("prefix") == "run_" and identifiers.get("run_id", {}).get("fields") == ["evaluation_id", "testbed", "case_id", "arm", "repetition_id"] and identifiers.get("attempt_id_pattern") == "<run_id>/aNNNN" and identifiers.get("outcome_dependent") is False and identifiers.get("timestamps_in_ids") is False, "outcome independent")

    results.add("D14 dataset map", datasets.get("dataset_hashes") == DATASET_HASHES and "dataset_hash" not in datasets, "19 exact hashes")
    envelope = schemas.get("common_execution_envelope", {})
    required_envelope = {"schema_version", "identity", "normative_identity", "dataset_hashes", "model_configuration", "selector_configuration", "started_at", "completed_at", "status", "failure_class", "raw_reason_code", "input_hash", "output_hash", "runtime_call_counts", "model_call_counts", "network_call_counts", "raw_payload_path", "raw_payload_sha256", "scientific_payload"}
    results.add("D15 envelope", envelope.get("classification") == "INFRASTRUCTURAL_WRAPPER" and envelope.get("replaces_scientific_schemas") is False and set(envelope.get("required_fields", [])) == required_envelope, "all required")
    lifecycle = execution.get("raw_lifecycle", {})
    results.add("D15 raw lifecycle", lifecycle == {"ledger": "APPEND_ONLY", "before_execution": "ATTEMPT_RESERVED", "raw_create": "IMMUTABLE_CREATE_IF_ABSENT", "duplicate_attempt_id": "HARD_FAIL", "completed_run": "NO_AUTOMATIC_RERUN", "infrastructure_retry": "NEW_ATTEMPT_SAME_RUN", "scientific_repeat": "NEW_REPETITION_NEW_RUN", "aggregate": "DERIVED_VERSIONED", "raw": "NEVER_MODIFIED"}, "append-only")

    active_hard = {f"H-{letter}" for letter in "ABCDEFGH"} | {"H-K", "H-O", "H-P"}
    heldout = {"H-L", "H-M", "H-N"}
    retired = {"H-I", "H-J"}
    historical = {"R-1", "R-2"}
    results.add("stable criteria IDs", set(criteria.get("active_HARD", [])) == active_hard and set(criteria.get("heldout", [])) == heldout and set(criteria.get("retired_from_primary", [])) == retired and set(criteria.get("historical_only", [])) == historical and criteria.get("renumbering_allowed") is False, "stable")
    results.add("criteria supersession", criteria.get("v1_2_supersedes") == {"H-E.primary_denominator": 1936, "H-E.target": "0/1936", "H-F.primary_denominator": 1936, "H-F.target": "0/1936"}, "explicit")

    results.add("A01 referenced not copied", lineage.get("A01", {}).get("source_of_truth") == "evaluation/final_protocol/amendments/A01" and lineage.get("A01", {}).get("bindings_copy_in_v1_2") is False, "direct read")
    results.add("S01 referenced not copied", lineage.get("S01", {}).get("source_of_truth") == "evaluation/final_protocol/supplements/S01" and lineage.get("S01", {}).get("text_copy_in_v1_2") is False, "direct read")
    results.add("final results absent", not (REPO_ROOT / "evaluation/final_evaluation").exists(), str((REPO_ROOT / "evaluation/final_evaluation").exists()))

    protected_paths = ["mtb-graphrag/evaluation/final_protocol", "mtb-graphrag/backend", "mtb-graphrag/frontend/src", "mtb-graphrag/evaluation/sourceunit_selector_independent"]
    protected = sorted(set(git_changed(protected_paths) + git_worktree_changed(protected_paths)))
    results.add("frozen ancestors untouched", not protected, str(protected))
    protocol_digest, file_hashes = compute_protocol_hash()
    results.add("seal normative files", tuple(seal.get("normative_files", ())) == NORMATIVE_FILES and seal.get("files") == file_hashes, "exact")
    expected_ancestors = {
        "runtime_commit": RUNTIME,
        "protocol_1_1_sha256": PARENT_SHA,
        "A01_sha256": A01_SHA,
        "S01_raw_sha256": S01_RAW_SHA,
        "S01_package_sha256": S01_PACKAGE_SHA,
    }
    results.add("seal ancestor identities", seal.get("ancestor_identities") == expected_ancestors, "all exact")
    results.add("protocol 1.2 seal", seal.get("protocol_1_2_sha256") == protocol_digest, protocol_digest)
    results.add("seal state", seal.get("protocol_id") == "mtb-graphrag-final-evaluation/1.2" and seal.get("protocol_version") == "1.2" and seal.get("review_status") == "ACCEPTED" and seal.get("frozen") is True and seal.get("freeze_timestamp") == manifest.get("freeze_timestamp"), "accepted/frozen")
    return results


def compute_s01_hash(record: dict[str, Any]) -> tuple[str, dict[str, str]]:
    base = REPO_ROOT / "evaluation/final_protocol/supplements/S01"
    names = tuple(record["normative_files"])
    files = {name: sha256_bytes(base / name) for name in names}
    joined = "\n".join(f"{name}:{files[name]}" for name in sorted(files))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), files


def main() -> int:
    try:
        return validate().emit()
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL | PROTOCOL_1_2_SPECIFICATION_GAP | {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
