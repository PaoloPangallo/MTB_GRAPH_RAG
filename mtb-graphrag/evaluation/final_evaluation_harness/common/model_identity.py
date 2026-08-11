"""Fail-closed Protocol 1.3 model and generation identity checks."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Mapping
from .protocol_loader import load_protocol

class GenerationIdentityError(RuntimeError): pass

def validate_execution_environment(environ: Mapping[str,str] | None = None) -> dict:
    env=os.environ if environ is None else environ; p=load_protocol(); mi=__import__('json').loads((p.root/'model_identity_contract.json').read_text(encoding='utf-8')); gc=__import__('json').loads((p.root/'generation_configuration.json').read_text(encoding='utf-8'))
    model=env.get('RESEARCH_PIPELINE_MODEL','')
    if model != mi['effective_model']: raise GenerationIdentityError('MODEL_IDENTITY_MISMATCH')
    base=env.get('RESEARCH_PIPELINE_LLM_BASE_URL','')
    if base not in ('','https://ollama.com'): raise GenerationIdentityError('ENDPOINT_IDENTITY_MISMATCH')
    if env.get('OLLAMA_BASE_URL','') not in ('',): raise GenerationIdentityError('ENDPOINT_IDENTITY_MISMATCH')
    timeout=env.get('RESEARCH_PIPELINE_LLM_TIMEOUT','')
    if timeout not in ('','60'): raise GenerationIdentityError('GENERATION_CONFIGURATION_MISMATCH')
    if not env.get('OLLAMA_API_KEY'): raise GenerationIdentityError('LLM_CREDENTIAL_MISSING')
    return {'provider':mi['provider'],'model':model,'endpoint':mi['endpoint'],'roles':gc['roles']}

def validate_prompt_hashes() -> None:
    p=load_protocol(); import json
    expected=json.loads((p.root/'generation_configuration.json').read_text(encoding='utf-8'))['roles']
    from backend.research_pipeline.casecontext import prompt as cp
    from backend.research_pipeline.enrichment import prompt_v2 as ep
    from backend.research_pipeline.narrative import prompt as np
    import hashlib
    narr=hashlib.sha256(json.dumps({'version':np.NARRATOR_PROMPT_VERSION,'system':np.SYSTEM_PROMPT,'schema':np.TOOL_SCHEMA,'language':np.NARRATIVE_LANGUAGE},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    actual={'case_context_parser':(cp.PROMPT_VERSION,cp.prompt_hash()),'paper_context_enricher':(ep.PROMPT_VERSION,ep.prompt_hash()),'dossier_narrator':(np.NARRATOR_PROMPT_VERSION,narr)}
    for role,(version,digest) in actual.items():
        if (expected[role]['prompt_version'],expected[role]['prompt_sha256']) != (version,digest): raise GenerationIdentityError('PROMPT_IDENTITY_MISMATCH')
