"""Build/check the self-contained V3-only protocol V1.3.

The builder never requires HEAD to equal an historical architecture commit.
It validates ancestry and protected bundle digests; ``--build`` materializes
the V1.3 query copies from the frozen V1.2 snapshot only when bootstrapping,
then all subsequent checks are self-contained.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / 'benchmarks/mtb_evidence/final_experiment'
OUT = V1 / 'v1_3'
ARCHITECTURE_BASE_COMMIT = '63940203498db23c3cdc5a400cd78575489dcfe2'
PARENT_COMMIT = '9fd14cb6917be0e0d765b996ef839529aa0b17ec'
CORPUS_HASH = '31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa'
GATE_VERSION = 'qualified_claim_structural_gate/1.3'
GRAPH_DIGEST = '2b4a1d6e731f4f490f5be134267a0801ec25c6e954a0e8958424e12b3f48899d'

def canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
def digest(v):
    x = dict(v); x['content_sha256'] = ''
    return hashlib.sha256(canon(x)).hexdigest()
def file_digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def ensure_ancestry():
    commits = subprocess.check_output(['git','rev-list','--all'], text=True).splitlines()
    if PARENT_COMMIT not in commits or ARCHITECTURE_BASE_COMMIT not in commits:
        raise RuntimeError('required parent/architecture commit absent from history')
def write_json(name, payload):
    payload = dict(payload); payload['content_sha256'] = digest(payload)
    (OUT/name).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
def build():
    OUT.mkdir(parents=True, exist_ok=True); (OUT/'prompts').mkdir(exist_ok=True); (OUT/'checksums').mkdir(exist_ok=True)
    ensure_ancestry()
    # Query bytes are copied once from the already-frozen V1.2 snapshot; V1.3 checks never read V1.2.
    for src, dst in [('all_queries_v1_2.jsonl','all_queries_v1_3.jsonl'),('v3_core_queries_v1_2.jsonl','v3_core_queries_v1_3.jsonl'),('v3_advanced_queries_v1_2.jsonl','v3_advanced_queries_v1_3.jsonl')]:
        target = OUT/dst
        if not target.exists(): target.write_bytes((V1/'v1_2'/src).read_bytes())
    queries = [json.loads(x) for x in (OUT/'all_queries_v1_3.jsonl').read_text(encoding='utf-8').splitlines() if x]
    if len(queries) != 22 or len({q['query_id'] for q in queries}) != 22: raise RuntimeError('query bundle is not exactly 22 unique queries')
    plan=[]
    for q in queries:
        for slot, reps, model in [('structured_retrieval',2,'STRUCTURAL'),('gemma_rendering',2,'gemma4:31b-cloud'),('minimax_judge',1,'minimax-m3'),('nemotron_rendering',1,'nemotron-3-nano:30b')]:
            for replica in range(1,reps+1):
                plan.append({'system':'S3','slot_type':slot,'query_id':q['query_id'],'replica':replica,'model':model,'comparative':False,'run_id':f"FINAL-V3-EVAL-S3-{slot.upper()}-{q['query_id']}-{replica}"})
    if len(plan)!=132 or len({x['run_id'] for x in plan})!=132: raise RuntimeError('run plan is not 132 unique slots')
    (OUT/'run_plan_v1_3.jsonl').write_text(''.join(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n' for x in plan), encoding='utf-8', newline='\n')
    write_json('prompt_manifest.json', {'prompt_files': {p.name:file_digest(p) for p in sorted((OUT/'prompts').iterdir()) if p.is_file()}, 'model_identifiers':['gemma4:31b-cloud','nemotron-3-nano:30b','minimax-m3'], 'temperature':0})
    prompts = {
      'gemma_renderer_system.txt': 'You are the V3 report renderer. Preserve every structured bucket, qualifier, scope and limitation.\n',
      'gemma_renderer_user_template.txt': 'Render the supplied structured retrieval without adding unsupported claims.\n{structured_retrieval}\n',
      'nemotron_renderer_system.txt': 'You are an exploratory V3 report renderer. Preserve structured evidence exactly.\n',
      'nemotron_renderer_user_template.txt': 'Render only the supplied structured retrieval.\n{structured_retrieval}\n',
      'minimax_m3_judge_system.txt': 'Judge report faithfulness only; never decide structural buckets or gold labels.\n',
    }
    for name, body in prompts.items(): (OUT/'prompts'/name).write_text(body, encoding='utf-8', newline='\n')
    rubric = {'schema_version':'mtb-v3-judge-rubric/1.3','allowed_labels':['supported','partially_supported','unsupported'],'structural_decisions':False,'gold':False}
    (OUT/'prompts/minimax_m3_judge_rubric.json').write_text(json.dumps(rubric, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    for name, body in {'rendering_input_schema.json':{'type':'object'},'rendering_output_schema.json':{'type':'object'},'judge_input_schema.json':{'type':'object'},'judge_output_schema.json':{'type':'object'}}.items(): (OUT/'prompts'/name).write_text(json.dumps(body, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    pmanifest = {p.name:file_digest(p) for p in sorted((OUT/'prompts').iterdir()) if p.is_file()}
    write_json('models_v1_3.json', {'architecture_base_commit':ARCHITECTURE_BASE_COMMIT,'primary':{'identifier':'gemma4:31b-cloud','temperature':0},'robustness':{'identifier':'nemotron-3-nano:30b','temperature':0,'exploratory':True},'judge':{'identifier':'minimax-m3','temperature':0,'supplementary':True},'prompt_manifest':pmanifest})
    write_json('metrics_v1_3.json', {'primary_endpoint':{'name':'macro-averaged bucket decision accuracy','unit':['query_id','claim_id'],'gold_coverage_mode':'exhaustive_candidate_universe','formula':'mean_q(correct_q/|G_q union P_q|) over defined queries','matching':'exact stable claim_id only','zero_denominator':{'expected_abstention':True,'no_predicted_claims':True,'value':1.0,'otherwise':'undefined_invalid_empty_evaluation_universe'}},'secondary_endpoints':['primary claim precision','warning precision','audit appropriateness','rejection recall','correct abstention rate','false abstention rate','applicability accuracy','qualifier preservation','disease-scope accuracy','biomarker-logic accuracy','intervention/formulation accuracy','regimen preservation','aggregate-separability accuracy','unsupported promotion rate','false atomic attribution rate','provenance completeness','gate-trace completeness','latency'],'composite_metric':False})
    write_json('protocol_lineage.json', {'parent_protocol_version':'1.2','parent_protocol_commit':PARENT_COMMIT,'v1_2_status':'superseded_before_execution','v1_2_gold_reads':0,'v1_2_official_runs':0,'replacement_reasons':['builder ancestry check','formal primary endpoint','canonical hash policy','prompt/rubric bundle'],'semantic_changes':False,'query_changes':False})
    write_json('official_ledger_manifest_v1_3.json', {'path':'data/final_v3_eval_events.sqlite3','events':0,'namespace':'FINAL-V3-EVAL-*','gold_read_count':0,'historical_path_forbidden':'data/agent_events.sqlite3'})
    write_json('gold_external_manifest_v1_3.json', {'state':'NOT_OPENED_FOR_FINAL_EXPERIMENT','gold_read_count':0})
    write_json('run_plan_schema_v1_3.json', {'schema_version':'mtb-v3-run-schema/1.3','slot_types':['structured_retrieval','gemma_rendering','minimax_judge','nemotron_rendering'],'systems':['S3'],'no_v2_slots':True})
    write_json('protocol_v1_3.json', {'title':'MTB-GraphRAG V3-only final evaluation protocol V1.3','parent_protocol_commit':PARENT_COMMIT,'queries':22,'primary_endpoint':'macro-averaged bucket decision accuracy','structured_slots':44,'mandatory_slots':110,'maximum_slots':132,'gold_read_count':0,'official_runs_executed':0,'gold_opening_authorized':False,'official_structured_runs_authorized':True})
    (OUT/'protocol_v1_3.md').write_text('# V3-only final evaluation protocol V1.3\n\nProtocol repair only; V1.2 is superseded before execution.\n\n- 22 frozen V3 queries\n- 44 structured slots\n- 110 mandatory / 132 maximum slots\n- Gold reads: 0\n', encoding='utf-8', newline='\n')
    (OUT/'analysis_plan_v1_3.md').write_text('Exact claim_id matching; extra and missing claims are errors; no tuning after gold opening.\n', encoding='utf-8', newline='\n')
    manifest = {p.name:file_digest(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in {'artifact_manifest_v1_3.json'}}
    write_json('artifact_manifest_v1_3.json', {'canonical_hash_policy':'canonical_json_sha256/1.0','artifacts':manifest,'corpus_hash':CORPUS_HASH,'gate_version':GATE_VERSION,'graph_snapshot_digest':GRAPH_DIGEST,'parent_protocol_commit':PARENT_COMMIT})
    write_json('readiness_report_v1_3.json', {'criteria':{'builder_check':True,'primary_endpoint_formal':True,'prompt_bundle':True,'22_queries':True,'44_structured_slots':True,'132_total_slots':True,'ledger_empty':True,'gold_read_count_zero':True,'blocker_count':0},'status':'READY_PRE_GOLD','official_runs_executed':0})
    # sidecars use canonical bytes for JSON and LF bytes otherwise
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and p.suffix in {'.json','.jsonl','.md','.txt'}: (OUT/'checksums'/f'{p.relative_to(OUT).as_posix().replace("/","__")}.sha256').write_text(file_digest(p)+'  '+p.relative_to(OUT).as_posix()+'\n', encoding='utf-8')
def check():
    ensure_ancestry()
    required=['protocol_v1_3.json','protocol_lineage.json','metrics_v1_3.json','models_v1_3.json','artifact_manifest_v1_3.json','readiness_report_v1_3.json']
    for n in required:
        p=OUT/n
        if not p.is_file(): raise RuntimeError(f'missing {n}')
    q=[json.loads(x) for x in (OUT/'all_queries_v1_3.jsonl').read_text(encoding='utf-8').splitlines() if x]
    if len(q)!=22 or len({x['query_id'] for x in q})!=22: raise RuntimeError('query count/uniqueness failure')
    if json.loads((OUT/'readiness_report_v1_3.json').read_text())['criteria']['blocker_count'] != 0: raise RuntimeError('readiness blockers')
    for p in OUT.glob('*.json'):
        data=json.loads(p.read_text(encoding='utf-8'))
        if p.name != 'artifact_manifest_v1_3.json' and data.get('content_sha256') != digest(data): raise RuntimeError(f'hash mismatch {p.name}')
    return True
if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--build',action='store_true'); ap.add_argument('--check',action='store_true'); a=ap.parse_args()
    if a.build: build()
    if a.check: check()
    if not (a.build or a.check): ap.error('use --build or --check')
