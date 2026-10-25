"""Research question relevance, separate from a graph assertion's arguments."""
from copy import deepcopy

VERSION = 'selection-intent/1.0'


def build_selection_intent(candidate: dict, verified_case: dict, linked_candidates: list[dict]) -> dict:
    # Linked assertions remain lineage, not an inferred regimen operator.
    targets = verified_case.get('target_interventions') or []
    if not targets and verified_case.get('target_intervention'):
        targets = [verified_case['target_intervention']]
    labels = []
    for target in targets:
        if not isinstance(target, dict) or target.get('assertion_status') in {'NEGATED', 'ABSENT', 'REJECTED'}:
            continue
        label = target.get('normalized_value') or target.get('raw_value')
        if isinstance(label, str) and label.strip() and label.strip() not in labels:
            labels.append(label.strip())
    return {'version': VERSION,
            'candidate_target': {'interventions': deepcopy(candidate.get('interventions') or []),
                                 'biomarkers': deepcopy(candidate.get('biomarkers') or [])},
            'case_question': {'interventions': labels},
            'field_lineage': {'candidate_target': 'GRAPH_ASSERTION', 'case_question.interventions': 'VERIFIED_CASE'},
            'linked_candidate_ids': [c['candidate_id'] for c in linked_candidates if c.get('candidate_id')],
            'unresolved': ['REGIMEN_OPERATOR_NOT_INFERRED_FROM_DRUG_EDGES'] if linked_candidates else []}
