"""Local, non-LLM, resumable G1.1 annotation CLI."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {"annotation_unit_id", "reviewer_id", "evaluable", "bucket", "source_checked", "source_available", "biomarker_match", "disease_scope_match", "intervention_match", "formulation_match", "direction_match", "regimen_or_aggregate_status", "separability_status", "applicability_status", "provenance_status", "uncertainty", "rationale_codes", "annotated_at", "annotation_protocol_version"}
BUCKETS = {"primary", "warning", "audit", "rejected", None}

def rows(path): return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
def append(path, value):
    with Path(path).open("a", encoding="utf-8", newline="\n") as h: h.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
def validate(response):
    missing=sorted(REQUIRED-set(response)); errors=[]
    if missing: errors.append("missing:"+",".join(missing))
    if response.get("annotation_protocol_version") != "G1.1": errors.append("wrong_protocol")
    if response.get("bucket") not in BUCKETS: errors.append("invalid_bucket")
    if response.get("evaluable") is False and response.get("bucket") is not None: errors.append("bucket_on_non_evaluable")
    if not isinstance(response.get("rationale_codes"), list): errors.append("rationale_codes_not_array")
    return errors

def main(argv=None):
    p=argparse.ArgumentParser(description="G1.1 local annotation tool; no network or LLM")
    p.add_argument("--packet", required=True); p.add_argument("--reviewer", required=True, choices=["reviewer_A","reviewer_B","adjudicator_C"]); p.add_argument("--output", required=True); p.add_argument("--audit-log", required=True); p.add_argument("--validate-only", action="store_true")
    a=p.parse_args(argv); packet=rows(a.packet); forbidden={"predicted_bucket","score","rank","reason_codes","gate_trace","gate_outcomes","system_id","run_id","run_key","output_path"}
    if any(forbidden & set(x) for x in packet): p.error("packet contains forbidden prediction/runtime fields")
    if a.validate_only: print(json.dumps({"packet_units":len(packet),"protocol":"G1.1","passed":True})); return 0
    done={x.get("annotation_unit_id") for x in rows(a.output)} if Path(a.output).exists() else set()
    for unit in packet:
        if unit["annotation_unit_id"] in done: continue
        print(json.dumps({"annotation_unit_id":unit["annotation_unit_id"],"query_id":unit["query_id"],"claim_tuple":unit["claim_tuple"],"source_context":unit["source_context"]},ensure_ascii=False))
        raw=input("response JSON (blank pauses): ").strip()
        if not raw: break
        response=json.loads(raw); response["reviewer_id"]=a.reviewer; response["annotation_unit_id"]=unit["annotation_unit_id"]; response.setdefault("annotated_at",datetime.now(timezone.utc).isoformat()); errors=validate(response)
        if errors: print("INVALID " + ";".join(errors)); continue
        append(a.output,response); append(a.audit_log,{"event":"annotation_saved","annotation_unit_id":unit["annotation_unit_id"],"reviewer_id":a.reviewer,"at":response["annotated_at"]})
    return 0
if __name__=="__main__": sys.exit(main())
