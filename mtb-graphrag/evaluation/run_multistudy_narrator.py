"""Ten narration trials: six declared synthetic scenarios and four archived subsets."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from evaluation.run_source_first_narrator import inputs as archived_inputs
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.narrator import call_dossier_narrator, narrative_hash
from backend.research_pipeline.narrative.verifier import verify_narrative


def synthetic(name):
    """Construct explicit contract fixtures; observations are invented test data."""
    findings = []
    bibliography = []
    for index in (1, 2):
        identity = 'pmid:' + str(90000000 + index)
        conflicting = name == 'contrasting_results' and index == 2
        population = 'stage III melanoma' if name == 'different_populations' and index == 2 else 'metastatic melanoma'
        treatment = 'dabrafenib plus trametinib' if name == 'combination_and_monotherapy' and index == 2 else 'trametinib'
        if name == 'two_passages_one_study':
            identity = 'pmid:90000001'
        sentence = (f'In this synthetic test, {treatment} ' +
                    ('did not improve survival' if conflicting else 'improved survival') +
                    f' in {population} with BRAF V600K.')
        source = {'document_id': identity, 'public_source_identity': identity,
                  'source_unit_id': 'SYNTHETIC-UNIT-' + str(index)}
        findings.append({'disposition': 'EXCLUDED_RECORD' if name == 'excluded_second_observation' and index == 2 else 'RETAINED_RECORD',
            'source': source, 'quotation': sentence,
            'observed': {'disease': population, 'intervention': treatment,
                'subjects': [{'type': 'GENE', 'surface_value': 'BRAF'},
                             {'type': 'ALTERATION', 'surface_value': 'V600K', 'linked_gene': 'BRAF'}],
                'observed_stance': 'DOES_NOT_SUPPORT' if conflicting else 'SUPPORTS',
                'effect_direction': 'NO_BENEFIT' if conflicting else 'SENSITIVITY_RESPONSE',
                'finding': sentence, 'caveats': ['Synthetic contract fixture; not a scientific result.']},
            'checks': {'quotation': {'status': 'AUTHENTICATED'},
                       'correspondence': {'fields': {'gene': 'CONFIRMED', 'alteration': 'CONFIRMED'}}},
            'limitations': {}, 'clinical_applicability': 'NOT_EVALUATED'})
        bibliography.append({'document_id': identity, 'public_source_identity': identity,
            'title': 'Synthetic test publication ' + identity, 'journal': 'Contract test fixture'})
    return {'case_id': 'SYNTHETIC-' + name, 'documentary_contract_version': 'documentary-findings/1.1',
        'case_summary': {'disease': 'melanoma metastatico', 'gene': 'BRAF', 'variant': 'V600K',
                         'intervention': 'trametinib'},
        'paper_evidence': [{'candidate_id': 'SYNTHETIC-RELATION', 'relation': 'has_evidence_statement',
            'source_bibliography': bibliography, 'documentary_findings': findings}], 'limitations': []}


def cases():
    for name in ('concordant_results', 'contrasting_results', 'different_populations',
                 'combination_and_monotherapy', 'two_passages_one_study', 'excluded_second_observation'):
        yield {'name': name, 'origin': 'SYNTHETIC_CONTRACT_FIXTURE', 'canonical_dossier': synthetic(name)}
    archived = list(archived_inputs())
    for item in archived:
        yield {**item, 'origin': 'ARCHIVED_DOCUMENTARY_SUBSET'}
    all_three = deepcopy(archived[0]['canonical_dossier'])
    all_three['paper_evidence'] = [deepcopy(item['canonical_dossier']['paper_evidence'][0]) for item in archived]
    yield {'name': 'BRAF_three_relations', 'origin': 'ARCHIVED_DOCUMENTARY_SUBSET',
           'canonical_dossier': all_three,
           'provenance': [record for item in archived for record in item['provenance']]}


def omission_mutations(dossier, source, narrative):
    mutations = []
    for index, entry in enumerate(narrative['candidate_narratives']):
        for observation in entry.get('observation_narratives') or []:
            changed = deepcopy(narrative)
            changed['candidate_narratives'][index]['observation_narratives'] = [
                value for value in entry['observation_narratives']
                if value['observation_id'] != observation['observation_id']]
            changed['narrative_hash'] = narrative_hash(changed)
            verdict = verify_narrative(dossier, source, changed)
            mutations.append({'kind': 'OMIT_OBSERVATION', 'candidate_id': entry['candidate_id'],
                'observation_id': observation['observation_id'], 'expected_status': 'FAIL', 'verification': verdict})
        if entry.get('study_comparison'):
            changed = deepcopy(narrative)
            changed['candidate_narratives'][index].pop('study_comparison')
            changed['narrative_hash'] = narrative_hash(changed)
            mutations.append({'kind': 'OMIT_COMPARISON', 'candidate_id': entry['candidate_id'],
                              'expected_status': 'FAIL' if len({o['study_id'] for c in source['candidates']
                                  if c['candidate_id'] == entry['candidate_id']
                                  for o in c.get('narration_observations') or []}) > 1 else 'PASS',
                              'verification': verify_narrative(dossier, source, changed)})
    return mutations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--reverify', type=Path, help='Recheck saved responses without a model call.')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    inputs = (json.loads(args.reverify.read_text(encoding='utf-8'))['cases'] if args.reverify else cases())
    for index, item in enumerate(inputs, 1):
        dossier = item['canonical_dossier']
        source = item['narrator_input'] if args.reverify else build_narrator_input(dossier)
        item['narrator_input'] = source
        print(str(index) + '/10 ' + item['name'], flush=True)
        if args.live or args.reverify:
            call = item['call'] if args.reverify else call_dossier_narrator(item['name'], source)
            if args.reverify:
                item['initial_verification'] = item['verification']
            item['call'] = call
            item['verification'] = verify_narrative(dossier, source, call.get('narrative'))
            item['omission_mutations'] = (omission_mutations(dossier, source, call['narrative'])
                if item['verification']['status'] == 'PASS' else [])
            print(call['transport_result'], item['verification']['status'], item['verification']['reason_codes'], flush=True)
        rows.append(item)
        (args.out / 'results.json').write_text(json.dumps({'mode': 'LIVE_MODEL_REVERIFIED' if args.reverify else 'LIVE_MODEL' if args.live else 'PREPARED',
            'cases': rows}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
