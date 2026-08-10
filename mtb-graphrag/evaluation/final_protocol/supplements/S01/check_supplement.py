"""Fail-closed consistency checks for dataset supplement S01.

This module reads frozen artifacts and the preserved JSONL only. It never
executes the selector, runtime, models, or network operations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from hash_supplement import NORMATIVE_FILES, compute_package_hash

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
RAW = HERE / "sourceunits_1697.jsonl"
INVENTORY = REPO_ROOT / "evaluation/sourceunit_selector_independent/document_inventory.jsonl"
GOLD = REPO_ROOT / "evaluation/sourceunit_selector_independent/gold_annotations.csv"

EXPECTED_RAW_SHA = "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99"
EXPECTED_RAW_BYTES = 731754
EXPECTED_LABELS = {
    "DIRECTLY_RELEVANT": 29,
    "PARTIALLY_RELEVANT": 49,
    "CONTEXT_ONLY": 355,
    "NOT_RELEVANT": 1264,
}
EXPECTED_PARENT_SHA = "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889"
EXPECTED_A01_SHA = "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf"
EXPECTED_RUNTIME = "3d2251f82a586535f79f3d0b3725c16330c365ba"
EXPECTED_A01_FREEZE = "50df9bc7a1071816f6ea617731d229f36af2a2a5"
EXPECTED_GENERATOR_COMMIT = "9e9d8d5724592a0bd74d0dff8187067a0ad86d75"
EXPECTED_INVENTORY_COMMIT = "ec79b62dc4832a648e1ea2e7e2f7af7756617efa"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_embedded_seal(
    record: dict[str, Any], base: Path, digest_field: str
) -> tuple[bool, str]:
    observed = {
        name: sha256_normalized(base / name)
        for name in record["files"]
    }
    joined = "\n".join(f"{name}:{observed[name]}" for name in sorted(observed))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    passed = observed == record["files"] and digest == record[digest_field]
    return passed, digest


def git_object_exists(spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT.parent), "cat-file", "-e", spec],
        capture_output=True,
        check=False,
    ).returncode == 0


def git_blob(spec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT.parent), "show", spec],
        capture_output=True,
        check=True,
    )
    return result.stdout


def validate() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append((name, condition, detail))

    manifest = load_json(HERE / "supplement_manifest.json")
    provenance = load_json(HERE / "provenance.json")
    report = load_json(HERE / "validation_report.json")
    seal = load_json(HERE / "supplement_hash.json")
    parent = load_json(REPO_ROOT / "evaluation/final_protocol/protocol_hash.json")
    a01 = load_json(REPO_ROOT / "evaluation/final_protocol/amendments/A01/amendment_hash.json")
    raw_rows = load_jsonl(RAW)
    inventory_rows = load_jsonl(INVENTORY)
    with GOLD.open(encoding="utf-8", newline="") as handle:
        gold_rows = list(csv.DictReader(handle))

    raw_ids = [row["source_unit_id"] for row in raw_rows]
    raw_pairs = {(row["candidate_id"], row["document_id"]) for row in raw_rows}
    raw_documents = {row["document_id"] for row in raw_rows}
    inventory_ids = {
        source_unit_id
        for row in inventory_rows
        for source_unit_id in row["source_unit_ids"]
    }
    inventory_pairs = {(row["candidate_id"], row["document_id"]) for row in inventory_rows}
    gold_ids = {row["source_unit_id"] for row in gold_rows}
    labels = Counter(row["relevance_label"] for row in gold_rows)
    direct_cases = {
        row["candidate_id"] for row in gold_rows if row["relevance_label"] == "DIRECTLY_RELEVANT"
    }
    source_types = Counter(row["source_type"] for row in inventory_rows)
    raw_mapping = {
        row["source_unit_id"]: (row["candidate_id"], row["document_id"])
        for row in raw_rows
    }
    inventory_memberships = [
        (source_unit_id, row["candidate_id"], row["document_id"])
        for row in inventory_rows
        for source_unit_id in row["source_unit_ids"]
    ]
    inventory_mapping = {
        source_unit_id: (candidate_id, document_id)
        for source_unit_id, candidate_id, document_id in inventory_memberships
    }
    gold_mapping = {
        row["source_unit_id"]: (row["candidate_id"], row["document_id"])
        for row in gold_rows
    }
    raw_pair_counts = Counter((row["candidate_id"], row["document_id"]) for row in raw_rows)
    inventory_pair_counts = Counter(
        (row["candidate_id"], row["document_id"])
        for row in inventory_rows
        for _ in row["source_unit_ids"]
    )
    gold_pair_counts = Counter((row["candidate_id"], row["document_id"]) for row in gold_rows)

    check("raw sha256", sha256_bytes(RAW) == EXPECTED_RAW_SHA, sha256_bytes(RAW))
    check("raw bytes", RAW.stat().st_size == EXPECTED_RAW_BYTES, str(RAW.stat().st_size))
    check("SourceUnits", len(raw_rows) == 1697, str(len(raw_rows)))
    check("unique IDs", len(set(raw_ids)) == 1697, str(len(set(raw_ids))))
    check("non-empty text", sum(bool(row.get("text", "").strip()) for row in raw_rows) == 1697,
          str(sum(bool(row.get("text", "").strip()) for row in raw_rows)))
    check("candidate-document pairs", len(raw_pairs) == 20, str(len(raw_pairs)))
    check("documents", len(raw_documents) == 20, str(len(raw_documents)))
    check("inventory join", set(raw_ids) == inventory_ids,
          f"missing={len(inventory_ids - set(raw_ids))}, outside={len(set(raw_ids) - inventory_ids)}")
    check("gold join", gold_ids == set(raw_ids),
          f"missing={len(gold_ids - set(raw_ids))}, outside={len(set(raw_ids) - gold_ids)}")
    check("pair join", raw_pairs == inventory_pairs,
          f"raw_only={len(raw_pairs - inventory_pairs)}, inventory_only={len(inventory_pairs - raw_pairs)}")
    check("inventory membership uniqueness", len(inventory_memberships) == len(inventory_mapping) == 1697,
          f"memberships={len(inventory_memberships)}, unique={len(inventory_mapping)}")
    check("gold ID uniqueness", len(gold_rows) == len(gold_mapping) == 1697,
          f"rows={len(gold_rows)}, unique={len(gold_mapping)}")
    check("inventory keyed mapping", raw_mapping == inventory_mapping, "source_unit_id -> pair")
    check("gold keyed mapping", raw_mapping == gold_mapping, "source_unit_id -> pair")
    check("per-pair counts", raw_pair_counts == inventory_pair_counts == gold_pair_counts,
          "raw == inventory == gold")
    check("labels", dict(labels) == EXPECTED_LABELS, json.dumps(dict(labels), sort_keys=True))
    check("positive/direct cases", len(direct_cases) == 9, str(len(direct_cases)))
    check("zero-direct cases", len(raw_pairs) - len(direct_cases) == 11,
          str(len(raw_pairs) - len(direct_cases)))

    document_provenance = provenance["documents"]
    check("document provenance coverage", len(document_provenance) == 20,
          str(len(document_provenance)))
    provenance_by_id = {row["document_id"]: row for row in document_provenance}
    provenance_matches = True
    for row in inventory_rows:
        observed = provenance_by_id.get(row["document_id"])
        payload = row["pmc_payload_hash"] if row["source_type"] == "PMC_FULLTEXT" else row["pubmed_payload_hash"]
        expected = {
            "document_id": row["document_id"],
            "payload_sha256": payload,
            "parser": row["parser_versions"][0],
            "source_unit_count": row["source_unit_count"],
        }
        provenance_matches &= observed == expected
    check("document provenance values", provenance_matches, "20/20 match inventory")
    check("document source counts", dict(source_types) == {
        "PUBMED_ABSTRACT": 12, "PMC_FULLTEXT": 8,
    } == manifest["structural_contract"]["document_sources"],
          json.dumps(dict(source_types), sort_keys=True))

    check("supplement identity",
          manifest["supplement_id"] == "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01",
          manifest["supplement_id"])
    check("classification", manifest["classification"] == "PRE_FINAL_DATASET_SUPPLEMENT",
          manifest["classification"])
    check("not frozen", manifest["frozen"] is False, str(manifest["frozen"]))
    check("review state", manifest["review_status"] == "READY_FOR_HUMAN_REVIEW",
          manifest["review_status"])
    check("no reconstruction claim",
          provenance["deterministic_reconstruction_from_original_versioned_artifacts"] is False,
          str(provenance["deterministic_reconstruction_from_original_versioned_artifacts"]))
    check("pre-final provenance", provenance["source_artifact_pre_final_provenance_verified"] is True,
          str(provenance["source_artifact_pre_final_provenance_verified"]))
    check("byte-identical claim", provenance["raw_source_copied_byte_identically"] is True,
          str(provenance["raw_source_copied_byte_identically"]))
    check("provenance identity", {
        "supplement_id": provenance["supplement_id"],
        "source_sha256": provenance["source_sha256"],
        "source_byte_size": provenance["source_byte_size"],
    } == {
        "supplement_id": "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01",
        "source_sha256": EXPECTED_RAW_SHA,
        "source_byte_size": EXPECTED_RAW_BYTES,
    }, "exact provenance identity")
    source_path = Path(provenance["source_path"])
    source_matches = (
        source_path.is_file()
        and source_path.stat().st_size == EXPECTED_RAW_BYTES
        and sha256_bytes(source_path) == EXPECTED_RAW_SHA
        and source_path.read_bytes() == RAW.read_bytes()
    )
    check("source binary equality at review", source_matches, str(source_path))
    expected_structure = manifest["structural_contract"]
    check("validation report identity", {
        "supplement_id": report["supplement_id"],
        "validation_mode": report["validation_mode"],
        "overall_status": report["overall_status"],
    } == {
        "supplement_id": "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01",
        "validation_mode": "READ_ONLY_DATA_VALIDATION_NO_SELECTOR_EXECUTION",
        "overall_status": "PASS",
    }, "exact report identity")
    check("validation report source", report["source_identity"] == {
        "exists": True, "sha256_expected": EXPECTED_RAW_SHA,
        "sha256_observed": EXPECTED_RAW_SHA, "bytes_expected": EXPECTED_RAW_BYTES,
        "bytes_observed": EXPECTED_RAW_BYTES, "pass": True,
    }, "exact observed source identity")
    check("validation report copy", report["copy_identity"] == {
        "sha256": EXPECTED_RAW_SHA, "bytes": EXPECTED_RAW_BYTES,
        "binary_equal_to_source": True, "pass": True,
    }, "exact observed copy identity")
    report_structure = dict(report["structure"])
    report_structure.pop("pass", None)
    check("validation report structure", report_structure == {
        key: value for key, value in expected_structure.items() if key != "document_sources"
    } and report["structure"]["pass"] is True, "matches manifest contract")
    check("validation report joins", report["joins"] == {
        "source_unit_ids_in_inventory": 1697,
        "inventory_source_unit_ids_missing_from_S01": 0,
        "S01_ids_outside_frozen_inventory": 0,
        "gold_source_unit_ids_missing_from_S01": 0,
        "S01_ids_outside_gold": 0,
        "candidate_document_pair_mismatch": 0,
        "pass": True,
    }, "exact join results")
    check("validation report document provenance", report["document_payload_provenance"] == {
        "covered": 20, "required": 20, "pass": True,
    }, "20/20")
    check("validation report mutations", report["data_mutations"] == {
        "source_unit_text": 0,
        "source_unit_id": 0,
        "label": 0,
        "candidate_mapping": 0,
        "document_mapping": 0,
    },
          json.dumps(report["data_mutations"], sort_keys=True))
    check("creation-phase attestation", report["creation_phase_attestation"] == {
        "evidence_basis": "commands executed during S01 preservation; not a persistent integrity invariant",
        "final_evaluation_directory_absent": True,
        "final_runtime_runs": 0,
        "selector_final_runs": 0,
        "Gemma_final_calls": 0,
        "Narrator_final_calls": 0,
        "network_final_calls": 0,
        "final_results_observed": False,
    }, "exact creation-phase attestation")
    check("parent SHA", parent["protocol_sha256"] == EXPECTED_PARENT_SHA, parent["protocol_sha256"])
    check("A01 SHA", a01["amendment_sha256"] == EXPECTED_A01_SHA, a01["amendment_sha256"])
    parent_valid, parent_recomputed = verify_embedded_seal(parent, REPO_ROOT, "protocol_sha256")
    a01_valid, a01_recomputed = verify_embedded_seal(
        a01, REPO_ROOT / "evaluation/final_protocol/amendments/A01", "amendment_sha256"
    )
    check("parent bytes recomputed", parent_valid and parent_recomputed == EXPECTED_PARENT_SHA,
          parent_recomputed)
    check("A01 bytes recomputed", a01_valid and a01_recomputed == EXPECTED_A01_SHA,
          a01_recomputed)
    check("manifest lineage", manifest["normative_identity"] == {
        "runtime_commit": EXPECTED_RUNTIME,
        "parent_protocol_sha256": EXPECTED_PARENT_SHA,
        "amendment_A01_sha256": EXPECTED_A01_SHA,
        "A01_freeze_commit": EXPECTED_A01_FREEZE,
    }, "exact normative identity")
    check("provenance commits", provenance["generator_commit"] == EXPECTED_GENERATOR_COMMIT
          and provenance["frozen_inventory_and_gold_commit"] == EXPECTED_INVENTORY_COMMIT,
          "exact commit identifiers")
    check("Git lineage objects", all((
        git_object_exists(f"{EXPECTED_RUNTIME}^{{commit}}"),
        git_object_exists(f"{EXPECTED_A01_FREEZE}^{{commit}}"),
        git_object_exists(f"{EXPECTED_GENERATOR_COMMIT}:mtb-graphrag/scripts/evaluate_independent_sourceunit_selector.py"),
        git_object_exists(f"{EXPECTED_INVENTORY_COMMIT}:mtb-graphrag/evaluation/sourceunit_selector_independent/document_inventory.jsonl"),
        git_object_exists(f"{EXPECTED_INVENTORY_COMMIT}:mtb-graphrag/evaluation/sourceunit_selector_independent/gold_annotations.csv"),
    )), "runtime, freeze, generator, inventory, and gold")
    inventory_spec = (
        f"{EXPECTED_INVENTORY_COMMIT}:mtb-graphrag/evaluation/"
        "sourceunit_selector_independent/document_inventory.jsonl"
    )
    gold_spec = (
        f"{EXPECTED_INVENTORY_COMMIT}:mtb-graphrag/evaluation/"
        "sourceunit_selector_independent/gold_annotations.csv"
    )
    check("frozen inventory blob", git_blob(inventory_spec) == INVENTORY.read_bytes(),
          EXPECTED_INVENTORY_COMMIT)
    check("frozen gold blob", git_blob(gold_spec) == GOLD.read_bytes(),
          EXPECTED_INVENTORY_COMMIT)
    check("normative files", tuple(seal["normative_files"]) == NORMATIVE_FILES,
          ",".join(seal["normative_files"]))
    package_hash, file_hashes = compute_package_hash(HERE)
    check("package file hashes", seal["files"] == file_hashes, "exact byte hashes")
    check("supplement SHA", seal["supplement_sha256"] == package_hash, package_hash)
    expected_seal_metadata = {
        "supplement_id": "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01",
        "classification": "PRE_FINAL_DATASET_SUPPLEMENT",
        "hash_algorithm": "sha256",
        "file_hash_rule": "sha256 over each file's exact bytes; no newline or encoding normalization",
        "supplement_hash_rule": "sha256 of sorted 'relative_name:sha256' lines joined by LF",
        "raw_source_sha256": EXPECTED_RAW_SHA,
        "frozen": False,
        "review_status": "READY_FOR_HUMAN_REVIEW",
    }
    check("seal metadata", all(seal.get(key) == value for key, value in expected_seal_metadata.items()),
          "all stable fields exact")
    expected_files = set(NORMATIVE_FILES) | {"supplement_hash.json"}
    observed_files = {path.name for path in HERE.iterdir() if path.is_file()}
    unexpected_dirs = {path.name for path in HERE.iterdir() if path.is_dir()}
    check("package file set", observed_files == expected_files and not unexpected_dirs,
          f"files={len(observed_files)}, extra_dirs={sorted(unexpected_dirs)}")
    return checks


def main() -> int:
    try:
        checks = validate()
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL | supplement incomplete or invalid | {exc}")
        return 1
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'} | {name} | {detail}")
    failed = sum(not passed for _, passed, _ in checks)
    print(f"SUMMARY | checks={len(checks)} | failed={failed}")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
