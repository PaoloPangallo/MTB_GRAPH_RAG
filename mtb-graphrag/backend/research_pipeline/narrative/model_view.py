"""One presentation view of retained facts; the canonical verification input stays intact."""
from __future__ import annotations

from copy import deepcopy

VERSION = 'dossier-model-view/1.0'


def branch_scope_text(candidate: dict) -> str:
    """Plain, source-bound context for branches with no therapeutic conclusion."""
    branch = candidate.get('branch')
    if branch == 'TRIAL':
        trial = candidate.get('trial_context') or {}
        if trial.get('evidence_interpretation') != 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE':
            return ''
        identity = trial.get('nct_id')
        if not identity:
            return ''
        parts = [f'Il registro descrive lo studio {identity}.']
        conditions = trial.get('conditions') or []
        if conditions:
            parts.append('Le condizioni riportate sono ' + ' e '.join(str(value) for value in conditions) + '.')
        parts.append('L’associazione a trial non costituisce prova di efficacia.')
        if trial.get('eligibility_status') == 'NOT_EVALUATED':
            parts.append('L’eleggibilità del paziente non è stata valutata.')
        return ' '.join(parts)
    if branch == 'KG_ONLY':
        context = candidate.get('kg_context') or {}
        subject = (context.get('subject') or {}).get('label')
        obj = (context.get('object') or {}).get('label')
        if not subject or not obj:
            return ''
        parts = [f'Il Knowledge Graph collega {subject} e {obj}.']
        diagnostic = context.get('diagnostic_context') or {}
        if diagnostic.get('drug'):
            parts.append('Il contesto registrato indica il farmaco ' + str(diagnostic['drug']) + '.')
        parts.append('La provenienza disponibile è il Knowledge Graph.')
        return ' '.join(parts)
    return ''


def _target(target: dict) -> dict:
    result = deepcopy(target)
    result.pop('graph_provenance', None)
    # An Evidence label is the graph's search hypothesis, not a source finding.
    obj = result.get('object') or {}
    if isinstance(obj, dict) and obj.get('type') in {'Evidence', 'EvidenceStatement'}:
        obj.pop('label', None)
    return result


def model_view(source: dict) -> dict:
    view = {key: deepcopy(value) for key, value in source.items()
            if key not in {'paper_evidence', 'clinical_trials', 'kg_only_relations', 'candidates'}}
    if not source.get('documentary_contract_version'):
        view['candidates'] = deepcopy(source.get('candidates') or [])
        return view
    view['model_view_version'] = VERSION
    view['candidates'] = []
    keys = ('candidate_id', 'branch', 'drug', 'graph_relation', 'canonical_status',
            'documentary_contract_version', 'warnings', 'critical_warnings',
            'required_limitations', 'abstention_reasons', 'source_cards', 'narration_observations')
    for candidate in source.get('candidates') or []:
        row = {key: deepcopy(candidate[key]) for key in keys if key in candidate}
        row['documentary_target'] = _target(candidate.get('documentary_target') or {})
        row['documentary_attempts'] = [
            {key: deepcopy(attempt[key]) for key in ('source', 'disposition', 'reason_codes',
                'abstain_reason', 'rejection_reason', 'status') if key in attempt}
            for attempt in candidate.get('documentary_attempts') or [] if isinstance(attempt, dict)]
        for name in ('trial_context', 'kg_context'):
            if name in candidate:
                row[name] = deepcopy(candidate[name])
                row[name].pop('graph_provenance', None)
                if name == 'kg_context':
                    for node in ('subject', 'object'):
                        if isinstance(row[name].get(node), dict):
                            row[name][node].pop('id', None)
                    (row[name].get('diagnostic_context') or {}).pop('device_id', None)
        scope = branch_scope_text(candidate)
        if scope:
            row['branch_scope_text'] = scope
        view['candidates'].append(row)
    return view
