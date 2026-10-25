"""Deterministic observation inventory and bounded narration coverage checks."""
from copy import deepcopy
from hashlib import sha256
import json


def narration_observations(candidate: dict) -> list[dict]:
    records = []
    if 'documentary_findings' in candidate:
        for finding in candidate.get('documentary_findings') or []:
            if finding.get('disposition') != 'RETAINED_RECORD':
                continue
            record = {key: deepcopy(finding.get(key)) for key in (
                'evidence_id', 'source', 'observed', 'checks', 'limitations',
                'observed_origin', 'clinical_applicability', 'scientific_correctness')}
            record['quotation'] = (finding.get('quotation')
                if (finding.get('checks', {}).get('quotation') or {}).get('status') == 'AUTHENTICATED' else None)
            records.append(record)
    else:
        cards = candidate.get('source_cards')
        if cards is None:
            from .source_cards import build_source_cards
            cards = build_source_cards(candidate)
        records = [{'source': deepcopy(card), 'quotation': card.get('validated_quote'),
                    'observed': {}, 'checks': {}, 'limitations': {}}
                   for card in cards if card.get('validated_quote')]
    result = []
    for index, record in enumerate(records):
        source = record.get('source') or {}
        record['study_id'] = (source.get('public_source_identity') or source.get('document_id')
                              or source.get('paper_id') or 'unresolved-source')
        encoded = json.dumps([candidate.get('candidate_id'), index, record], sort_keys=True, ensure_ascii=False)
        record['observation_id'] = 'OBS-' + sha256(encoded.encode('utf-8')).hexdigest()[:16]
        result.append(record)
    return result


def observation_text(item: dict) -> str:
    return '\n\n'.join(value for value in (item.get('text'), item.get('case_relevance')) if value)


def candidate_text(entry: dict) -> str:
    """Every generated text participates in the same downstream checks."""
    texts = [entry.get('text') or '']
    texts.extend(observation_text(item) for item in entry.get('observation_narratives') or [])
    texts.append((entry.get('study_comparison') or {}).get('text') or '')
    return '\n\n'.join(text for text in texts if text)


def coverage_errors(candidate: dict, entry: dict) -> list[str]:
    observations = candidate.get('narration_observations') or []
    expected = [item['observation_id'] for item in observations]
    actual = [item['observation_id'] for item in entry.get('observation_narratives') or []]
    errors = []
    if sorted(actual) != sorted(expected):
        errors.append('NARRATIVE_OBSERVATION_COVERAGE_MISMATCH')
    comparison = entry.get('study_comparison')
    if len({item['study_id'] for item in observations}) > 1 and not comparison:
        errors.append('NARRATIVE_STUDY_COMPARISON_MISSING')
    if comparison and sorted(comparison['observation_ids']) != sorted(expected):
        errors.append('NARRATIVE_COMPARISON_COVERAGE_MISMATCH')
    return errors
