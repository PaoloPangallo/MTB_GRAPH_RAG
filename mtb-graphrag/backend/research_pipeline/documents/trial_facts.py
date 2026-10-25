"""Typed registry facts, independently bound to each graph relation."""
import re

VERSION = 'structured-trial-facts/1.0'


def extract_trial_facts(record: dict, snapshot_digest: str) -> dict:
    document_id = record.get('document_id', '')
    if not re.fullmatch(r'nct:NCT\d{8}', document_id) or not snapshot_digest:
        raise ValueError('A resolved NCT identity and snapshot digest are required')
    units = record.get('units') or []
    if any(u.get('document_id') != document_id for u in units):
        raise ValueError('Trial fact unit identity mismatch')
    return {'version': VERSION, 'document_id': document_id, 'nct_id': document_id[4:],
            'snapshot_digest': snapshot_digest, 'units': units,
            'origin': 'RESOLVED_REGISTRY_SOURCE_UNITS', 'eligibility_status': 'NOT_EVALUATED',
            'evidence_interpretation': 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE'}


def bind_trial_relation(candidate: dict, facts: dict, case_id: str) -> dict:
    targets = [str(i.get('label') or '') for i in candidate.get('interventions', [])]
    normalize = lambda value: re.sub(r'\W+', ' ', value.casefold()).strip()
    units = facts['units']
    matching = [u for u in units if u.get('unit_type') == 'INTERVENTION'
                and any(normalize(t) == normalize(u.get('text', '')) for t in targets)]
    if not targets:
        genes = [str(b.get('gene') or b.get('label') or '') for b in candidate.get('biomarkers', [])]
        matching = [u for u in units if u.get('unit_type') in {'BRIEF_SUMMARY', 'DETAILED_DESCRIPTION', 'TRIAL_TITLE'}
                    and any(g and re.search(r'\b' + re.escape(g) + r'\b', u.get('text', ''), re.I) for g in genes)]
    unit = min(matching, key=lambda u: (len(u.get('text', '')), u['source_unit_id'])) if matching else None
    observation = {'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE'}
    if unit:
        intervention = unit['text'] if unit.get('unit_type') == 'INTERVENTION' else None
        relation = {'subjects': [], 'disease': None, 'intervention': intervention,
                    'observed_stance': 'UNKNOWN', 'effect_direction': 'UNKNOWN',
                    'relation_assertion': 'ENTITY_CO_OCCURRENCE', 'relation_scope': 'UNKNOWN',
                    'molecular_composition': 'UNKNOWN', 'intervention_composition': 'UNKNOWN',
                    'trial_context': {}, 'evidence_context': {'subject_level': 'UNKNOWN', 'claim_type': 'OTHER'}}
        observation = {'decision': 'QUOTE', 'source_unit_id': unit['source_unit_id'], 'quote': unit['text'],
                       'author_claim_quote': unit['text'], 'observed_relation': relation,
                       'intervention': intervention, 'effect_direction': 'UNKNOWN', 'observed_stance': 'UNKNOWN'}
    return {'case_id': case_id, 'candidate_id': candidate['candidate_id'], 'paper_id': facts['document_id'],
            'model': None, 'prompt_version': VERSION, 'transport_version': VERSION,
            'transport_result': 'V3_TRANSPORT_VALID', 'enrichment': observation,
            'model_call_count': 0, 'input_tokens': 0, 'output_tokens': 0, 'latency_ms': 0,
            'retry_count': 0, 'token_usage_complete': True, 'replayed': False, 'artifact_origin': 'GENERATED_NOW',
            'trial_facts': {k: v for k, v in facts.items() if k != 'units'}}
