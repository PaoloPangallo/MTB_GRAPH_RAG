"""Fail-closed checker for the pre-freeze Protocol 1.4 amendment."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
P13 = "1e7f154ae6dff655937acb486226b88ac5baa556efaeb1a6a77d64d423399fa5"
OLD_RUNTIME = "3d2251f82a586535f79f3d0b3725c16330c365ba"
NEW_RUNTIME = "79867435acd59b830dae1d0fbab272c2bea2427b"
A01 = "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf"
S01 = "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15"

def load(name: str):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

def main() -> int:
    m, l, i, f = (load(n) for n in ("protocol_manifest.json", "lineage.json", "inherited_protocol_contract.json", "amendment_contract.json"))
    p13 = json.loads((ROOT / "evaluation/final_protocol_v1_3/protocol_hash.json").read_text(encoding="utf-8"))
    checks = []
    def add(name, ok): checks.append((name, bool(ok)))
    add("protocol version", m.get("protocol_version") == "1.4")
    add("accepted frozen review", m.get("review_status") == "ACCEPTED" and m.get("status") == "ACCEPTED" and m.get("frozen") is True and isinstance(m.get("freeze_timestamp"), str) and m.get("freeze_scope") == "FINAL_EVALUATION_PROTOCOL_1_4_FINAL_FREEZE")
    add("human review record", m.get("human_review") == {"reviewer":"Paolo Pangallo","review_date":"2026-08-11","review_verdict":"ACCEPTED","review_scope":"FINAL_EVALUATION_PROTOCOL_1_4_RUNTIME_INTERFACE_AMENDMENT"})
    add("parent 1.3 exact", m.get("parent_protocol_sha256") == P13 and l.get("parent_protocol_sha256") == P13 and p13.get("protocol_1_3_sha256") == P13)
    add("runtime lineage", l.get("runtime_previous") == OLD_RUNTIME and l.get("runtime_current") == NEW_RUNTIME and f.get("runtime_identity") == {"previous": OLD_RUNTIME, "current": NEW_RUNTIME})
    add("ancestor lineage", l.get("A01_sha256") == A01 and l.get("S01_package_sha256") == S01 and l.get("protocol_1_1_sha256") == "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889")
    add("D02-D16 inherited", len(i.get("inherited_decisions", {})) == 15 and all(v == "INHERITED_UNCHANGED_FROM_1_2" for v in i["inherited_decisions"].values()) and i.get("semantic_change_count_D02_D16") == 0)
    add("E01-E04 inherited", i.get("inherited_identity_decisions") == {"E01":"INHERITED_UNCHANGED_FROM_1_3","E02":"INHERITED_UNCHANGED_FROM_1_3","E03":"INHERITED_UNCHANGED_FROM_1_3","E04":"INHERITED_UNCHANGED_FROM_1_3"} and i.get("semantic_change_count_E01_E04") == 0)
    add("F01 scope", f.get("amendment_id") == "F01" and f.get("authorized_scope") == "NO_OTHER_RUNTIME_SEMANTIC_CHANGE")
    add("injection points", f.get("runtime_file") == "backend/research_pipeline/orchestrator.py" and set(f.get("injection_points", {})) == {"match_verifier_fn", "eligibility_gate_fn"})
    add("canonical defaults", f.get("canonical_defaults") == {"match_verifier":["verifier.verify_case_context","verifier.essential_fields_pass"],"eligibility_gate":["cc_pipeline.run","eligibility.gate.evaluate"]})
    d = f.get("d05", {})
    add("D05 unchanged", d.get("scientific_meaning") == "REMOVE_STAGE_3_MATCH_VERIFIER_AND_STAGE_3B_ELIGIBILITY_GATE_ONLY" and d.get("bypassed_stages") == ["3", "3b"])
    add("D05 parser/retrieval", d.get("parser_output_unchanged") is True and d.get("retrieval_input") == "ORIGINAL_PARSER_PRODUCED_CASECONTEXT" and d.get("downstream") == "SAME_CANONICAL_DOWNSTREAM_FROM_RETRIEVAL_ONWARD")
    add("no synthetic clinical state", all(d.get(k) is False for k in ("synthetic_match_true","synthetic_eligible_true","synthetic_eligibility_status","synthetic_positive_reason_codes","new_clinical_state")))
    add("model identity inherited", json.loads((ROOT / "evaluation/final_protocol_v1_3/model_identity_contract.json").read_text(encoding="utf-8")).get("effective_model") == "gemma4:31b-cloud")
    add("endpoint inherited", json.loads((ROOT / "evaluation/final_protocol_v1_3/model_identity_contract.json").read_text(encoding="utf-8")).get("endpoint") == "https://ollama.com/v1/chat/completions")
    add("generation inherited", (ROOT / "evaluation/final_protocol_v1_3/generation_configuration.json").is_file())
    add("provider policy inherited", (ROOT / "evaluation/final_protocol_v1_3/provider_metadata_contract.json").is_file())
    add("scientific plan", i.get("scientific_plan") == {"RQ1":1,"RQ2":80,"RQ3":5,"RQ4":70,"Narrative":25,"Operational":9,"Reliability":30,"Latency":2,"total":222} and i.get("scientific_projection_sha256") == "76bcb6f395aa4b8053ac19305d7404713aa6d0d53c6bce21a1f0f7b3e4971497")
    add("no new scientific decisions", all(i.get(k) == 0 for k in ("new_metrics","new_datasets","new_denominators","new_arms","new_evaluation_units","new_clinical_semantics")))
    add("canonical equivalence claim", f.get("canonical_equivalence_claim") == "CANONICAL_SEMANTIC_EQUIVALENCE_UNDER_DEFAULT_INJECTION")
    add("final results absent", not (ROOT / "evaluation/final_evaluation").exists())
    for name, ok in checks: print(("PASS" if ok else "FAIL") + " | " + name)
    print(f"SUMMARY {sum(ok for _, ok in checks)}/{len(checks)}")
    return 0 if all(ok for _, ok in checks) else 1

if __name__ == "__main__": raise SystemExit(main())
