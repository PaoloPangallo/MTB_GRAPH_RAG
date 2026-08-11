"""Metadata-only provider snapshot parsing and drift comparison."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone

IDENTITY_FIELDS=('model_alias','family','parameter_size','quantization','context_length')
class ProviderMetadataMismatch(RuntimeError): pass

def collect_snapshot(metadata_request, model_alias: str, *, endpoint: str='/api/show', timestamp: str|None=None) -> dict:
    """Collect metadata through an injected metadata-only request callable."""
    raw = metadata_request(model_alias)
    if not isinstance(raw, dict):
        raise ProviderMetadataMismatch('PROVIDER_METADATA_RESPONSE_INVALID')
    return parse_metadata(model_alias, raw, endpoint=endpoint, timestamp=timestamp)

def parse_metadata(model_alias: str, raw: dict, *, endpoint: str='/api/show', timestamp: str|None=None) -> dict:
    details=raw.get('details') or {}; info=raw.get('model_info') or {}
    parsed={'model_alias':model_alias,'family':details.get('family'),'parameter_size':details.get('parameter_size'),'quantization':details.get('quantization_level'),'context_length':info.get('gemma4.context_length'),'modified_at':raw.get('modified_at')}
    payload=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return {'timestamp_utc':timestamp or datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'endpoint_path':endpoint,'http_status':200,'sanitized_raw_metadata':raw,'raw_sha256':hashlib.sha256(payload).hexdigest(),'parsed_identity_fields':parsed}

def validate_metadata(snapshot: dict, expected: dict) -> None:
    observed=snapshot.get('parsed_identity_fields',{})
    for field,value in expected.items():
        if observed.get(field)!=value: raise ProviderMetadataMismatch('PROVIDER_MODEL_METADATA_MISMATCH')

def compare_snapshots(pre: dict, post: dict) -> list[str]:
    a=pre.get('parsed_identity_fields',{}); b=post.get('parsed_identity_fields',{})
    return [field for field in IDENTITY_FIELDS if a.get(field)!=b.get(field)]
