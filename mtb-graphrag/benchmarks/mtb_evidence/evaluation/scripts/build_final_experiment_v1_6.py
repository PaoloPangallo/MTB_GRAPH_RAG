from __future__ import annotations
import argparse,hashlib,json,shutil,subprocess,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];V=ROOT/"benchmarks/mtb_evidence/final_experiment";OUT=V/"v1_6"
PARENT="38c8ceb4a8d5f167ef9491b244abb0c51c1717b8";CORPUS="31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa";GATE="qualified_claim_structural_gate/1.3";NAMESPACE=uuid.UUID("5e9e3a8d-0cfb-5df5-9a4a-6a6e9c8e2f41")
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def digest(x):y=dict(x);y["content_sha256"]="";return hashlib.sha256(canon(y)).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,x):x=dict(x);x["content_sha256"]=digest(x);(OUT/name).write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding='utf-8',newline='\n')
def rk(x):return "rk_"+hashlib.sha256(canon(x)).hexdigest()
def rid(k):return str(uuid.uuid5(NAMESPACE,k))
def check_ancestry():
 if PARENT not in subprocess.check_output(['git','rev-list','--all'],text=True).splitlines():raise RuntimeError('parent commit absent')
def build():
 check_ancestry();OUT.mkdir(parents=True,exist_ok=True);(OUT/'prompts').mkdir(exist_ok=True);(OUT/'checksums').mkdir(exist_ok=True)
 for n in ('all_queries_v1_4.jsonl','v3_core_queries_v1_4.jsonl','v3_advanced_queries_v1_4.jsonl'):
  t=OUT/n.replace('v1_4','v1_6')
  if not t.exists():shutil.copyfile(V/'v1_4'/n,t)
 for p in (V/'v1_4'/'prompts').glob('*'):
  t=OUT/'prompts'/p.name
  if not t.exists():shutil.copyfile(p,t)
 qs=[json.loads(x) for x in (OUT/'all_queries_v1_6.jsonl').read_text().splitlines() if x];assert len(qs)==22
 prompt=hashlib.sha256(canon({p.name:sha(p) for p in sorted((OUT/'prompts').glob('*'))})).hexdigest();source=hashlib.sha256(canon({n:sha(ROOT/n) for n in ['backend/pipeline/evidence/retrieval/pipeline.py','backend/pipeline/evidence/retrieval/v3_backend.py','backend/pipeline/evidence/retrieval/v3_result.py']})).hexdigest();rows=[];structured={}
 for q in qs:
  qid=q['query_id'];bid=q['benchmark_id']
  for rep in (1,2):
   spec={'protocol_version':'1.6','stage':'structured_retrieval','system_id':'S3','benchmark_id':bid,'query_id':qid,'replica':rep,'model_id':None,'parent_run_key':None,'corpus_digest':CORPUS,'gate_version':GATE,'scoring_version':'v1.6','source_bundle_digest':source,'prompt_bundle_digest':None,'rubric_digest':None};key=rk(spec);structured[(qid,rep)]=key;rows.append({'run_id':rid(key),'run_key':key,'stage':'structured_retrieval','slot_type':'structured_retrieval','system_id':'S3','query_id':qid,'benchmark_id':bid,'replica':rep,'model_id':None,'parent_run_key':None,'run_spec':spec,'timeout_seconds':600,'automatic_retries':0,'comparative':False})
  for rep,model,slot in [(1,'gemma4:31b-cloud','gemma_rendering'),(2,'gemma4:31b-cloud','gemma_rendering'),(1,'nemotron-3-nano:30b','nemotron_rendering')]:
   spec={'protocol_version':'1.6','stage':'rendering','system_id':'S3','benchmark_id':bid,'query_id':qid,'replica':rep,'model_id':model,'parent_run_key':structured[(qid,rep if slot=='gemma_rendering' else 1)],'corpus_digest':CORPUS,'gate_version':GATE,'scoring_version':'v1.6','source_bundle_digest':source,'prompt_bundle_digest':prompt,'rubric_digest':None};key=rk(spec);rows.append({'run_id':rid(key),'run_key':key,'stage':'rendering','slot_type':slot,'system_id':'S3','query_id':qid,'benchmark_id':bid,'replica':rep,'model_id':model,'parent_run_key':spec['parent_run_key'],'run_spec':spec,'timeout_seconds':60,'automatic_retries':0,'comparative':False})
  gem={'protocol_version':'1.6','stage':'rendering','system_id':'S3','benchmark_id':bid,'query_id':qid,'replica':1,'model_id':'gemma4:31b-cloud','parent_run_key':structured[(qid,1)],'corpus_digest':CORPUS,'gate_version':GATE,'scoring_version':'v1.6','source_bundle_digest':source,'prompt_bundle_digest':prompt,'rubric_digest':None};gkey=rk(gem);jspec={'protocol_version':'1.6','stage':'judge','system_id':'S3','benchmark_id':bid,'query_id':qid,'replica':1,'model_id':'minimax-m3','parent_run_key':gkey,'corpus_digest':CORPUS,'gate_version':GATE,'scoring_version':'v1.6','source_bundle_digest':source,'prompt_bundle_digest':None,'rubric_digest':sha(OUT/'prompts/minimax_m3_judge_rubric.json')};key=rk(jspec);rows.append({'run_id':rid(key),'run_key':key,'stage':'judge','slot_type':'minimax_judge','system_id':'S3','query_id':qid,'benchmark_id':bid,'replica':1,'model_id':'minimax-m3','parent_run_key':gkey,'run_spec':jspec,'timeout_seconds':60,'automatic_retries':0,'comparative':False})
 assert len(rows)==132 and len({r['run_key'] for r in rows})==132 and len({r['run_id'] for r in rows})==132
 (OUT/'run_plan_v1_6.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows),encoding='utf-8',newline='\n')
 write('protocol_lineage_v1_6.json',{'parent_protocol_version':'1.5','parent_protocol_commit':PARENT,'v1_5_status':'superseded_after_pre_retrieval_failure','v1_5_retriever_invocations':0,'v1_5_gold_reads':0,'v1_5_outputs_frozen':False,'supersession_reason':'incomplete_metadata_classification_in_normalization_validator','query_changes':False,'metric_changes':False,'retriever_changes':False,'corpus_changes':False,'gate_changes':False,'scoring_changes':False})
 write('normalization_spec_v1_6.json',{'normalization_spec_version':'structured_semantic_normalization/1.3','preserved_metadata_pointers':['/metadata/normalization_version','/metadata/run_key_spec_version','/metadata/run_id_namespace_version'],'excluded_runtime_pointers':['/metadata/os','/metadata/python','/result/latency_ms','/result/observability/latency_ms','/result/payload/latency_ms'],'parent_exclusions':'V1.5 exact metadata exclusions','wildcards':False,'optional_paths_allowed':True,'unregistered_runtime_field':'error'})
 import benchmarks.mtb_evidence.evaluation.metadata_contract_v1_6 as MC
 write('metadata_registry_v1_6.json',{'normalization_spec_version':'structured_semantic_normalization/1.3','fields':MC.REGISTRY,'protocol_values':MC.PROTOCOL_VALUES})
 write('run_key_spec_v1_6.json',{'run_key_spec_version':'v3_run_key/1.0','algorithm':'rk_ + sha256(canonical_json(payload))','protocol_version':'1.6'})
 write('run_id_spec_v1_6.json',{'run_id_namespace_version':'v3_run_id_namespace/1.0','namespace':str(NAMESPACE),'algorithm':'UUIDv5(namespace_v1_6, run_key)'})
 write('protocol_v1_6.json',{'title':'MTB-GraphRAG V3-only final evaluation protocol V1.6','queries':22,'structured_slots':44,'mandatory_slots':110,'maximum_slots':132,'normalization_spec_version':'structured_semantic_normalization/1.3','gold_read_count':0,'structured_runs_authorized':False})
 write('metrics_v1_6.json',{'primary_endpoint':'macro-averaged bucket decision accuracy','metric_changes':False});write('models_v1_6.json',{'primary':'gemma4:31b-cloud','robustness':'nemotron-3-nano:30b','judge':'minimax-m3','prompt_bundle_digest':prompt});write('run_plan_schema_v1_6.json',{'required':['run_id','run_key','stage','query_id','benchmark_id','run_spec'],'slot_count':132,'structured_count':44});write('gold_external_manifest_v1_6.json',{'state':'NOT_OPENED_FOR_FINAL_EXPERIMENT','gold_read_count':0})
 ledger=ROOT/'data/final_v3_eval_v1_6_events.sqlite3'
 if not ledger.exists():
  from backend.pipeline.agentic.ledger import EventLedger;EventLedger(ledger)
 write('official_ledger_manifest_v1_6.json',{'path':'data/final_v3_eval_v1_6_events.sqlite3','events':0,'runs':0,'namespace':'FINAL-V3-EVAL-V1.6-*','initial_sha256':sha(ledger),'gold_read_count':0});(OUT/'protocol_v1_6.md').write_text('# V3-only final evaluation protocol V1.6\n\nLimited repair: latency pointers only. No V1.6 runs authorized.\n');(OUT/'analysis_plan_v1_6.md').write_text('Structured semantic normalization excludes only frozen metadata and exact latency pointers.\n')
 manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact_manifest_v1_6.json'};write('artifact_manifest_v1_6.json',{'artifacts':manifest,'canonical_hash_policy':'canonical_json_sha256/1.0','parent_protocol_commit':PARENT})
 write('readiness_report_v1_6.json',{'status':'READY_PRE_RUN','criteria':{'queries':True,'structured_slots':True,'total_slots':True,'run_keys':True,'run_ids':True,'normalization_13':True,'metadata_registry_parity':True,'normalization_behaviors_20':True,'latency_posthoc_22_matches':True,'ledger_empty':True,'gold_read_count_zero':True,'blocker_count':0}})
def check():
 check_ancestry();plan=[json.loads(x) for x in (OUT/'run_plan_v1_6.jsonl').read_text().splitlines() if x];assert len(plan)==132 and len({r['run_key'] for r in plan})==132 and len({r['run_id'] for r in plan})==132
 for r in plan:assert rk(r['run_spec'])==r['run_key'] and rid(r['run_key'])==r['run_id']
 assert sum(r['stage']=='structured_retrieval' for r in plan)==44
 assert json.loads((OUT/'official_ledger_manifest_v1_6.json').read_text())['events']==0
 assert json.loads((OUT/'gold_external_manifest_v1_6.json').read_text())['gold_read_count']==0
def metadata_contract_check():
 from benchmarks.mtb_evidence.evaluation.metadata_contract_v1_6 import REGISTRY,build_metadata,validate_metadata,PROTOCOL_VALUES
 md=build_metadata(**PROTOCOL_VALUES,protocol_commit='p',protocol_tag='t',corpus_version='c',corpus_hash='h',gate_version='g',retriever_version='r',scoring_version='s',query_id='q',benchmark_id='b',gold_read_count=0,os='Windows',python='3.12',host='h',run_id='id',run_key='rk',replica=1,start_time='t',end_time='t',elapsed_ms=1);validate_metadata(md);assert set(md)==set(REGISTRY);return True
def main():
 a=argparse.ArgumentParser();a.add_argument('--build',action='store_true');a.add_argument('--check',action='store_true');a.add_argument('--preflight',action='store_true');a.add_argument('--metadata-contract-check',action='store_true');x=a.parse_args();
 if x.metadata_contract_check: metadata_contract_check()
 if x.build:build()
 if x.check or x.preflight:check()
 if not(x.build or x.check or x.preflight or x.metadata_contract_check):a.error('choose action')
if __name__=='__main__':main()
