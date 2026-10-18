"""Cheap, auditable planning before per-document neural selection."""
import os
import re

VERSION = 'document-plan/1.0'


def focused_enabled() -> bool:
    value = os.getenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', '').strip()
    if value not in {'', 'legacy', 'focused-v1'}:
        raise ValueError('Unsupported RESEARCH_PIPELINE_DOCUMENTARY_PROFILE')
    return value == 'focused-v1'


def plan_documents(records: list, units_by_document: dict, intent: dict, max_documents: int | None) -> dict:
    if max_documents is not None and (type(max_documents) is not int or max_documents < 1):
        raise ValueError('Document limit must be positive or None')
    labels = list(intent.get('case_question', {}).get('interventions', []))
    target = intent.get('candidate_target', {})
    for item in target.get('interventions', []):
        labels.append(str(item.get('label') or item.get('normalized_value') or item.get('raw_value') or ''))
    for item in target.get('biomarkers', []):
        labels.extend(str(item.get(key) or '') for key in ('gene', 'alteration', 'label'))
    terms = set(re.findall(r'[a-z0-9]+', ' '.join(labels).lower())) - {'and', 'or', 'of', 'the', 'with', 'combination'}
    unique, duplicates, scores = {}, [], {}
    for record in records:
        if record.document_id in unique:
            duplicates.append(record)
            continue
        unique[record.document_id] = record
        metadata = ' '.join(str(u.get('text') or '') for u in units_by_document.get(record.document_id, [])
                            if u.get('unit_type') in {'TITLE', 'ABSTRACT', 'ABSTRACT_SECTION', 'TRIAL_TITLE', 'BRIEF_SUMMARY'})
        scores[record.document_id] = len(terms & set(re.findall(r'[a-z0-9]+', metadata.lower())))
    ordered = sorted(unique.values(), key=lambda r: (-scores[r.document_id], not r.full_text_available, r.document_id, r.bundle_id))
    selected = ordered if max_documents is None else ordered[:max_documents]
    deferred = [] if max_documents is None else ordered[max_documents:]
    return {'version': VERSION, 'selected': selected, 'deferred': deferred, 'duplicates': duplicates,
            'scores': scores, 'basis': 'METADATA_QUERY_TERM_COVERAGE_NOT_CLINICAL_APPLICABILITY'}
