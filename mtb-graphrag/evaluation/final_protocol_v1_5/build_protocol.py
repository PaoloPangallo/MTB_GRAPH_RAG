"""Create the Protocol 1.5 pre-freeze candidate artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = ROOT / "evaluation" / "final_protocol_v1_5_candidates"
OUT = HERE


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def write_json(name, value):
    (OUT / name).write_bytes(canonical(value))


def main():
    hostile_manifest = json.loads((CANDIDATE / "narrative/hostile_manifest.json").read_text(encoding="utf-8"))
    controls_manifest = json.loads((CANDIDATE / "narrative/controls_manifest.json").read_text(encoding="utf-8"))
    authority_mapping = json.loads((CANDIDATE / "narrative/authority_mapping.json").read_text(encoding="utf-8"))
    g01 = json.loads((CANDIDATE / "rq4/heldout_evaluator_contract.json").read_text(encoding="utf-8"))

    counts = {"RQ1": 1, "RQ2": 80, "RQ3": 5, "RQ4": 70, "Narrative": 25, "Operational": 9, "Reliability": 30, "Latency": 2, "total": 222}
    projection = {
        "projection_version": "scientific-projection/1.5",
        "parent_projection_sha256": "76bcb6f395aa4b8053ac19305d7404713aa6d0d53c6bce21a1f0f7b3e4971497",
        "counts": counts,
        "non_narrative_units_changed": 0,
        "narrative_units_changed": 25,
        "narrative_split": {"hostile": 20, "controls": 5},
        "authorized_narrative_field_changes": {
            "hostile_execution_class": "NARRATIVE_VERIFIER_ROBUSTNESS",
            "hostile_narrator_requirement": "PROHIBITED",
            "hostile_narrative_verifier_requirement": "REQUIRED",
            "hostile_candidate_narrative": "FROZEN_PREMATERIALIZED_CORPUS",
            "controls_execution_class": "LIVE_NARRATOR_PLUS_VERIFIER_FIDELITY_CONTROL",
            "controls_narrator_requirement": "REQUIRED",
            "controls_narrative_verifier_requirement": "REQUIRED",
            "controls_candidate_narrative": "LIVE_OUTPUT",
            "primary_metrics": "SEPARATE_H_AND_C_STRATA_NO_POOLED_PRIMARY",
        },
        "unchanged": ["case_ids", "arms", "ordering", "metrics_non_narrative", "denominators", "dataset_identities", "gold_identities"],
    }
    projection_sha = digest(projection)
    corpus_identity = {
        "candidate_corpus_source_commit": "5a2012f6aa3780059ad6e1585ee8424b65d7503e",
        "candidate_corpus_integration_commit": "b637223c4001c73c2dd084e316fdb5274e533d55",
        "hostile_corpus_sha256": "f586f6ea394a41107c643eb2a234747566f2115647b6aec203ef498d8673059c",
        "controls_corpus_sha256": "d2dc257e2dbf67a979fb933e1dd12c38a5bc48f0a9fe51eba08330dda3047ca9",
        "authority_mapping_sha256": "fd627471c6110bc873d47b73087985878c511b6d228bd28ff3d2ccb3c4be174b",
        "hostile_manifest_relative_path": "evaluation/final_protocol_v1_5_candidates/narrative/hostile_manifest.json",
        "controls_manifest_relative_path": "evaluation/final_protocol_v1_5_candidates/narrative/controls_manifest.json",
        "authority_mapping_relative_path": "evaluation/final_protocol_v1_5_candidates/narrative/authority_mapping.json",
        "hostile_case_count": 20,
        "control_case_count": 5,
    }
    inherited = {
        "source_protocol_id": "mtb-graphrag-final-evaluation/1.4",
        "source_protocol_sha256": "6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e",
        "inherited_decisions": {f"D{i:02d}": "INHERITED_UNCHANGED_FROM_1_4" for i in range(2, 17)},
        "inherited_identity_decisions": {f"E{i:02d}": "INHERITED_UNCHANGED_FROM_1_4" for i in range(1, 5)},
        "F01": "INHERITED_UNCHANGED_FROM_1_4",
        "semantic_change_count_D02_D16": 0,
        "semantic_change_count_E01_E04": 0,
        "scientific_plan": counts,
        "parent_scientific_projection_sha256": projection["parent_projection_sha256"],
        "new_metrics": 0, "new_datasets": 0, "new_denominators": 0, "new_arms": 0,
        "new_evaluation_units": 0, "new_clinical_semantics": 0,
    }
    amendment = {
        "amendment_id": "G01_G02",
        "classification": "AUTHORIZED_PRE_EXECUTION_METHODOLOGICAL_AMENDMENT",
        "G01": g01,
        "G02": {
            "contract": "NARRATIVE_TWO_STRATUM_CONTRACT",
            "hostile": {"n": 20, "narrator": "PROHIBITED", "verifier": "REQUIRED", "upstream": "PROHIBITED", "primary": ["verifier_rejection_success", "structured_fallback_success"], "corpus_sha256": corpus_identity["hostile_corpus_sha256"]},
            "controls": {"n": 5, "narrator": "REQUIRED", "verifier": "REQUIRED", "upstream": "PROHIBITED", "primary": ["verifier_acceptance", "structured_fallback_behavior"], "corpus_sha256": corpus_identity["controls_corpus_sha256"]},
            "authority_mapping_sha256": corpus_identity["authority_mapping_sha256"],
            "pooled_primary_metric": False,
            "gold_firewall": True,
            "hostile_candidate_narrative_is_only_mutated_object": True,
            "controls_candidate_narrative": "LIVE_OUTPUT_NOT_PREAUTHORED",
            "new_scientific_decision": True,
        },
    }
    lineage = {
        "parent_protocol_version": "1.4",
        "parent_protocol_freeze_commit": "87b61df186b16de94834b9365fb6de334b034a84",
        "parent_protocol_sha256": "6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e",
        "candidate_corpus_source_commit": corpus_identity["candidate_corpus_source_commit"],
        "candidate_corpus_integration_commit": corpus_identity["candidate_corpus_integration_commit"],
        "runtime_sha256": "79867435acd59b830dae1d0fbab272c2bea2427b",
        "G01_artifact_sha256": digest(g01),
        "hostile_corpus_sha256": corpus_identity["hostile_corpus_sha256"],
        "controls_corpus_sha256": corpus_identity["controls_corpus_sha256"],
        "authority_mapping_sha256": corpus_identity["authority_mapping_sha256"],
        "parent_scientific_projection_sha256": projection["parent_projection_sha256"],
        "scientific_projection_sha256": projection_sha,
    }
    manifest = {
        "protocol_id": "mtb-graphrag-final-evaluation/1.5",
        "protocol_version": "1.5",
        "status": "PRE_FREEZE_CANDIDATE",
        "review_status": "PENDING_REVIEW",
        "frozen": False,
        "parent_protocol_id": "mtb-graphrag-final-evaluation/1.4",
        "parent_protocol_sha256": lineage["parent_protocol_sha256"],
        "runtime_commit": lineage["runtime_sha256"],
        "scientific_projection_sha256": projection_sha,
        "scientific_plan": counts,
        "normative_files": ["protocol_manifest.json", "lineage.json", "inherited_protocol_contract.json", "amendment_contract.json", "corpus_identity.json", "scientific_projection.json"],
        "final_runs_executed_before_v1_5": False,
        "pre_freeze_only": True,
    }
    write_json("scientific_projection.json", projection)
    write_json("corpus_identity.json", corpus_identity)
    write_json("inherited_protocol_contract.json", inherited)
    write_json("amendment_contract.json", amendment)
    write_json("lineage.json", lineage)
    write_json("protocol_manifest.json", manifest)

    md = f'''# Final Evaluation Protocol 1.5 — Pre-Freeze Candidate\n\nThis candidate inherits Protocol 1.4 (`{lineage["parent_protocol_sha256"]}`) and runtime `{lineage["runtime_sha256"]}`.\n\n## Authorized amendment\n\n- G01: recovered RQ4 held-out inference/evaluation separation.\n- G02: two-stratum Narrative contract: 20 hostile verifier-only cases and 5 live Narrator+Verifier controls.\n\nAll other D02–D16, E01–E04 and F01 decisions remain inherited and unchanged.\n\nScientific units remain 222. Parent projection: `{projection["parent_projection_sha256"]}`. Candidate projection: `{projection_sha}`.\n\nStatus: `frozen=false`, `review_status=PENDING_REVIEW`.\n'''
    (ROOT / "docs" / "final_evaluation" / "v1_5").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "final_evaluation" / "v1_5" / "final_evaluation_protocol_1_5.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
