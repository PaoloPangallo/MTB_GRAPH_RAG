from __future__ import annotations
from dataclasses import dataclass
from typing import Any
PROTOCOL_VALUES={"normalization_version":"structured_semantic_normalization/1.3","run_key_spec_version":"v3_run_key/1.0","run_id_namespace_version":"v3_run_id_namespace/1.0"}
PRESERVED={"protocol_commit","protocol_tag","corpus_version","corpus_hash","gate_version","retriever_version","scoring_version","normalization_version","run_key_spec_version","run_id_namespace_version","query_id","benchmark_id","gold_read_count"}
RUNTIME_EXCLUDED={"start_time","end_time","elapsed_ms","replica","run_id","run_key","host","os","python","process_id","ledger_event_start","ledger_event_end","output_path","temporary_path"}
REGISTRY={**{k:{"field_name":k,"exact_json_pointer":"/metadata/"+k,"classification":"SEMANTIC_OR_PROTOCOL_PRESERVED","required":True,"included_in_raw":True,"included_in_normalized":True,"included_in_semantic_hash":True,"included_in_run_manifest":True,"version_introduced":"1.6"} for k in PRESERVED},**{k:{"field_name":k,"exact_json_pointer":"/metadata/"+k,"classification":"REGISTERED_RUNTIME_EXCLUDED","required":False,"included_in_raw":True,"included_in_normalized":False,"included_in_semantic_hash":False,"included_in_run_manifest":True,"version_introduced":"1.6"} for k in RUNTIME_EXCLUDED}}
def build_metadata(**values:Any)->dict[str,Any]:
 base={k:values.get(k) for k in REGISTRY}
 base.update({k:values[k] for k in values if k in REGISTRY})
 return base
def validate_metadata(md:dict[str,Any])->None:
 unknown=set(md)-set(REGISTRY)
 if unknown: raise ValueError('UNREGISTERED_RUNTIME_FIELD:'+','.join(sorted(unknown)))
 for k,v in PROTOCOL_VALUES.items():
  if md.get(k)!=v: raise ValueError('PROTOCOL_METADATA_MISMATCH:'+k)
def metadata_fields()->set[str]:return set(REGISTRY)
