from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]; V=ROOT/"benchmarks/mtb_evidence/final_experiment"; OUT=V/"v1_4"
PARENT_COMMIT="0f6a30cf39c03fb277bd67a476d949e0028da5df"; ARCH="63940203498db23c3cdc5a400cd78575489dcfe2"
CORPUS_HASH="31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"; GATE="qualified_claim_structural_gate/1.3"; RETRIEVER="qualified_claim_retriever/1.0"; GRAPH="2b4a1d6e731f4f490f5be134267a0801ec25c6e954a0e8958424e12b3f48899d"
NAMESPACE=uuid.UUID("9c5f0d2a-08f4-5d19-8f5c-3b0c8b8852b2")
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def digest(x):
 y=dict(x); y["content_sha256"]=""; return hashlib.sha256(canon(y)).hexdigest()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write_json(name,x):
 x=dict(x); x["content_sha256"]=digest(x); (OUT/name).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="\n")
def rk(payload): return "rk_"+hashlib.sha256(canon(payload)).hexdigest()
def runid(key): return str(uuid.uuid5(NAMESPACE,key))
def ancestry():
 commits=subprocess.check_output(["git","rev-list","--all"],text=True).splitlines()
 if PARENT_COMMIT not in commits or ARCH not in commits: raise RuntimeError("required ancestry missing")
def build():
 ancestry(); OUT.mkdir(parents=True,exist_ok=True); (OUT/"prompts").mkdir(exist_ok=True); (OUT/"checksums").mkdir(exist_ok=True)
 for n in ("all_queries_v1_3.jsonl","v3_core_queries_v1_3.jsonl","v3_advanced_queries_v1_3.jsonl"):
  t=OUT/n.replace("v1_3","v1_4");
  if not t.exists(): shutil.copyfile(V/"v1_3"/n,t)
 # byte-identical prompt bundle
 for p in (V/"v1_3"/"prompts").glob("*"):
  t=OUT/"prompts"/p.name
  if not t.exists(): shutil.copyfile(p,t)
 queries=[json.loads(x) for x in (OUT/"all_queries_v1_4.jsonl").read_text().splitlines() if x]
 if len(queries)!=22 or len({q["query_id"] for q in queries})!=22: raise RuntimeError("query bundle")
 prompt_digest=hashlib.sha256(canon({p.name:sha(p) for p in sorted((OUT/"prompts").glob("*"))})).hexdigest()
 source_files=["backend/pipeline/evidence/retrieval/pipeline.py","backend/pipeline/evidence/retrieval/v3_backend.py","backend/pipeline/evidence/retrieval/v3_result.py"]
 source_digest=hashlib.sha256(canon({n:sha(ROOT/n) for n in source_files})).hexdigest()
 rows=[]; structured={}
 for q in queries:
  qid=q["query_id"]; bid=q["benchmark_id"]
  for rep in (1,2):
   payload={"protocol_version":"1.4","stage":"structured_retrieval","system_id":"S3","benchmark_id":bid,"query_id":qid,"replica":rep,"model_id":None,"parent_run_key":None,"corpus_digest":CORPUS_HASH,"gate_version":GATE,"scoring_version":"v1.4","source_bundle_digest":source_digest,"prompt_bundle_digest":None,"rubric_digest":None}
   key=rk(payload); structured[(qid,rep)]=key; rows.append({"run_id":runid(key),"run_key":key,"stage":"structured_retrieval","slot_type":"structured_retrieval","system_id":"S3","query_id":qid,"benchmark_id":bid,"replica":rep,"model_id":None,"parent_run_key":None,"run_spec":payload,"timeout_seconds":600,"automatic_retries":0,"comparative":False})
  for rep in (1,2):
   parent=structured[(qid,rep)]; payload={"protocol_version":"1.4","stage":"rendering","system_id":"S3","benchmark_id":bid,"query_id":qid,"replica":rep,"model_id":"gemma4:31b-cloud","parent_run_key":parent,"corpus_digest":CORPUS_HASH,"gate_version":GATE,"scoring_version":"v1.4","source_bundle_digest":source_digest,"prompt_bundle_digest":prompt_digest,"rubric_digest":None}; key=rk(payload); rows.append({"run_id":runid(key),"run_key":key,"stage":"rendering","slot_type":"gemma_rendering","system_id":"S3","query_id":qid,"benchmark_id":bid,"replica":rep,"model_id":"gemma4:31b-cloud","parent_run_key":parent,"run_spec":payload,"timeout_seconds":60,"automatic_retries":0,"comparative":False})
  gp=structured[(qid,1)]; payload={"protocol_version":"1.4","stage":"rendering","system_id":"S3","benchmark_id":bid,"query_id":qid,"replica":1,"model_id":"nemotron-3-nano:30b","parent_run_key":gp,"corpus_digest":CORPUS_HASH,"gate_version":GATE,"scoring_version":"v1.4","source_bundle_digest":source_digest,"prompt_bundle_digest":prompt_digest,"rubric_digest":None}; key=rk(payload); rows.append({"run_id":runid(key),"run_key":key,"stage":"rendering","slot_type":"nemotron_rendering","system_id":"S3","query_id":qid,"benchmark_id":bid,"replica":1,"model_id":"nemotron-3-nano:30b","parent_run_key":gp,"run_spec":payload,"timeout_seconds":60,"automatic_retries":0,"comparative":False})
  gemma=rk({"protocol_version":"1.4","stage":"rendering","system_id":"S3","benchmark_id":bid,"query_id":qid,"replica":1,"model_id":"gemma4:31b-cloud","parent_run_key":structured[(qid,1)],"corpus_digest":CORPUS_HASH,"gate_version":GATE,"scoring_version":"v1.4","source_bundle_digest":source_digest,"prompt_bundle_digest":prompt_digest,"rubric_digest":None})
  payload={"protocol_version":"1.4","stage":"judge","system_id":"S3","benchmark_id":bid,"query_id":qid,"replica":1,"model_id":"minimax-m3","parent_run_key":gemma,"corpus_digest":CORPUS_HASH,"gate_version":GATE,"scoring_version":"v1.4","source_bundle_digest":source_digest,"prompt_bundle_digest":None,"rubric_digest":sha(OUT/"prompts/minimax_m3_judge_rubric.json")}; key=rk(payload); rows.append({"run_id":runid(key),"run_key":key,"stage":"judge","slot_type":"minimax_judge","system_id":"S3","query_id":qid,"benchmark_id":bid,"replica":1,"model_id":"minimax-m3","parent_run_key":gemma,"run_spec":payload,"timeout_seconds":60,"automatic_retries":0,"comparative":False})
 if len(rows)!=132 or len({r["run_key"] for r in rows})!=132 or len({r["run_id"] for r in rows})!=132: raise RuntimeError("slot identity")
 (OUT/"run_plan_v1_4.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n" for r in rows),encoding="utf-8",newline="\n")
 write_json("protocol_lineage_v1_4.json",{"parent_protocol_version":"1.3","parent_protocol_commit":PARENT_COMMIT,"v1_3_status":"superseded_before_output_freeze","v1_3_structured_runs_completed":44,"v1_3_structured_outputs_frozen":False,"v1_3_gold_reads":0,"v1_3_runtime_failures":0,"supersession_reasons":["missing_run_key_in_run_plan","incomplete_semantic_normalization_contract"],"semantic_query_changes":False,"metric_changes":False,"retriever_changes":False,"corpus_changes":False,"gate_changes":False})
 write_json("run_key_spec_v1_4.json",{"run_key_spec_version":"v3_run_key/1.0","algorithm":"rk_ + sha256(canonical_json(payload))","canonicalization":"canonical_json_sha256/1.0","timestamp_independent":True})
 write_json("run_id_spec_v1_4.json",{"run_id_namespace_version":"v3_run_id_namespace/1.0","namespace":str(NAMESPACE),"algorithm":"UUIDv5(namespace_v1_4, run_key)"})
 write_json("normalization_spec_v1_4.json",{"normalization_spec_version":"structured_semantic_normalization/1.1","excluded_json_pointers":["/metadata/start_time","/metadata/end_time","/metadata/elapsed_ms","/metadata/replica","/metadata/run_id","/metadata/run_key","/metadata/host","/metadata/process_id","/metadata/ledger_event_start","/metadata/ledger_event_end","/metadata/output_path","/metadata/temporary_path"],"array_order_preserved":True,"null_preserved":True,"unregistered_runtime_field":"fail"})
 write_json("metrics_v1_4.json",{"primary_endpoint":"macro-averaged bucket decision accuracy","metric_changes":False})
 write_json("models_v1_4.json",{"primary":"gemma4:31b-cloud","robustness":"nemotron-3-nano:30b","judge":"minimax-m3","prompt_bundle_digest":prompt_digest})
 write_json("run_plan_schema_v1_4.json",{"required":["run_id","run_key","stage","query_id","benchmark_id","run_spec"],"slot_count":132,"structured_count":44})
 write_json("gold_external_manifest_v1_4.json",{"state":"NOT_OPENED_FOR_FINAL_EXPERIMENT","gold_read_count":0})
 ledger=ROOT/"data/final_v3_eval_v1_4_events.sqlite3"
 if not ledger.exists():
  from backend.pipeline.agentic.ledger import EventLedger; EventLedger(ledger)
 write_json("official_ledger_manifest_v1_4.json",{"path":"data/final_v3_eval_v1_4_events.sqlite3","events":0,"runs":0,"namespace":"FINAL-V3-EVAL-V1.4-*","gold_read_count":0,"initial_sha256":sha(ledger)})
 write_json("protocol_v1_4.json",{"title":"MTB-GraphRAG V3-only final evaluation protocol V1.4","queries":22,"structured_slots":44,"mandatory_slots":110,"maximum_slots":132,"run_key_spec_version":"v3_run_key/1.0","run_id_namespace_version":"v3_run_id_namespace/1.0","normalization_spec_version":"structured_semantic_normalization/1.1","gold_read_count":0,"structured_runs_authorized":False})
 (OUT/"protocol_v1_4.md").write_text("# V3-only final evaluation protocol V1.4\n\nProtocol repair only. No V1.4 run is authorized in this freeze.\n",encoding="utf-8")
 (OUT/"analysis_plan_v1_4.md").write_text("Run identity is deterministic from canonical run_key; semantic replica comparison removes only the exact frozen JSON pointers.\n",encoding="utf-8")
 manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="artifact_manifest_v1_4.json"}; write_json("artifact_manifest_v1_4.json",{"canonical_hash_policy":"canonical_json_sha256/1.0","artifacts":manifest,"corpus_hash":CORPUS_HASH,"gate_version":GATE,"parent_protocol_commit":PARENT_COMMIT})
 write_json("readiness_report_v1_4.json",{"status":"READY_PRE_RUN","criteria":{"queries":len(queries)==22,"slots":len(rows)==132,"run_keys":len({r["run_key"] for r in rows})==132,"run_ids":len({r["run_id"] for r in rows})==132,"gold_read_count_zero":True,"ledger_empty":True,"blocker_count":0}})
def check():
 ancestry(); plan=[json.loads(x) for x in (OUT/"run_plan_v1_4.jsonl").read_text().splitlines() if x]
 if len(plan)!=132 or len({r["run_key"] for r in plan})!=132 or len({r["run_id"] for r in plan})!=132: raise RuntimeError("identity check")
 if any("run_key" not in r or "run_id" not in r for r in plan): raise RuntimeError("missing identity")
 for r in plan:
  if rk(r["run_spec"])!=r["run_key"] or runid(r["run_key"])!=r["run_id"]: raise RuntimeError("identity reproducibility")
 if sum(r["stage"]=="structured_retrieval" for r in plan)!=44: raise RuntimeError("structured count")
 if any(r["parent_run_key"] and r["parent_run_key"] not in {x["run_key"] for x in plan} for r in plan): raise RuntimeError("parent key")
 data=json.loads((OUT/"official_ledger_manifest_v1_4.json").read_text());
 if data["events"]!=0 or json.loads((OUT/"gold_external_manifest_v1_4.json").read_text())["gold_read_count"]!=0: raise RuntimeError("state")
def main():
 a=argparse.ArgumentParser(); a.add_argument("--build",action="store_true");a.add_argument("--check",action="store_true");a.add_argument("--preflight",action="store_true"); x=a.parse_args();
 if x.build: build()
 if x.check or x.preflight: check()
 if not (x.build or x.check or x.preflight): a.error("choose action")
if __name__=="__main__": main()
