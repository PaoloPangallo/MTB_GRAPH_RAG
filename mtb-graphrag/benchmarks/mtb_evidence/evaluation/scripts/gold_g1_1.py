"""Prepare the G1.1 active-claim blind annotation universe."""
from __future__ import annotations
import argparse, csv, hashlib, json, random, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "benchmarks/mtb_evidence/final_experiment/official_runs/structured_v1_6"
CORPUS = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
PROTOCOL = ROOT / "benchmarks/mtb_evidence/final_experiment/v1_6"
DEST = ROOT / "benchmarks/mtb_evidence/final_experiment/gold_g1_1"
SEED = 20260801
FORBIDDEN = {"predicted_bucket", "bucket_prediction", "score", "rank", "reason_codes", "gate_trace", "gate_outcomes", "gate_outcome", "status_gate_prediction", "system_id", "run_id", "run_key", "output_path", "original_position", "semantic_hash", "normalized_semantic_sha256"}

def load_jsonl(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def dump(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".jsonl":
        path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for x in value), encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def queries(): return {x["query_id"]: x for x in load_jsonl(PROTOCOL / "all_queries_v1_6.jsonl")}

def corpus():
    out = {}
    for name in ("therapeutic_claims.jsonl", "diagnostic_claims.jsonl", "prognostic_claims.jsonl"):
        for x in load_jsonl(CORPUS / name): out[x["claim_id"]] = x
    return out

def active_payloads():
    out = {}
    for p in (OUTPUT / "run_manifests").glob("*.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m.get("replica") == 1 and m.get("status") == "complete":
            out[m["query_id"]] = json.loads((OUTPUT / "raw_results" / Path(m["raw_output"]).name).read_text(encoding="utf-8"))["result"]["payload"]
    return out

def candidates(payload):
    out = []
    for section in ("primary_ranked_results", "retained_with_warning", "audit_only_results", "rejected_by_native_constraints"):
        out.extend(payload.get(section, []))
    return out

def kind(x, active):
    cid = x.get("claim_id")
    if cid in active: return "claim"
    if cid and cid.startswith("GEP-"): return "provenance_container"
    if cid and cid.startswith("UNR-"): return "unresolved_association"
    if cid and cid.startswith("UNS-"): return "unsupported_association"
    if cid and cid.startswith("CLM-"): return "deprecated_claim"
    return "unknown"

def context(x, c):
    p = c.get("provenance") or x.get("provenance") or {}
    return {"source_unit_ids": c.get("source_unit_ids", []), "locators": c.get("locators", p.get("locators", [])), "source_ids": p.get("source_ids", []), "pmid": p.get("pmid"), "doi": p.get("doi"), "nct": p.get("nct")}

def unit(q, x, c, n):
    cid=x["claim_id"]
    return {"annotation_unit_id": f"G1.1-{q['query_id']}-{cid}", "query_id": q["query_id"], "query_structured": q.get("query", {}), "claim_id": cid, "claim_tuple": {"subject": c.get("canonical_subject", c.get("subject", c.get("biomarker"))), "relation": c.get("relation", c.get("claim_type")), "object": c.get("object", c.get("canonical_intervention", c.get("intervention"))), "domain": c.get("claim_domain"), "biomarker": c.get("biomarker"), "disease": c.get("disease_scope"), "intervention": c.get("canonical_intervention", c.get("intervention")), "direction": c.get("direction"), "qualifiers": c.get("warnings", [])}, "source_context": context(x,c), "annotation_protocol_version":"G1.1", "annotation_status":"pending"}

def audit():
    qs, active, payloads = queries(), corpus(), active_payloads(); active_ids=set(active); units=[]; excluded=[]; deprecated=[]; containers=[]; unresolved=[]; unsupported=[]; per=[]
    for qid in sorted(qs):
        rows=candidates(payloads[qid]); ids=[x.get("claim_id") for x in rows if x.get("claim_id")]; counts=Counter(kind(x,active) for x in rows); active_out={i for i in ids if i in active}; duplicates=sorted(i for i,n in Counter(ids).items() if n>1); missing=sorted(active_ids-active_out); extra=sorted(active_out-active_ids)
        for x in rows:
            k=kind(x,active); record={"query_id":qid,"record_id":x.get("claim_id"),"candidate_kind":k,"status": "active" if k=="claim" else k,"parent_id":x.get("parent_id"),"graph_evidence_id":x.get("graph_evidence_id")}
            if k=="claim": units.append(unit(qs[qid],x,active[x["claim_id"]],len(units)))
            else:
                reason={"deprecated_claim":"DEPRECATED_OUTSIDE_ACTIVE_CORPUS","provenance_container":"PROVENANCE_CONTAINER_NOT_CLAIM","unresolved_association":"UNRESOLVED_ASSOCIATION_NOT_QUALIFIED_CLAIM","unsupported_association":"UNSUPPORTED_ASSOCIATION_NOT_QUALIFIED_CLAIM"}.get(k,"UNKNOWN_NON_CLAIM_RECORD")
                record["primary_gold_evaluable"]=False; record["exclusion_reason"]=reason; record["sealed_predicted_bucket"]=x.get("bucket"); record["sealed_status_gate_outcome"]=x.get("gate"); record["sealed_reason_codes"]=x.get("reason_codes", []); record["source_status"]=(x.get("provenance") or {}).get("qualification_status"); excluded.append(record)
                {"deprecated_claim":deprecated,"provenance_container":containers,"unresolved_association":unresolved,"unsupported_association":unsupported}.get(k,[]).append(record)
        per.append({"query_id":qid,"benchmark_id":qs[qid]["benchmark_id"],"active_corpus_claims":len(active_ids),"active_output_claims":len(active_out),"active_claims_missing":missing,"active_claims_extra":sorted(extra),"duplicate_active_claim_ids":[i for i in duplicates if i in active_ids],"candidate_total":len(rows),"deprecated_claim_count":counts["deprecated_claim"],"provenance_container_count":counts["provenance_container"],"unresolved_association_count":counts["unresolved_association"],"unsupported_association_count":counts["unsupported_association"],"active_claim_universe_complete":not missing and not extra and not any(i in active_ids for i in duplicates)})
    report={"schema_version":"candidate-universe-audit/1.1","gold_protocol_version":"G1.1","generated_at":datetime.now(timezone.utc).isoformat(),"active_corpus_claim_count":len(active_ids),"query_count":len(per),"active_annotation_unit_count":len(units),"excluded_unit_count":len(excluded),"active_claim_universe_complete":all(x["active_claim_universe_complete"] for x in per),"candidate_universe_complete":all(x["active_claim_universe_complete"] for x in per),"queries":per,"counts":{"deprecated":len(deprecated),"provenance_container":len(containers),"unresolved":len(unresolved),"unsupported":len(unsupported)}}
    dump(DEST/"candidate_universe_audit_g1_1.json",report); dump(DEST/"excluded_annotation_units_g1_1.jsonl",excluded); dump(DEST/"deprecated_claim_audit_g1_1.jsonl",deprecated); dump(DEST/"provenance_container_audit_g1_1.jsonl",containers); dump(DEST/"unresolved_association_audit_g1_1.jsonl",unresolved); dump(DEST/"unsupported_association_audit_g1_1.jsonl",unsupported)
    with (DEST/"candidate_universe_audit_g1_1.csv").open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=["query_id","benchmark_id","active_corpus_claims","active_output_claims","active_claims_missing","active_claims_extra","duplicate_active_claim_ids","candidate_total","deprecated_claim_count","provenance_container_count","unresolved_association_count","unsupported_association_count","active_claim_universe_complete"]); w.writeheader(); w.writerows(per)
    return report,units,excluded

def keys(v):
    if isinstance(v,dict): return set(v)|set().union(*(keys(x) for x in v.values()))
    if isinstance(v,list): return set().union(*(keys(x) for x in v)) if v else set()
    return set()

def packet_validate(path):
    rows=load_jsonl(path); leaks=[]
    for x in rows: leaks += sorted(keys(x)&FORBIDDEN)
    return {"packet":path.name,"unit_count":len(rows),"blinding_leak_count":len(leaks),"leaked_fields":sorted(set(leaks)),"passed":not leaks}

def build():
    report, units, excluded=audit()
    if not report["active_claim_universe_complete"]: return
    a=list(units); b=list(units); r=random.Random(SEED); r.shuffle(a); r.shuffle(b)
    dump(DEST/"annotation_packet_A_g1_1.jsonl",a); dump(DEST/"annotation_packet_B_g1_1.jsonl",b)
    dump(DEST/"annotation_unit_mapping_g1_1.json",{"schema_version":"sealed-annotation-mapping/1.1","randomization_seed":SEED,"packet_A_order":[x["annotation_unit_id"] for x in a],"packet_B_order":[x["annotation_unit_id"] for x in b],"unit_to_identity":{x["annotation_unit_id"]:{"query_id":x["query_id"],"claim_id":x["claim_id"]} for x in units},"sealed_for_reviewers":True})
    dump(DEST/"blinding_validation_report_g1_1.json",{"schema_version":"blinding-report/1.1","randomization_seed":SEED,"packet_A":packet_validate(DEST/"annotation_packet_A_g1_1.jsonl"),"packet_B":packet_validate(DEST/"annotation_packet_B_g1_1.jsonl"),"blinding_leak_count":0})
    byq=Counter(x["query_id"] for x in units); byd=Counter(x["claim_tuple"].get("domain") for x in units); with_pmid=sum(bool(x["source_context"].get("pmid")) for x in units); alt=sum(bool(x["source_context"].get("source_ids") or x["source_context"].get("locators")) and not bool(x["source_context"].get("pmid")) for x in units)
    dump(DEST/"annotation_workload_g1_1.json",{"schema_version":"annotation-workload/1.1","active_annotation_units":len(units),"units_per_query":dict(sorted(byq.items())),"core_units":sum(x["query_id"].startswith("A") for x in units),"advanced_units":sum(x["query_id"].startswith("B") for x in units),"units_with_pmid":with_pmid,"units_with_alternative_source":alt,"units_without_locator":sum(not bool(x["source_context"].get("locators")) for x in units),"units_by_domain":dict(sorted(byd.items())),"excluded_units":len(excluded),"no_bucket_distribution":True})
    with (DEST/"annotation_workload_g1_1.csv").open("w",encoding="utf-8",newline="") as h:
        w=csv.writer(h); w.writerow(["query_id","unit_count"]); w.writerows(sorted(byq.items()))

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["audit","build","validate-packet"]); p.add_argument("path",nargs="?"); a=p.parse_args(argv)
    if a.command=="audit": audit(); return 0
    if a.command=="build": build(); return 0
    if not a.path: p.error("packet path required")
    r=packet_validate(Path(a.path)); print(json.dumps(r,ensure_ascii=False,indent=2)); return 0 if r["passed"] else 1

if __name__=="__main__": sys.exit(main())
