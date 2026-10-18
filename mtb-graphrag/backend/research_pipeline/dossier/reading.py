"""Pure reading aids. Literal comparisons never establish clinical applicability.

Built at the public boundary, independently of recorded scientific admissions.
Indexes bind the guide to the canonical entry order; no evidence is discarded.
"""
from __future__ import annotations

import json
import re
from typing import Any

VERSION = 'dossier-reading/1.0'
VERIFICATION_NOTE = (
    'La verifica narrativa controlla la fedeltà al dossier, non la correttezza '
    'scientifica, la completezza delle evidenze o l’applicabilità al paziente.'
)
OUTCOME_NOTE = (
    'La categoria generale non identifica l’endpoint né la misura del beneficio. '
    'Risposta, sopravvivenza e recidiva vanno distinte leggendo la citazione e lo studio.'
)
SNAPSHOT_FIELDS = (
    'title', 'status', 'recruitment_status', 'phase', 'conditions', 'interventions',
    'arm_groups', 'arm_group_status', 'trial_structure_provenance', 'trial_resolution_status',
)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _compare(left: str | None, right: str | None) -> str:
    if not left or not right:
        return 'NOT_RECORDED'
    return ('SAME_RECORDED_TEXT' if ' '.join(left.casefold().split()) == ' '.join(right.casefold().split())
            else 'DIFFERENT_RECORDED_TEXT')


def normalized_nct(value: Any) -> str | None:
    match = re.fullmatch(r'(?:nct:)?(NCT\d{8})', _text(value) or '', flags=re.IGNORECASE)
    return match[1].upper() if match else None


def source_url(value: Any) -> str | None:
    value = _text(value) or ''
    if re.fullmatch(r'pmid:\d+', value, re.IGNORECASE):
        return f'https://pubmed.ncbi.nlm.nih.gov/{value.split(":")[1]}/'
    match = re.fullmatch(r'(?:pmcid:)?(PMC\d+)', value, re.IGNORECASE)
    if match:
        return f'https://pmc.ncbi.nlm.nih.gov/articles/{match[1].upper()}/'
    nct = normalized_nct(value)
    return f'https://clinicaltrials.gov/study/{nct}' if nct else None


def _finding(context: dict, finding: dict, paper_index: int, finding_index: int) -> dict:
    observed = finding.get('observed') or {}
    requested_disease, observed_disease = _text(context.get('disease')), _text(observed.get('disease'))
    requested_drug, observed_drug = _text(context.get('intervention')), _text(observed.get('intervention'))
    disease_comparison = _compare(requested_disease, observed_disease)
    drug_comparison = _compare(requested_drug, observed_drug)
    notices = []

    def notice(code: str, message: str) -> None:
        notices.append({'code': code, 'message': message})

    if disease_comparison == 'DIFFERENT_RECORDED_TEXT':
        notice('DISEASE_DESCRIPTIONS_DIFFER', 'Descrizioni della patologia diverse: verificare popolazione, stadio e contesto terapeutico nella fonte. La differenza testuale non stabilisce incompatibilità clinica.')
    elif disease_comparison == 'NOT_RECORDED':
        notice('DISEASE_COMPARISON_UNAVAILABLE', 'Confronto della patologia non disponibile: manca la descrizione del caso o quella estratta dalla fonte.')
    if drug_comparison == 'DIFFERENT_RECORDED_TEXT':
        notice('INTERVENTION_DESCRIPTIONS_DIFFER', 'Intervento richiesto e intervento osservato hanno descrizioni diverse. Non è stabilita equivalenza fra farmaci o regimi.')
    elif drug_comparison == 'NOT_RECORDED':
        notice('INTERVENTION_COMPARISON_UNAVAILABLE', 'Confronto dell’intervento non disponibile: manca una delle descrizioni registrate.')
    if observed.get('molecular_composition') == 'ALTERNATIVES':
        notice('MOLECULAR_ALTERNATIVES', 'La fonte comprende varianti alternative o coorti distinte: un risultato aggregato non dimostra un effetto specifico per la singola variante.')
    if _text(observed.get('effect_direction')):
        notice('BROAD_OUTCOME_CATEGORY', OUTCOME_NOTE)
    checks = finding.get('checks') or {}
    structural = (checks.get('structural') or {}).get('status')
    semantic = (checks.get('semantic') or {}).get('status')
    if structural in (None, '', 'NOT_RECORDED'):
        notice('STRUCTURAL_CHECK_NOT_RECORDED', 'Controllo strutturale non registrato: non può essere letto come controllo superato.')
    if semantic == 'NOT_REQUIRED_BY_POLICY':
        notice('SEMANTIC_CHECK_NOT_REQUIRED', 'La policy non richiede la verifica semantica per questo record; tale verifica non è attestata come eseguita.')
    elif semantic in (None, '', 'NOT_RECORDED', 'NOT_EXECUTED'):
        notice('SEMANTIC_CHECK_NOT_EXECUTED', 'Verifica semantica non eseguita o non registrata; la citazione autentica non certifica l’interpretazione.')
    elif semantic == 'TECHNICAL_ERROR':
        notice('SEMANTIC_CHECK_TECHNICAL_ERROR', 'Verifica semantica interrotta da un errore tecnico: nessuna conferma scientifica è stabilita da questo controllo.')
    return {
        'paper_index': paper_index, 'finding_index': finding_index,
        'candidate_id': finding.get('candidate_id'), 'evidence_id': finding.get('evidence_id'),
        'requested_disease': requested_disease, 'observed_disease': observed_disease,
        'requested_intervention': requested_drug, 'observed_intervention': observed_drug,
        'disease_text_comparison': disease_comparison, 'intervention_text_comparison': drug_comparison,
        'notices': notices,
    }


def build_reading_guide(dossier: dict[str, Any]) -> dict[str, Any]:
    context = dossier.get('case_summary') or {}
    findings = [_finding(context, finding, pi, fi)
                for pi, entry in enumerate(dossier.get('paper_evidence') or [])
                for fi, finding in enumerate(entry.get('documentary_findings') or [])]
    groups: dict[str, dict] = {}
    snapshots: dict[str, set[str]] = {}
    trials = dossier.get('clinical_trials') or []
    for index, entry in enumerate(trials):
        nct = normalized_nct(entry.get('nct_id'))
        key = nct or f'unidentified:{index}'
        if key not in groups:
            groups[key] = {'nct_id': nct, 'entry_indexes': [], 'snapshot_indexes': [], 'conflicting_snapshots': False}
            snapshots[key] = set()
        group = groups[key]
        group['entry_indexes'].append(index)
        snapshot = json.dumps({field: entry.get(field) for field in SNAPSHOT_FIELDS}, sort_keys=True, ensure_ascii=False)
        if snapshot not in snapshots[key]:
            snapshots[key].add(snapshot)
            group['snapshot_indexes'].append(index)
        group['conflicting_snapshots'] = len(group['snapshot_indexes']) > 1
    return {
        'version': VERSION, 'clinical_applicability': 'NOT_EVALUATED',
        'verification_note': VERIFICATION_NOTE, 'findings': findings,
        'trial_groups': list(groups.values()), 'trial_association_count': len(trials),
        'identified_study_count': sum(group['nct_id'] is not None for group in groups.values()),
        'unidentified_trial_association_count': sum(group['nct_id'] is None for group in groups.values()),
    }
