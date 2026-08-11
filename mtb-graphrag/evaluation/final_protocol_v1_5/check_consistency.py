"""Deterministic pre-freeze checker for Protocol 1.5."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
P14 = "6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e"
RUNTIME = "79867435acd59b830dae1d0fbab272c2bea2427b"
HOSTILE = "f586f6ea394a41107c643eb2a234747566f2115647b6aec203ef498d8673059c"
CONTROLS = "d2dc257e2dbf67a979fb933e1dd12c38a5bc48f0a9fe51eba08330dda3047ca9"
MAPPING = "fd627471c6110bc873d47b73087985878c511b6d228bd28ff3d2ccb3c4be174b"

def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))

def main() -> int:
    m, l, i, a, c, p = (load(n) for n in ("protocol_manifest.json","lineage.json","inherited_protocol_contract.json","amendment_contract.json","corpus_identity.json","scientific_projection.json"))
    checks = []
    def add(name, ok): checks.append((name, bool(ok)))
    add("version and pre-freeze", m.get("protocol_version")=="1.5" and m.get("frozen") is False and m.get("review_status")=="PENDING_REVIEW")
    add("parent exact", m.get("parent_protocol_sha256")==P14 and l.get("parent_protocol_sha256")==P14)
    add("runtime exact", m.get("runtime_commit")==RUNTIME and l.get("runtime_sha256")==RUNTIME)
    add("lineage freeze commit", l.get("parent_protocol_freeze_commit")=="87b61df186b16de94834b9365fb6de334b034a84")
    add("candidate corpus lineage", l.get("candidate_corpus_commit")=="5a2012f6aa3780059ad6e1585ee8424b65d7503e")
    add("corpus identities", c.get("hostile_corpus_sha256")==HOSTILE and c.get("controls_corpus_sha256")==CONTROLS and c.get("authority_mapping_sha256")==MAPPING)
    add("G01", a.get("G01",{}).get("contract_id")=="G01" and a.get("G01",{}).get("inference",{}).get("gold_access")=="PROHIBITED" and a.get("G01",{}).get("adversarial",{}).get("expected_retrieval_allowed") is None)
    g2=a.get("G02",{}); h=g2.get("hostile",{}); ctrl=g2.get("controls",{})
    add("G02 split", g2.get("contract")=="NARRATIVE_TWO_STRATUM_CONTRACT" and h.get("n")==20 and ctrl.get("n")==5 and g2.get("pooled_primary_metric") is False)
    add("G02 requirements", h.get("narrator")=="PROHIBITED" and h.get("verifier")=="REQUIRED" and ctrl.get("narrator")=="REQUIRED" and ctrl.get("verifier")=="REQUIRED")
    add("inherited D02-D16", len(i.get("inherited_decisions",{}))==15 and all(v=="INHERITED_UNCHANGED_FROM_1_4" for v in i["inherited_decisions"].values()))
    add("inherited E01-E04/F01", len(i.get("inherited_identity_decisions",{}))==4 and i.get("F01")=="INHERITED_UNCHANGED_FROM_1_4")
    add("plan counts", p.get("counts")=={"RQ1":1,"RQ2":80,"RQ3":5,"RQ4":70,"Narrative":25,"Operational":9,"Reliability":30,"Latency":2,"total":222})
    add("projection diff scope", p.get("non_narrative_units_changed")==0 and p.get("narrative_units_changed")==25 and len(p.get("authorized_narrative_field_changes",{}))==9)
    add("dataset identity unchanged", i.get("new_datasets")==0 and i.get("new_denominators")==0 and i.get("new_arms")==0 and i.get("new_evaluation_units")==0)
    add("runtime no amendment", i.get("F01")=="INHERITED_UNCHANGED_FROM_1_4")
    add("G01/G02 source artifacts", Path(c["hostile_manifest_relative_path"]).is_relative_to(Path("evaluation")) and Path(c["controls_manifest_relative_path"]).is_relative_to(Path("evaluation")))
    add("final evaluation absent", not (ROOT/"evaluation/final_evaluation").exists())
    for name, ok in checks: print(("PASS" if ok else "FAIL")+" | "+name)
    print(f"SUMMARY {sum(ok for _,ok in checks)}/{len(checks)}")
    return 0 if all(ok for _,ok in checks) else 1
if __name__ == "__main__": raise SystemExit(main())
