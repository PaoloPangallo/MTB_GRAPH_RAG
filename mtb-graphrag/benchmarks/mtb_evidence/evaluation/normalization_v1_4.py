"""Exact semantic projection contract for V3 structured outputs V1.4."""
from __future__ import annotations
import copy, hashlib, json
NORMALIZATION_SPEC_VERSION = "structured_semantic_normalization/1.1"
EXCLUDED_METADATA_FIELDS = ("start_time","end_time","elapsed_ms","replica","run_id","run_key","host","process_id","ledger_event_start","ledger_event_end","output_path","temporary_path")

def _drop_pointer(doc):
    out=copy.deepcopy(doc)
    md=out.get("metadata")
    if isinstance(md,dict):
        for field in EXCLUDED_METADATA_FIELDS: md.pop(field,None)
    return out

def normalize(raw):
    if not isinstance(raw,dict): raise ValueError("OUTPUT_SCHEMA_FAILURE")
    out=_drop_pointer(raw)
    return json.loads(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False))

def semantic_sha256(raw):
    return hashlib.sha256(json.dumps(normalize(raw),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()

def raw_sha256(raw_bytes): return hashlib.sha256(raw_bytes).hexdigest()

def validate_runtime_fields(raw):
    md=raw.get("metadata",{})
    if not isinstance(md,dict): raise ValueError("OUTPUT_SCHEMA_FAILURE")
    allowed=set(EXCLUDED_METADATA_FIELDS)|{"protocol_commit","protocol_tag","execution_branch","query_id","benchmark_id","corpus_version","corpus_hash","gate_version","retriever_version","scoring_version","gold_read_count"}
    unknown=set(md)-allowed
    if unknown: raise ValueError("UNREGISTERED_RUNTIME_FIELD:"+','.join(sorted(unknown)))
    return True
