"""Build the Protocol 1.7.2 seal without executing evaluation units."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

os.environ["MTB_EVALUATION_PROTOCOL_VERSION"] = "1.7.2"

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ROOT = ROOT / "evaluation" / "final_protocol_v1_7_2"
sys.path.insert(0, str(ROOT))

from evaluation.final_evaluation_harness.common.identities import evaluation_id
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan, execution_plan_sha256


PLAN_PATH = PROTOCOL_ROOT / "sealed_execution_plan.json"
SEAL_PATH = PROTOCOL_ROOT / "seal_manifest.json"
SEAL_HASH_PATH = PROTOCOL_ROOT / "seal_manifest.sha256"
RUNTIME_COMMIT = "586bf27885c11173510a6bd0b93db3f3ac0f222a"
HARNESS_COMMIT = "3b0d326509d2a11fc69214b420074e4164ae354e"
OUTPUT_DIRECTORY = "evaluation/final_evaluation_v1_7_3"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def protocol_digest() -> str:
    manifest = json.loads((PROTOCOL_ROOT / "protocol_manifest.json").read_text(encoding="utf-8"))
    names = manifest["normative_files"]
    lines = [f"{name}:{digest(PROTOCOL_ROOT / name)}" for name in sorted(names)]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def main() -> None:
    runtime_commit = RUNTIME_COMMIT
    manifest_path = PROTOCOL_ROOT / "protocol_manifest.json"
    lineage_path = PROTOCOL_ROOT / "lineage.json"
    amendment_path = PROTOCOL_ROOT / "operational_amendment.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "protocol_version": "1.7.2",
        "protocol_id": "mtb-graphrag-final-evaluation/1.7.2",
        "evaluation_boundary": "FINAL_EVALUATION_1_7_2",
        "output_directory": OUTPUT_DIRECTORY,
        "runtime_commit": runtime_commit,
        "harness_commit": HARNESS_COMMIT,
        "evaluation_protocol_commit": HARNESS_COMMIT,
        "model_alias": "gemma4:31b-cloud",
        "review_status": "ACCEPTED",
        "frozen": True,
        "case1_document_support_level": "PARTIAL_SUPPORT",
        "case1_document_support_reason": "The paper supports KRAS mutations generally, not specifically KRAS G12D.",
        "support_levels": ["STRONG_SUPPORT", "PARTIAL_SUPPORT", "CONTEXT_ONLY", "CONTRADICTORY", "UNVERIFIABLE"],
        "unit_membership_unchanged": True,
        "development_units": 35,
        "heldout_units": 35,
        "total_units": 222,
    })
    write_json(manifest_path, manifest)
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage.update({"runtime_commit": runtime_commit, "harness_commit": HARNESS_COMMIT, "protocol_version": "1.7.2"})
    write_json(lineage_path, lineage)
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    amendment.update({"runtime_commit": runtime_commit, "harness_commit": HARNESS_COMMIT, "evaluation_output_directory": OUTPUT_DIRECTORY})
    write_json(amendment_path, amendment)
    from backend.research_pipeline.casecontext import prompt as case_prompt
    from backend.research_pipeline.enrichment import prompt_v2 as paper_prompt
    from backend.research_pipeline.narrative import prompt as narrator_prompt
    narrator_hash = hashlib.sha256(json.dumps({
        "version": narrator_prompt.NARRATOR_PROMPT_VERSION,
        "system": narrator_prompt.SYSTEM_PROMPT,
        "schema": narrator_prompt.TOOL_SCHEMA,
        "language": narrator_prompt.NARRATIVE_LANGUAGE,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    write_json(PROTOCOL_ROOT / "prompt_identity.json", {"roles": {
        "case_context_parser": {"prompt_version": case_prompt.PROMPT_VERSION, "prompt_sha256": case_prompt.prompt_hash()},
        "paper_context_enricher": {"prompt_version": paper_prompt.PROMPT_VERSION, "prompt_sha256": paper_prompt.prompt_hash()},
        "dossier_narrator": {"prompt_version": narrator_prompt.NARRATOR_PROMPT_VERSION, "prompt_sha256": narrator_hash},
    }})
    manifest["prompt_identity_path"] = "prompt_identity.json"
    manifest["prompt_identity_sha256"] = digest(PROTOCOL_ROOT / "prompt_identity.json")
    normative_files = list(manifest.get("normative_files", []))
    if "prompt_identity.json" not in normative_files:
        normative_files.append("prompt_identity.json")
    manifest["normative_files"] = normative_files
    write_json(manifest_path, manifest)
    initial_protocol_sha = protocol_digest()
    write_json(PROTOCOL_ROOT / "protocol_hash.json", {
        "protocol_version": "1.7.2",
        "parent_protocol_sha256": manifest["parent_protocol_sha256"],
        "protocol_sha256": initial_protocol_sha,
        "protocol_sha256_repeat": initial_protocol_sha,
    })
    protocol = load_protocol(ROOT)
    plans = build_full_plan(protocol)
    if len(plans) != 222:
        raise RuntimeError(f"SEALED_PLAN_UNIT_COUNT_MISMATCH:{len(plans)}")
    serialized_plan = [plan.__dict__ for plan in plans]
    plan_sha = execution_plan_sha256(plans)
    PLAN_PATH.write_text(
        json.dumps(serialized_plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    if digest(PLAN_PATH) != plan_sha:
        raise RuntimeError("SEALED_PLAN_SERIALIZATION_MISMATCH")

    manifest = json.loads((PROTOCOL_ROOT / "protocol_manifest.json").read_text(encoding="utf-8"))
    manifest["sealed_plan_sha256"] = plan_sha
    write_json(PROTOCOL_ROOT / "protocol_manifest.json", manifest)
    psha = protocol_digest()
    seal_hash = json.loads((PROTOCOL_ROOT / "protocol_hash.json").read_text(encoding="utf-8"))
    seal_hash["protocol_sha256"] = psha
    seal_hash["protocol_sha256_repeat"] = psha
    write_json(PROTOCOL_ROOT / "protocol_hash.json", seal_hash)

    protocol = load_protocol(ROOT)
    plans_again = build_full_plan(protocol)
    plan_sha_again = execution_plan_sha256(plans_again)
    if plan_sha_again != plan_sha or [p.__dict__ for p in plans_again] != serialized_plan:
        raise RuntimeError("SEALED_PLAN_NONDETERMINISTIC")
    final_id = evaluation_id(protocol, protocol.hashes["runtime_commit"])
    seal = {
        "protocol_version": "1.7.2",
        "boundary": "FINAL_EVALUATION_1_7_2",
        "evaluation_id": final_id,
        "canonical_runtime_commit": protocol.hashes["runtime_commit"],
        "harness_commit": HARNESS_COMMIT,
        "gca_sha256": manifest["gca_sha256"],
        "benchmark_path": manifest["benchmark_path"],
        "benchmark_sha256": manifest["benchmark_sha256"],
        "gold_path": manifest["gold_path"],
        "gold_sha256": manifest["gold_sha256"],
        "sealed_plan_sha256": plan_sha,
        "closure_policy": "WHOLE_GCA",
        "closure_identifier_count": 6375,
        "closure_manifest_path": manifest["closure_manifest_path"],
        "closure_manifest_sha256": manifest["closure_manifest_sha256"],
        "frozen_document_manifest_path": manifest["frozen_document_manifest_path"],
        "frozen_document_manifest_sha256": manifest["frozen_document_manifest_sha256"],
        "sourceunit_index_path": manifest["frozen_source_unit_index_path"],
        "sourceunit_index_sha256": manifest["frozen_source_unit_index_sha256"],
        "acquisition_ledger_path": manifest["frozen_acquisition_ledger_path"],
        "acquisition_ledger_sha256": manifest["frozen_acquisition_ledger_sha256"],
        "document_network_allowed": False,
        "document_transport_policy": "OFFLINE_FROZEN_TRANSPORT_ONLY",
        "model_identity": {
            "provider": "OLLAMA_CLOUD",
            "model": "gemma4:31b-cloud",
            "model_config_sha256": manifest["model_config_sha256"],
            "model_identity_sha256": manifest["model_identity_sha256"],
        },
        "prompt_identity_sha256": manifest["prompt_identity_sha256"],
        "deterministic_configuration": {
            "retrieval_and_selection": "frozen runtime commit",
            "generation_configuration_sha256": manifest["model_config_sha256"],
            "document_obligation": manifest["document_obligation"],
        },
        "total_units": 222,
        "unit_composition": {"RQ1": 1, "RQ2": 80, "RQ3": 5, "RQ4": 70, "Narrative": 25, "Operational": 9, "Reliability": 30, "Latency": 2},
        "document_obligation": manifest["document_obligation"],
        "frozen_coverage_complete": True,
        "gold_leakage": False,
        "output_directory": manifest["output_directory"],
        "full_evaluation_executed": False,
        "real_evaluation_units_executed": 0,
    }
    write_json(SEAL_PATH, seal)
    SEAL_HASH_PATH.write_text(digest(SEAL_PATH) + "  seal_manifest.json\n", encoding="utf-8", newline="\n")
    sealed_plan_manifest = {
        "protocol_version": "1.7.2",
        "runtime_commit": protocol.hashes["runtime_commit"],
        "harness_commit": HARNESS_COMMIT,
        "protocol_sha256": protocol.hashes["protocol_sha256"],
        "boundary": "FINAL_EVALUATION_1_7_2",
        "plan_builder": "evaluation.final_evaluation_harness.common.runner.build_full_plan",
        "planned_units": 222,
        "plan_sha256": plan_sha,
        "evaluation_id": final_id,
        "output_directory": manifest["output_directory"],
        "document_transport_policy": "OFFLINE_FROZEN_TRANSPORT_ONLY",
        "frozen_document_manifest": manifest["frozen_document_manifest_path"],
        "frozen_document_manifest_sha256": manifest["frozen_document_manifest_sha256"],
        "closure_manifest_sha256": manifest["closure_manifest_sha256"],
        "sourceunit_index_sha256": manifest["frozen_source_unit_index_sha256"],
        "full_evaluation_executed": False,
    }
    write_json(PROTOCOL_ROOT / "sealed_plan_manifest.json", sealed_plan_manifest)
    print(json.dumps({"protocol_sha256": protocol.hashes["protocol_sha256"], "plan_sha256": plan_sha, "evaluation_id": final_id, "seal_manifest_sha256": digest(SEAL_PATH), "planned_units": 222}, sort_keys=True))


if __name__ == "__main__":
    main()
