from __future__ import annotations
import copy,hashlib,json
from benchmarks.mtb_evidence.evaluation.metadata_contract_v1_6 import REGISTRY,validate_metadata
NORMALIZATION_SPEC_VERSION="structured_semantic_normalization/1.3"
EXCLUDED_POINTERS=("/metadata/start_time","/metadata/end_time","/metadata/elapsed_ms","/metadata/replica","/metadata/run_id","/metadata/run_key","/metadata/host","/metadata/os","/metadata/python","/metadata/process_id","/metadata/ledger_event_start","/metadata/ledger_event_end","/metadata/output_path","/metadata/temporary_path","/result/latency_ms","/result/observability/latency_ms","/result/payload/latency_ms")
PRESERVED_POINTERS=tuple('/metadata/'+k for k,v in REGISTRY.items() if v['classification']=='SEMANTIC_OR_PROTOCOL_PRESERVED')
def remove(doc,p):
 cur=doc;parts=p.strip('/').split('/')
 for part in parts[:-1]:
  if not isinstance(cur,dict):return
  cur=cur.get(part)
 if isinstance(cur,dict):cur.pop(parts[-1],None)
def normalize(raw):
 if not isinstance(raw,dict) or not isinstance(raw.get('metadata'),dict):raise ValueError('OUTPUT_SCHEMA_FAILURE')
 validate_metadata(raw['metadata']);out=copy.deepcopy(raw)
 for p in EXCLUDED_POINTERS:remove(out,p)
 return json.loads(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
def semantic_sha256(raw):return hashlib.sha256(json.dumps(normalize(raw),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
