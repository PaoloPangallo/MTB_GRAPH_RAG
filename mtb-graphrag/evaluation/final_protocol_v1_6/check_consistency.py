from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent

def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def main() -> int:
    manifest = load("protocol_manifest.json")
    amendment = load("amendment_contract.json")
    inherited = load("inherited_protocol_contract.json")
    projection = load("scientific_projection.json")
    corpus = load("corpus_identity.json")
    lineage = load("lineage.json")
    protocol_hash = load("protocol_hash.json")
    h01 = load("../final_protocol_v1_6_candidates/rq4/review_report.json")
    checks = {
        "version": manifest["protocol_version"] == "1.6",
        "pre_freeze": manifest["frozen"] is False and manifest["review_status"] == "PENDING_REVIEW" and manifest["reviewer"] is None,
        "parent": manifest["parent_protocol_commit"] == "556618f8810333d1abad3771e42c4626e54d3670" and manifest["parent_protocol_sha256"] == "60b74a031688161690b34a8ed6dda7f4b36ca7323541bbd1564b0ad816fe3bdd",
        "h01_identity": amendment["H01"]["normative_sha256"] == "b98d0ac2f8cc596ef87ed35e18fceb3291106c213e12b3d007103e463f7d11d4" and h01["normative_sha256"] == amendment["H01"]["normative_sha256"],
        "h02_identity": amendment["H02"]["runtime_commit"] == "eb20fdfab35724f3b84651d8c02f1ec3970db615" and manifest["runtime_commit"] == amendment["H02"]["runtime_commit"],
        "counts": projection["counts"] == manifest["scientific_plan"] == inherited["scientific_plan"],
        "unit_membership": projection["unit_membership_unchanged"] and projection["units_unchanged"] == 222 and projection["units_changed"] == 0,
        "h01_raw": amendment["H01"]["raw_path_count"] == amendment["H01"]["valid_raw_path_count"] == 14 and amendment["H01"]["invalid_raw_path_count"] == 0,
        "h01_hard": amendment["H01"]["hard_observables_executable"] == "5/5" and amendment["H01"]["precomputed_scientific_booleans"] == 0 and amendment["H01"]["prose_executable_clauses"] == 0,
        "g02": amendment["G02"] == "INHERITED_UNCHANGED" and projection["narrative_G02"] == "INHERITED_UNCHANGED",
        "corpora": corpus["source_artifacts_modified"] is False and corpus["narrative_hostile_count"] == 20 and corpus["narrative_controls_count"] == 5,
        "h01_lineage": lineage["H01_normative_sha256"] == amendment["H01"]["normative_sha256"],
        "projection_parent": projection["parent_projection_sha256"] == "4be62db090f9fa0c05c0369008cc267af0e6c1132ccee9cc09705542237f78d0",
        "projection_identity": manifest["scientific_projection_sha256"] == lineage["scientific_projection_sha256"] == "a4edb0bad5cd233fe04423068dacf14de91bb7a7421169c5602c7bf79e67229c",
        "rq3_metadata_only": projection["authorized_changes"]["RQ3"] == ["H02 reviewed runtime identity/interface metadata only"],
        "no_scope_expansion": projection["unauthorized_scientific_changes"] == 0,
        "pre_freeze_hash": protocol_hash["pre_freeze"] is True and protocol_hash["protocol_sha256"] == protocol_hash["protocol_sha256_repeat"] and len(protocol_hash["protocol_sha256"]) == 64,
        "final_eval_absent": not (ROOT.parents[1] / "final_evaluation").exists(),
    }
    result = {"checks": checks, "passed": sum(checks.values()), "total": len(checks), "all_pass": all(checks.values())}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
