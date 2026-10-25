"""Pure structural validation and digest for generated dossier explanations."""
import hashlib
import json

from jsonschema import Draft7Validator

from .prompt import REQUIRED_KEYS, TOOL_SCHEMA

METADATA_KEYS = frozenset({
    'narrative_id', 'case_id', 'language', 'model', 'prompt_version',
    'transport_version', 'narrator_input_hash', 'timestamp', 'narrative_hash',
    'generation_origin', 'dossier_narration_contract', 'canonical_sources', 'canonical_observations',
})
_VALIDATOR = Draft7Validator(TOOL_SCHEMA)


def valid_body(body: dict) -> bool:
    if not _VALIDATOR.is_valid(body):
        return False
    if not body['narrative_summary'].strip():
        return False
    return all(entry['candidate_id'].strip() and entry['text'].strip()
               and all(item['text'].strip() and item['observation_id'].strip()
                       for item in entry.get('observation_narratives') or [])
               and ('study_comparison' not in entry or entry['study_comparison']['text'].strip())
               for entry in body['candidate_narratives'])


def body_hash(body: dict) -> str:
    value = {key: body.get(key) for key in REQUIRED_KEYS}
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
