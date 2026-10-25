"""Adversarial checks against the saved, provider-generated KRAS narration.

Inputs remain immutable: each mutation changes only a copy of generated prose.
These examples exercise bounded safeguards, not general semantic entailment.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.research_pipeline.narrative.narrator import narrative_hash
from backend.research_pipeline.narrative.verifier import verify_narrative

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope='module')
def saved_kras():
    directory = ROOT / 'experiments_real/kras_narration_repaired_20261020'
    canonical = ROOT / 'experiments_real/additional_cases_20261020/kras-g12d-panitumumab/run.json'
    if not directory.is_dir() or not canonical.is_file():
        pytest.skip('Saved real KRAS run is not installed')
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    return (read(canonical)['relation_aware_report'], read(directory / 'narrator-input.json'),
            read(directory / 'narrator-output.json')['narrative'])


def verdict(saved, suffix='', field='text'):
    dossier, source, output = saved
    output = deepcopy(output)
    output['candidate_narratives'][0]['observation_narratives'][0][field] += ' ' + suffix
    output['narrative_hash'] = narrative_hash(output)
    return verify_narrative(dossier, source, output)


def test_actual_provider_output_preserves_valid_source_case_comparisons(saved_kras):
    assert verdict(saved_kras)['status'] == 'PASS'


@pytest.mark.parametrize('claim,code', [
    ('La fonte descrive la variante KRAS G12D.', 'NARRATIVE_OBSERVATION_VARIANT_ESCALATION'),
    ('The source describes the KRAS G12D variant.', 'NARRATIVE_OBSERVATION_VARIANT_ESCALATION'),
    ('La fonte riporta una buona risposta alle terapie anti-EGFR.', 'NARRATIVE_OBSERVATION_POLARITY_INVERSION'),
    ('The source reports sensitivity to anti-EGFR therapies.', 'NARRATIVE_OBSERVATION_POLARITY_INVERSION'),
    ('Il paziente risulta eleggibile.', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED'),
    ('The patient is eligible for the trial.', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED'),
    ('Il paziente non è eleggibile.', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED'),
    ('The patient is not eligible.', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED'),
    ('The patient is ineligible.', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED'),
    ('La fonte descrive panitumumab in monoterapia.', 'NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN'),
    ('La fonte dimostra efficacia clinica.', 'NARRATIVE_OBSERVATION_CAUSAL_ESCALATION'),
    ('Il tasso di risposta osservato era 87%.', 'NARRATIVE_UNAUTHORIZED_NUMBER'),
])
def test_actual_observation_cannot_gain_an_unsupported_claim(saved_kras, claim, code):
    assert code in verdict(saved_kras, claim)['reason_codes']


@pytest.mark.parametrize('claim', [
    'La fonte non descrive la variante KRAS G12D.',
    'La fonte descrive KRAS, mentre il caso riguarda KRAS G12D.',
    'La fonte non riporta una buona risposta alle terapie anti-EGFR.',
    "L'eleggibilità individuale non è stata valutata.",
    'The source does not report sensitivity to anti-EGFR therapies.',
    'La fonte non dimostra efficacia clinica.',
    'La fonte non descrive panitumumab in monoterapia.',
])
def test_valid_negation_and_gene_case_variant_comparison_remain_accepted(saved_kras, claim):
    assert verdict(saved_kras, claim)['status'] == 'PASS'

@pytest.mark.parametrize('direction,claim', [
    ('RESISTANCE', 'The source reports sensitivity to trametinib.'),
    ('SENSITIVITY_RESPONSE', 'The source reports resistance to trametinib.'),
])
def test_recorded_observation_direction_controls_polarity_not_candidate_direction(direction, claim):
    from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check
    data, _, _ = repaired()
    for finding in data['paper_evidence'][0]['documentary_findings']:
        finding['observed']['effect_direction'] = direction
    source = build_narrator_input(data)
    output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = claim
    assert 'NARRATIVE_OBSERVATION_POLARITY_INVERSION' in check(data, source, output)['reason_codes']


def test_source_variant_and_monotherapy_are_allowed_when_documented_in_this_passage():
    from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check
    data, _, _ = repaired()
    for finding in data['paper_evidence'][0]['documentary_findings']:
        finding['observed'].update(subjects=[{'type': 'VARIANT', 'surface_value': 'BRAF V600K'}],
                                   intervention_composition='SINGLE_AGENT')
    source = build_narrator_input(data)
    output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = (
        'La fonte descrive BRAF V600K e trametinib in monoterapia.')
    assert check(data, source, output)['status'] == 'PASS'


@pytest.mark.parametrize('claim', [
    'La fonte dimostra efficacia clinica.',
    'The study demonstrates no clinical efficacy.',
])
def test_actual_response_is_not_rejected_using_patient_applicability_as_an_efficacy_ban(claim):
    from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check
    data, _, _ = repaired()
    for finding in data['paper_evidence'][0]['documentary_findings']:
        finding['observed']['evidence_context'] = {'claim_type': 'OBSERVED_RESPONSE', 'subject_level': 'COHORT'}
    source = build_narrator_input(data)
    output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = claim
    assert check(data, source, output)['status'] == 'PASS'

@pytest.mark.parametrize('claim', [
    'The study describes p.V600E.',
    'The study describes KRAS p.G12D.',
])
def test_hgvs_prefix_cannot_split_an_unsupported_source_variant(saved_kras, claim):
    assert 'NARRATIVE_OBSERVATION_VARIANT_ESCALATION' in verdict(saved_kras, claim)['reason_codes']


@pytest.mark.parametrize('claim', [
    'The study describes no monotherapy.',
    'The study describes neither combination therapy nor monotherapy.',
    'The study does not demonstrate clinical efficacy.',
    'The study describes no p.G12D variant.',
])
def test_local_negative_source_assertion_does_not_add_a_positive_fact(saved_kras, claim):
    assert verdict(saved_kras, claim)['status'] == 'PASS'


@pytest.mark.parametrize('claim,code', [
    ('The study describes no detail. The study describes monotherapy.', 'NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN'),
    ('The study describes no detail; the study describes monotherapy.', 'NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN'),
    ('The study describes no monotherapy but reports monotherapy.', 'NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN'),
    ('The study demonstrates no uncertainty about clinical efficacy.', 'NARRATIVE_OBSERVATION_CAUSAL_ESCALATION'),
    ('The study demonstrates no clinical efficacy.', 'NARRATIVE_OBSERVATION_CAUSAL_ESCALATION'),
    ('Lo studio dimostra assenza di efficacia clinica.', 'NARRATIVE_OBSERVATION_CAUSAL_ESCALATION'),
])
def test_negation_cannot_license_a_positive_assertion_or_a_negative_outcome(saved_kras, claim, code):
    assert code in verdict(saved_kras, claim)['reason_codes']


def test_documented_hgvs_prefix_is_allowed_in_a_source_assertion():
    from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check
    data, _, _ = repaired()
    for finding in data['paper_evidence'][0]['documentary_findings']:
        finding['observed']['subjects'] = [{'type': 'VARIANT', 'surface_value': 'BRAF V600K'}]
    source = build_narrator_input(data)
    output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = 'The study describes BRAF p.V600K.'
    assert check(data, source, output)['status'] == 'PASS'
