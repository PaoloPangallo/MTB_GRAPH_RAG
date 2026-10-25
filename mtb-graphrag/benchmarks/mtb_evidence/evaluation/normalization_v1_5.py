"""Exact semantic projection for V1.5: V1.4 runtime fields plus latency objects."""
from __future__ import annotations
import copy,hashlib,json
NORMALIZATION_SPEC_VERSION="structured_semantic_normalization/1.2"
EXCLUDED_METADATA_FIELDS=("start_time","end_time","elapsed_ms","replica","run_id","run_key","host","process_id","ledger_event_start","ledger_event_end","output_path","temporary_path")
EXCLUDED_POINTERS=("/result/latency_ms","/result/observability/latency_ms","/result/payload/latency_ms")
def _remove(doc,path):
 cur=doc
 for part in path.strip('/').split('/')[:-1]:
  if not isinstance(cur,dict): return
  cur=cur.get(part)
 if isinstance(cur,dict): cur.pop(path.strip('/').split('/')[-1],None)
def normalize(raw):
 if not isinstance(raw,dict): raise ValueError('OUTPUT_SCHEMA_FAILURE')
 out=copy.deepcopy(raw);md=out.get('metadata')
 if isinstance(md,dict):
  for k in EXCLUDED_METADATA_FIELDS: md.pop(k,None)
 for p in EXCLUDED_POINTERS:_remove(out,p)
 return json.loads(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
def semantic_sha256(raw):return hashlib.sha256(json.dumps(normalize(raw),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def validate_runtime_fields(raw):
 md=raw.get('metadata',{})
 if not isinstance(md,dict):raise ValueError('OUTPUT_SCHEMA_FAILURE')
 allowed=set(EXCLUDED_METADATA_FIELDS)|{'protocol_commit','protocol_tag','execution_branch','query_id','benchmark_id','corpus_version','corpus_hash','gate_version','retriever_version','scoring_version','gold_read_count'}
 unknown=set(md)-allowed
 if unknown:raise ValueError('UNREGISTERED_RUNTIME_FIELD:'+','.join(sorted(unknown)))
 return True
