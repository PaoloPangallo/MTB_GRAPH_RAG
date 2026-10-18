"""Ten transparent narration scenarios; --live performs real model calls.

Synthetic fixtures exercise contracts, not clinical truth. Archived cases reuse
selected canonical rows without rerunning retrieval or changing evidence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.research_pipeline.narrative.controlled import verify_controlled
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.narrator import call_dossier_narrator, narrative_hash
from backend.research_pipeline.narrative.verifier import verify_narrative
from evaluation.run_dossier_narrator_benchmark import build_benchmark


def cases() -> list[dict]:
    benchmark = build_benchmark()
    rows = []
    for index, name in [(0, 'direct'), (6, 'ambiguous'), (12, 'negative_direction'),
                        (18, 'missing_quote'), (24, 'mixed_candidates')]:
        dossier = deepcopy(benchmark[index][1])
        # This suite uses internally consistent synthetic quotations rather than
        # inheriting independently rotated sentences from the historical fixture.
        for candidate in dossier['candidate_therapies']:
            for context in candidate['author_context']:
                if context['presentation_state'] == 'VALIDATED_QUOTE':
                    context['author_claim_quote'] = (
                        'The source does not support the proposed association.' if name == 'negative_direction'
                        else 'The source reports the association examined in this synthetic fixture.')
        rows.append({'name': name, 'origin': 'SYNTHETIC_CONTRACT_FIXTURE', 'dossier': dossier})
    partial = {
        'case_id': 'SYN-PARTIAL',
        'case_summary': {'disease': 'melanoma', 'gene': 'BRAF', 'variant': 'V600K'},
        'paper_evidence': [{'candidate_id': 'P-PARTIAL', 'relation': 'associated_with',
                            'document_id': 'pmid:100', 'quote_valid': False,
                            'support_level': 'PARTIAL_SUPPORT', 'support_fields': {},
                            'warnings': [], 'graph_provenance': {}}],
        'limitations': [],
    }
    rows.append({'name': 'partial_support', 'origin': 'SYNTHETIC_CONTRACT_FIXTURE', 'dossier': partial})
    trial = {'case_id': 'SYN-TRIAL', 'clinical_trials': [{
        'candidate_id': 'T-REGISTRY', 'nct_id': 'NCT00000001',
        'title': 'Synthetic registry fixture', 'conditions': ['melanoma'],
        'interventions': [], 'phase': [], 'status': 'UNKNOWN',
        'trial_resolution_status': 'RESOLVED', 'eligibility_status': 'NOT_EVALUATED',
        'evidence_interpretation': 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE',
        'graph_provenance': {}}], 'limitations': []}
    rows.append({'name': 'registry', 'origin': 'SYNTHETIC_CONTRACT_FIXTURE', 'dossier': trial})
    kg = {'case_id': 'SYN-KG', 'kg_only_relations': [{
        'candidate_id': 'K-GRAPH', 'subject': {'label': 'BRAF'},
        'relation': 'associated_with', 'object': {'label': 'test diagnostico'},
        'verification_status': 'KG_ONLY', 'document_provenance': 'NOT_AVAILABLE',
        'graph_provenance': {}}], 'limitations': []}
    rows.append({'name': 'graph_provenance', 'origin': 'SYNTHETIC_CONTRACT_FIXTURE', 'dossier': kg})
    for case_id in ('E2E20-13', 'E2E20-16'):
        path = REPO.parent / 'experiments_real/remaining_fixes_20261015/live4' / case_id / 'dossier.json'
        raw = path.read_bytes()
        dossier = json.loads(raw)['dossier']
        subset = deepcopy(dossier)
        # A declared small projection keeps these trials about narration rather
        # than generation capacity. Evidence rows are copied byte-for-value.
        subset['paper_evidence'] = deepcopy(dossier.get('paper_evidence', [])[:2])
        subset['clinical_trials'] = []
        subset['kg_only_relations'] = []
        subset['documentary_summary'] = {}  # no stale aggregate from the full archive
        rows.append({'name': case_id.lower() + '_documentary_subset',
                     'origin': 'ARCHIVED_DOSSIER_SELECTED_PAPER_ROWS',
                     'source': path.relative_to(REPO.parent).as_posix(),
                     'source_sha256': sha256(raw).hexdigest(), 'dossier': subset})
    return rows


def mutations(dossier: dict, source: dict, narrative: dict | None) -> list[dict]:
    """Probe actual model text, including text already rejected by the gate."""
    if not narrative or not narrative.get('candidate_narratives'):
        return []
    changes = {
        'new_drug': lambda d: d['candidate_narratives'][0].update(text='Si osserva una risposta a inventatinib.'),
        'new_quantity': lambda d: d['candidate_narratives'][0].update(text='Il tasso di risposta è 87%.'),
        'new_source': lambda d: d['candidate_narratives'][0].update(text='La fonte è PMID:999999999999.'),
        'recommendation': lambda d: d['candidate_narratives'][0].update(text='Si raccomanda di somministrare il trattamento.'),
        'missing_candidate': lambda d: d['candidate_narratives'].pop(0),
        'changed_input_binding': lambda d: d['dossier_narration_contract'].update(input_hash='wrong'),
    }
    rows = []
    for name, change in changes.items():
        altered = deepcopy(narrative)
        change(altered)
        altered['narrative_hash'] = narrative_hash(altered)
        result = verify_narrative(dossier, source, altered)
        rows.append({'mutation': name, 'status': result['status'], 'reason_codes': result['reason_codes']})
    return rows


def write_report(folder: Path, records: list[dict], mode: str):
    summary = {'mode': mode, 'case_count': len(records),
               'model_narratives_passing_checks': sum(r.get('verification', {}).get('status') == 'PASS' for r in records),
               'model_narratives_failing_checks': sum(r.get('verification', {}).get('status') == 'FAIL' for r in records),
               'transport_failures': sum(r.get('transport_result') not in (None, 'FORCED_TOOL_VALID') for r in records),
               'cases': records,
               'limits': ['Rule-based fidelity checks are bounded, not semantic equivalence proofs.',
                          'Synthetic outcomes are contract fixtures, not clinical observations.',
                          'No retrieval or upstream evidence decisions are rerun.',
                          'Mutation failures on an already failing baseline do not establish mutation-specific detection.']}
    (folder / 'results.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Prova del narratore su dieci scenari', '',
             'Modalità: ' + mode + '. Il prompt è in inglese; la spiegazione richiesta è in italiano.', '',
             '| Caso | Origine | Trasporto | Verifica della prosa | Ripiego verificato |',
             '|---|---|---|---|---|']
    for row in records:
        lines.append('| ' + ' | '.join([row['name'], row['origin'], row.get('transport_result', 'PREPARED'),
                                      row.get('verification', {}).get('status', 'NOT_EXECUTED'),
                                      row.get('fallback_verification', {}).get('status', 'NOT_EXECUTED')]) + ' |')
    lines += ['', 'Il superamento indica conformità ai controlli implementati, distinta dalla correttezza clinica e da una prova generale di equivalenza semantica.', '']
    for row in records:
        lines += ['## ' + row['name'], '', 'Esiti: ' + ', '.join(row.get('verification', {}).get('reason_codes', [])), '']
        if row.get('narrative'):
            narrative = row['narrative']
            lines += [narrative['narrative_summary'], '']
            lines.extend(entry['text'] + '\n' for entry in narrative['candidate_narratives'])
            lines += [narrative['limitations_summary'], '', narrative['closing_note'], '']
    (folder / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--reverify', action='store_true', help='Recheck saved model outputs without new calls')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.reverify:
        if args.live:
            parser.error('--reverify and --live are mutually exclusive')
        saved = json.loads((args.out / 'results.json').read_text(encoding='utf-8'))
        for record in saved['cases']:
            source, dossier = record['narrator_input'], record['canonical_dossier']
            record.setdefault('original_verification', record.get('verification'))
            record['verification'] = verify_narrative(dossier, source, record.get('narrative'))
            record['mutations'] = mutations(dossier, source, record.get('narrative'))
            record['verification_mode'] = 'RECHECKED_SAVED_MODEL_OUTPUT'
        write_report(args.out, saved['cases'], saved['mode'])
        print('Saved outputs rechecked without model calls.', flush=True)
        return
    records = []
    mode = 'LIVE_MODEL' if args.live else 'PREPARED_WITHOUT_MODEL_CALLS'
    for index, case in enumerate(cases(), 1):
        print(f'{index}/10 {case["name"]}: {mode}', flush=True)
        dossier = case.pop('dossier')
        source = build_narrator_input(dossier)
        record = {**case, 'narrator_input': source, 'canonical_dossier': dossier}
        if args.live:
            started = time.perf_counter()
            try:
                call = call_dossier_narrator(dossier.get('case_id', case['name']), source)
                verification = verify_narrative(dossier, source, call.get('narrative'))
                fallback = call.get('deterministic_fallback')
                record.update({'transport_result': call['transport_result'], 'narrative': call.get('narrative'),
                               'verification': verification, 'fallback': fallback,
                               'fallback_verification': verify_controlled(source, fallback),
                               'model': call.get('model'), 'prompt_version': call.get('prompt_version'),
                               'model_call_count': call.get('model_call_count'),
                               'input_tokens': call.get('input_tokens'), 'output_tokens': call.get('output_tokens'),
                               'mutations': mutations(dossier, source, call.get('narrative'))})
                print('  transport=' + call['transport_result'] + ' checks=' + verification['status'] +
                      ' reasons=' + ','.join(verification['reason_codes']), flush=True)
            except Exception as exc:
                # Never serialize request headers, credentials or exception text.
                record.update({'transport_result': 'EXCEPTION', 'error_type': type(exc).__name__})
                print('  exception=' + type(exc).__name__, flush=True)
            record['elapsed_seconds'] = round(time.perf_counter() - started, 2)
        records.append(record)
        write_report(args.out, records, mode)


if __name__ == '__main__':
    main()
