"""Pure, closed-vocabulary Italian realization of canonical narrative facts.

This proves correspondence to the projected dossier, not clinical truth.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

CONTROLLED_VERSION = 'controlled-narrative/2.0'
CONTROLLED_CONTRACT_VERSION = CONTROLLED_VERSION

_STATUS = {
    'STRONG_SUPPORT': 'supporto documentale forte',
    'FULL_SUPPORT': 'supporto documentale completo',
    'PARTIAL_SUPPORT': 'supporto documentale parziale',
    'NO_SUPPORT': 'assenza di supporto documentale',
    'CONTRADICTORY': 'evidenza documentale contraddittoria',
    'UNVERIFIABLE': 'supporto documentale non verificabile',
    'INSUFFICIENT_INFORMATION': 'informazioni insufficienti per stabilire il supporto documentale',
    'DIRECT': 'stato diretto nel dossier',
    'AMBIGUOUS': 'stato ambiguo, senza supporto stabilito',
    'CONTRADICTED': 'stato contraddetto',
    'NO_MATCH': 'nessuna corrispondenza documentale',
    'CONTEXT_ONLY': 'solo contesto',
    'KG_ONLY': 'relazione presente soltanto nel grafo',
}
_WARNING = {
    'NO_VALIDATED_ENRICHMENT_AVAILABLE': 'Non è disponibile un arricchimento validato.',
    'VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION': 'L’arricchimento validato non affronta la direzione della relazione.',
    'SOURCE_POLARITY_DOES_NOT_SUPPORT': 'La polarità della fonte non supporta la relazione.',
    'SOURCE_POLARITY_CONTRADICTS': 'La polarità della fonte contraddice la relazione.',
    'SOURCE_POLARITY_NEUTRAL': 'La polarità della fonte è neutra e non stabilisce supporto.',
    'TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE': 'L’associazione al trial non costituisce evidenza di efficacia.',
    'DOCUMENT_PROVENANCE_NOT_AVAILABLE': 'La provenienza documentale non è disponibile.',
}
_DIRECTION = {
    'Supports': 'Direzione dichiarata dal grafo: Supports; questo valore non stabilisce supporto documentale.',
    'Does Not Support': 'Direzione dichiarata dal grafo: Does Not Support; questo valore non prova la direzione clinica opposta.',
    'SUPPORTED': 'La direzione è supportata nel dossier.',
    'SOURCE_DOES_NOT_SUPPORT': 'La fonte non supporta la direzione della relazione.',
    'CONTRADICTED': 'La direzione è contraddetta.',
    'NO_DOCUMENT_SIGNAL': 'Non è presente un segnale documentale per la direzione.',
    'UNRELATED_EVIDENCE': 'L’evidenza non riguarda la direzione della relazione.',
}
# Graph directions from gca_v3.polarity, plus the legacy non-applicable value.
# They describe the graph assertion, and never imply document support.
_GRAPH_DIRECTIONS = frozenset({
    'SENSITIVITY', 'RESISTANCE', 'REDUCED_SENSITIVITY', 'ADVERSE_RESPONSE',
    'BETTER_OUTCOME', 'POOR_OUTCOME', 'POSITIVE', 'NEGATIVE', 'PREDISPOSITION',
    'PROTECTIVENESS', 'ONCOGENICITY', 'GAIN_OF_FUNCTION', 'LOSS_OF_FUNCTION',
    'DOMINANT_NEGATIVE', 'NEOMORPHIC', 'UNALTERED_FUNCTION',
    'UNCERTAIN_SIGNIFICANCE', 'UNKNOWN', 'UNMAPPED_SOURCE_VALUE', 'NOT_APPLICABLE',
})
# Historical relation projection preserves source spelling rather than the
# later graph enum. This finite map does not authorize arbitrary prose.
_LEGACY_GRAPH_DIRECTIONS = {
    value.replace('_', ' ').title(): value for value in _GRAPH_DIRECTIONS
}
_LEGACY_GRAPH_DIRECTIONS['Sensitivity/Response'] = 'SENSITIVITY'
_LIMITATION = {
    **_WARNING,
    'PAPER_SUPPORT_NOT_EVALUATED': 'Il supporto documentale non è stato valutato.',
    'CANDIDATE_PARTIALLY_SUPPORTED': 'Il dossier contiene una relazione con supporto parziale.',
    'DOCUMENT_UNAVAILABLE': 'Il dossier segnala un documento non disponibile.',
    'READER_ABSTAINED': 'Il Reader si è astenuto dalla valutazione.',
    'QUOTE_INVALID': 'Il dossier segnala una citazione non valida; il testo scartato non viene riportato.',
    'TRIAL_RECORD_UNAVAILABLE': 'Il record del trial non è disponibile.',
}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f'Malformed {field}')
    return value


def _label(value: Any) -> str:
    if value is None: return ''
    if isinstance(value, str): return value
    if isinstance(value, dict):
        label = value.get('label') or value.get('name') or value.get('id')
        if isinstance(label, str): return label
    if isinstance(value, list): return ', '.join(_label(x) for x in value)
    raise ValueError('Malformed canonical label')


def _documentary_text(candidate: dict) -> str:
    """Closed realization: reported fields and process, never an aggregate verdict."""
    parts = [f"Relazione {candidate['candidate_id']} ({candidate['branch']}): osservazioni documentali e controlli registrati."]
    target = candidate.get('documentary_target') or {}
    if target:
        parts.append('Target della ricerca nel grafo: ' + json.dumps(target, ensure_ascii=False, sort_keys=True) + '.')
    for finding in candidate.get('documentary_findings') or []:
        parts.append('Record ' + str(finding.get('evidence_id') or 'senza ID') + ': ' + str(finding.get('disposition')) + '.')
        parts.append('Fonte e SourceUnit registrate: ' + json.dumps(finding.get('source') or {}, ensure_ascii=False, sort_keys=True) + '.')
        if finding.get('quotation') and finding.get('disposition') == 'RETAINED_RECORD':
            parts.append('Citazione letterale della fonte: ' + json.dumps(finding['quotation'], ensure_ascii=False) + '.')
        if finding.get('observed') and finding.get('disposition') == 'RETAINED_RECORD':
            parts.append('Campi estratti dal Reader, non annotazioni indipendenti: ' + json.dumps(finding['observed'], ensure_ascii=False, sort_keys=True) + '.')
        parts.append('Controlli registrati: ' + json.dumps(finding.get('checks') or {}, ensure_ascii=False, sort_keys=True) + '.')
        parts.append('Limitazioni del record: ' + json.dumps(finding.get('limitations') or {}, ensure_ascii=False, sort_keys=True) + '.')
    if not candidate.get('documentary_findings'):
        parts.append('Nessuna osservazione documentale conservata per questa relazione.')
    if candidate.get('documentary_attempts'):
        parts.append('Tentativi Reader registrati: ' + json.dumps(candidate['documentary_attempts'], ensure_ascii=False, sort_keys=True) + '.')
    if candidate['branch'] == 'TRIAL':
        parts.append('Informazioni del registro: ' + json.dumps(candidate.get('trial_context') or {}, ensure_ascii=False, sort_keys=True) + '. Associazione a trial, non prova di efficacia; eleggibilita individuale non valutata.')
    if candidate['branch'] == 'KG_ONLY':
        parts.append('Solo provenienza del grafo: ' + json.dumps(candidate.get('kg_context') or {}, ensure_ascii=False, sort_keys=True) + '.')
    parts.append('Correttezza scientifica non valutata indipendentemente; applicabilita clinica non valutata.')
    return ' '.join(parts)


def build_catalog(narrator_input: dict) -> dict:
    """Build mandatory candidate facts in original order, without external state."""
    if not isinstance(narrator_input, dict) or not isinstance(narrator_input.get('candidates'), list):
        raise ValueError('Malformed candidates')
    limits = _strings(narrator_input.get('limitations', []), 'limitations')
    limit_text = ' '.join(
        f'{_LIMITATION[code]} [Limite canonico: {json.dumps(code, ensure_ascii=False)}]'
        if code in _LIMITATION else f'Il dossier registra il seguente limite canonico, senza interpretazione aggiuntiva: {json.dumps(code, ensure_ascii=False)}.'
        for code in limits
    )
    entries = []; seen = set(); counts = {'PAPER': 0, 'TRIAL': 0, 'KG_ONLY': 0}
    for candidate in narrator_input['candidates']:
        if not isinstance(candidate, dict): raise ValueError('Malformed candidate')
        cid = candidate.get('candidate_id'); status = candidate.get('canonical_status')
        if not isinstance(cid, str) or not cid.strip() or cid in seen: raise ValueError('Invalid or duplicate candidate identity')
        seen.add(cid)
        branch = candidate.get('branch', 'PAPER')
        if candidate.get('documentary_contract_version'):
            if branch not in counts:
                raise ValueError('Unknown documentary branch')
            counts[branch] += 1
            text = _documentary_text(candidate)
            entries.append({'fact_id': 'f_' + _hash(candidate)[:24], 'candidate_id': cid,
                            'branch': branch, 'variants': {'concise': text, 'detailed': text + ' Autenticazione, corrispondenza e completezza della run sono dimensioni distinte.'}})
            continue
        if not isinstance(branch, str) or not isinstance(status, str) or branch not in counts or status not in _STATUS: raise ValueError('Unknown branch or status')
        if branch == 'TRIAL' and status != 'CONTEXT_ONLY': raise ValueError('Unknown trial status')
        if branch == 'KG_ONLY' and status != 'KG_ONLY': raise ValueError('Unknown graph status')
        if 'branch' not in candidate and status not in {'DIRECT','AMBIGUOUS','CONTRADICTED','NO_MATCH'}:
            raise ValueError('Ambiguous legacy candidate')
        counts[branch] += 1
        warnings = _strings(candidate.get('critical_warnings', []), 'critical_warnings')
        if any(w not in _WARNING for w in warnings): raise ValueError('Unknown critical warning')
        warnings = warnings + [w for w in _strings(candidate.get('warnings', []), 'warnings') if w in _WARNING and w not in warnings]
        parts = [f'Relazione {cid} ({branch}): {_STATUS[status]}.']
        composition = candidate.get('evidence_composition') or {}
        if composition:
            if not isinstance(composition, dict): raise ValueError('Malformed evidence composition')
            parts.append(f"Composizione delle evidenze ammesse: {composition.get('record_count', 0)} record da {composition.get('unique_publication_count', 0)} pubblicazioni distinte.")
            for state, count in (composition.get('counts_by_support_result') or {}).items():
                if count: parts.append(f'{state}: {count} record.')
            if composition.get('mixed_support'): parts.append('Gli esiti dei record sono misti; lo stato aggregato non descrive ogni singolo record.')
        context = candidate.get('kg_context') or {}
        if not isinstance(context, dict): raise ValueError('Malformed graph context')
        branch_entries = narrator_input.get({'PAPER': 'paper_evidence', 'TRIAL': 'clinical_trials', 'KG_ONLY': 'kg_only_relations'}[branch], [])
        if not isinstance(branch_entries, list): raise ValueError('Malformed branch entries')
        matches = [e for e in branch_entries if isinstance(e, dict) and e.get('candidate_id') == cid]
        if len(matches) > 1: raise ValueError('Duplicate branch candidate identity')
        if matches: context = {**matches[0], **context}
        if branch == 'PAPER':
            if context.get('document_resolution_status') in ('UNAVAILABLE', 'DOCUMENT_UNAVAILABLE'):
                parts.append('Il documento non è disponibile (DOCUMENT_UNAVAILABLE).')
            if context.get('reader_status') == 'ABSTAIN' or context.get('reader_decision') == 'ABSTAIN':
                parts.append('Il Reader si è astenuto dalla valutazione di questa relazione (READER_ABSTAINED).')
            validation = context.get('quote_validation') or {}
            # Dossier builder emits validation_outcome/outcome as a string;
            # older projections may carry the structured validation object.
            if isinstance(validation, str): validation = {'status': validation}
            if not isinstance(validation, dict): raise ValueError('Malformed quote validation')
            invalid_quote = (context.get('quote_valid') is False and context.get('reader_status') != 'ABSTAIN' and context.get('reader_decision') != 'ABSTAIN') or validation.get('status') in ('REJECTED', 'INVALID', 'REJECTED_QUOTE') or validation.get('valid') is False
            if invalid_quote:
                parts.append('La citazione proposta è non valida e non viene riportata (QUOTE_INVALID).')
                if candidate.get('validated_quotes'): raise ValueError('Conflicting validated quote and rejected source quote')
        labels = [_label(context.get(k)) for k in ('subject','object','disease_context')]
        drug = _label(candidate.get('drug'))
        if drug: parts.append(f'Intervento indicato nel dossier: {drug}.')
        if any(labels): parts.append('Entità del grafo: ' + '; '.join(x for x in labels if x) + '.')
        relation = candidate.get('graph_relation', '')
        if not isinstance(relation, str): raise ValueError('Malformed relation')
        if relation: parts.append(f'Relazione dichiarata dal grafo: {relation}.')
        direction = candidate.get('support_direction', '')
        if not isinstance(direction, str): raise ValueError('Malformed direction')
        if direction:
            if direction in _DIRECTION: parts.append(_DIRECTION[direction])
            elif direction in _GRAPH_DIRECTIONS or direction in _LEGACY_GRAPH_DIRECTIONS: parts.append(f'Direzione della dichiarazione del grafo: {direction}; questo valore non stabilisce supporto documentale.')
            else: raise ValueError('Unknown direction')
        if candidate.get('contradiction_present'): parts.append('Il dossier segnala la presenza di una contraddizione.')
        support = candidate.get('candidate_support')
        if support is not None:
            if not isinstance(support, dict) or support.get('result') not in _STATUS: raise ValueError('Unknown support status')
            parts.append(f'Esito della verifica di supporto: {_STATUS[support["result"]]}.')
        checks = candidate.get('candidate_support_checks', [])
        if not isinstance(checks, list): raise ValueError('Malformed support checks')
        for check in checks:
            if not isinstance(check, dict) or check.get('candidate_id') != cid: raise ValueError('Foreign support check')
            checked = check.get('candidate_support')
            if not isinstance(checked, dict) or not isinstance(checked.get('result'), str) or checked['result'] not in _STATUS:
                raise ValueError('Unknown scoped support status')
            identities = [check.get(k, '') for k in ('paper_id', 'document_id', 'source_unit_id')]
            if any(not isinstance(v, str) for v in identities): raise ValueError('Malformed scoped source identity')
            parts.append('Verifica documentale per ' + '; '.join(v for v in identities if v) + ': ' + _STATUS[checked['result']] + '.')
        if branch == 'TRIAL':
            trial = candidate.get('trial_context') or {}
            if not isinstance(trial, dict): raise ValueError('Malformed trial context')
            for key, label in (('nct_id','Identificativo trial'), ('title','Titolo del registro'), ('conditions','Condizioni nel registro'), ('interventions','Interventi nel registro'), ('phase','Fase nel registro'), ('status','Stato nel registro')):
                value = _label(trial.get(key))
                if value: parts.append(f'{label}: {value}.')
            parts.extend([_WARNING['TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE'], 'L’eleggibilità del paziente è non valutata (NOT_EVALUATED).', 'La disponibilità della fonte del registro non è assunta.'])
            if trial.get('eligibility_status') not in (None, '', 'NOT_EVALUATED'): raise ValueError('Unknown eligibility status')
        elif branch == 'KG_ONLY': parts.append(_WARNING['DOCUMENT_PROVENANCE_NOT_AVAILABLE'])
        refs = _strings(candidate.get('selected_paper_ids', []), 'selected_paper_ids') + _strings(candidate.get('source_refs', []), 'source_refs')
        if refs: parts.append('Identificativi di provenienza dichiarati: ' + '; '.join(dict.fromkeys(refs)) + '. La disponibilità del documento non è assunta.')
        quotes = candidate.get('validated_quotes', [])
        if not isinstance(quotes, list): raise ValueError('Malformed quotes')
        for quote in quotes:
            if not isinstance(quote, dict) or any(not isinstance(quote.get(k), str) or not quote[k] for k in ('quote','paper_id','source_unit_id')): raise ValueError('Malformed bound quote')
            parts.append(f'Dichiarazione letterale della fonte {quote["paper_id"]}, SourceUnit {quote["source_unit_id"]}: «{quote["quote"]}». Questa citazione è una dichiarazione della fonte, non una conclusione di efficacia del sistema.')
            record_support = quote.get('support_result')
            if record_support:
                if record_support not in _STATUS: raise ValueError('Unknown quote support status')
                parts.append(f'Esito del record: {_STATUS[record_support]}.')
        required_limitations = candidate.get('required_limitations', [])
        if not isinstance(required_limitations, list): raise ValueError('Malformed required limitations')
        for limitation in required_limitations:
            if not isinstance(limitation, dict) or not isinstance(limitation.get('text'), str) or not limitation['text'].strip():
                raise ValueError('Malformed evidence limitation')
            identity = '; '.join(v for v in (
                limitation.get('evidence_id'), limitation.get('paper_id'), limitation.get('source_unit_id')
            ) if isinstance(v, str) and v)
            parts.append(f'Limitazione associata a {identity}: {limitation["text"]}.')
        parts.extend(_WARNING[w] for w in warnings if _WARNING[w] not in parts)
        text = ' '.join(parts)
        entries.append({'fact_id': 'f_' + _hash({'candidate': candidate, 'bound_context': context})[:24], 'candidate_id': cid, 'branch': branch, 'variants': {'concise': text, 'detailed': text + ' Questa descrizione conserva lo stato e la provenienza canonici della relazione.'}})
    catalog: dict[str, Any] = {'version': CONTROLLED_VERSION, 'entries': entries, 'globals': {
        'narrative_summary': f'Il dossier comprende {len(entries)} relazioni: {counts["PAPER"]} PAPER, {counts["TRIAL"]} TRIAL e {counts["KG_ONLY"]} KG_ONLY. L’ordine segue il dossier canonico.',
        'limitations_summary': 'La narrazione riflette esclusivamente gli stati verificati nel dossier. Le associazioni ai trial non dimostrano efficacia; l’eleggibilità non è valutata. Le relazioni del solo grafo non hanno provenienza documentale. La disponibilità delle fonti non è assunta.' + (' ' + limit_text if limit_text else ''),
        'closing_note': 'Questa sintesi non costituisce una raccomandazione terapeutica e non verifica la correttezza clinica delle fonti.'}}
    publication = narrator_input.get('publication') or {}
    if publication:
        catalog['globals']['narrative_summary'] += f" Stato di pubblicazione: {publication.get('publication_status') or 'UNKNOWN'}; esecuzione: {publication.get('technical_run_status') or 'UNKNOWN'}; riconciliazione: {publication.get('reconciliation_status') or 'UNKNOWN'}."
    catalog['catalog_hash'] = _hash(catalog)
    return catalog


def default_plan(catalog: dict) -> dict:
    return {'catalog_hash': catalog['catalog_hash'], 'entries': [{'fact_id': e['fact_id'], 'variant': 'concise'} for e in catalog['entries']]}


def validate_plan(catalog: dict, plan: dict) -> list[str]:
    errors = []
    if not isinstance(plan, dict) or set(plan) != {'catalog_hash','entries'}: return ['CONTROLLED_PLAN_SHAPE_INVALID']
    if plan['catalog_hash'] != catalog['catalog_hash']: errors.append('CONTROLLED_CATALOG_HASH_MISMATCH')
    choices = plan['entries']
    if not isinstance(choices, list): return errors + ['CONTROLLED_PLAN_SHAPE_INVALID']
    if len(choices) != len(catalog['entries']): errors.append('CONTROLLED_FACT_COVERAGE_INVALID')
    for index, choice in enumerate(choices):
        if not isinstance(choice, dict) or set(choice) != {'fact_id','variant'}:
            errors.append('CONTROLLED_PLAN_SHAPE_INVALID'); continue
        if index >= len(catalog['entries']) or choice['fact_id'] != catalog['entries'][index]['fact_id']:
            errors.append('CONTROLLED_FACT_ORDER_OR_ID_INVALID'); continue
        if not isinstance(choice['variant'], str) or choice['variant'] not in catalog['entries'][index]['variants']:
            errors.append('CONTROLLED_VARIANT_INVALID')
    return sorted(set(errors))


def render_plan(catalog: dict, plan: dict) -> dict:
    errors = validate_plan(catalog, plan)
    if errors: raise ValueError(', '.join(errors))
    return {**deepcopy(catalog['globals']), 'candidate_narratives': [{'candidate_id': entry['candidate_id'], 'text': entry['variants'][choice['variant']]} for entry, choice in zip(catalog['entries'], plan['entries'])], 'controlled_contract': {'version': CONTROLLED_VERSION, 'catalog_hash': catalog['catalog_hash'], 'plan': deepcopy(plan)}}


def verify_controlled(narrator_input: dict, narrative: dict) -> dict:
    """Independently rebuild and compare every authoritative field exactly."""
    errors = []; results = []; catalog = None
    try:
        catalog = build_catalog(narrator_input)
        if not isinstance(narrative, dict): raise ValueError('Narrative shape')
        contract = narrative.get('controlled_contract')
        if not isinstance(contract, dict) or set(contract) != {'version','catalog_hash','plan'}: raise ValueError('Contract shape')
        if contract['version'] != CONTROLLED_VERSION: errors.append('CONTROLLED_VERSION_MISMATCH')
        if contract['catalog_hash'] != catalog['catalog_hash']: errors.append('CONTROLLED_CATALOG_HASH_MISMATCH')
        errors.extend(validate_plan(catalog, contract['plan']))
        if not errors:
            expected = render_plan(catalog, contract['plan'])
            for key in expected:
                if narrative.get(key) != expected[key]: errors.append('CONTROLLED_RENDER_MISMATCH')
            allowed_metadata = {'case_id','language','generation_origin','narrator_input_hash','prompt_version','transport_version','model','timestamp','narrative_hash'}
            if set(narrative) - set(expected) - allowed_metadata: errors.append('CONTROLLED_NARRATIVE_SHAPE_INVALID')
            if 'narrator_input_hash' in narrative and narrator_input.get('narrator_input_hash') is not None and narrative['narrator_input_hash'] != narrator_input['narrator_input_hash']:
                errors.append('CONTROLLED_INPUT_HASH_MISMATCH')
            if 'narrative_hash' in narrative and narrative['narrative_hash'] != _hash({key: narrative.get(key) for key in ('narrative_summary', 'candidate_narratives', 'limitations_summary', 'closing_note')}):
                errors.append('CONTROLLED_NARRATIVE_HASH_MISMATCH')
            for entry, actual in zip(expected['candidate_narratives'], narrative.get('candidate_narratives') or []):
                results.append({'candidate_id': entry['candidate_id'], 'narrated': actual == entry, 'status': 'PASS' if actual == entry else 'FAIL'})
    except (ValueError, TypeError, KeyError):
        errors.append('CONTROLLED_CONTRACT_UNPROVEN')
    input_hash = narrator_input.get('narrator_input_hash') if isinstance(narrator_input, dict) else None
    authoritative_hash = None
    if isinstance(narrative, dict):
        try:
            authoritative_hash = _hash({key: narrative.get(key) for key in ('narrative_summary', 'candidate_narratives', 'limitations_summary', 'closing_note')})
        except (ValueError, TypeError):
            pass
    return {'status': 'FAIL' if errors else 'PASS', 'reason_codes': sorted(set(errors)), 'candidate_results': results, 'verifier_version': CONTROLLED_VERSION, 'catalog_hash': catalog['catalog_hash'] if catalog else None, 'input_hash': input_hash, 'narrative_hash': authoritative_hash, 'verified_at': datetime.now(timezone.utc).isoformat()}
