import { describe, expect, it } from 'vitest';
import { buildComparisonRequest, splitClinicalValues, type ComparisonFormState } from './comparisonRequest';

function baseFormState(overrides: Partial<ComparisonFormState> = {}): ComparisonFormState {
  return {
    gene: 'EGFR',
    variant: 'L858R',
    tumorType: 'Lung Adenocarcinoma',
    alterationType: 'point_mutation',
    therapyLine: 'first-line',
    diseaseStage: '',
    diseaseSetting: '',
    priorTherapies: '',
    priorResponse: '',
    ecogStatus: '',
    cnsMetastases: '',
    coAlterations: '',
    jurisdiction: '',
    mtbGoal: 'general-review',
    mode: 'demo',
    ...overrides,
  };
}

describe('splitClinicalValues', () => {
  it('splits comma-separated values and trims whitespace', () => {
    expect(splitClinicalValues('osimertinib, chemioterapia ,  radioterapia')).toEqual([
      'osimertinib',
      'chemioterapia',
      'radioterapia',
    ]);
  });

  it('drops empty entries and returns an empty array for blank input', () => {
    expect(splitClinicalValues('')).toEqual([]);
    expect(splitClinicalValues('  ,  ,')).toEqual([]);
  });
});

describe('buildComparisonRequest', () => {
  it('leaves undeclared clinical fields as null/empty arrays, never invented', () => {
    const payload = buildComparisonRequest(baseFormState());
    expect(payload.disease_stage).toBeNull();
    expect(payload.disease_setting).toBeNull();
    expect(payload.prior_therapies).toEqual([]);
    expect(payload.prior_response).toBeNull();
    expect(payload.ecog_status).toBeNull();
    expect(payload.cns_metastases).toBeNull();
    expect(payload.co_alterations).toEqual([]);
    expect(payload.jurisdiction).toBeNull();
  });

  it('splits comma-separated prior therapies and co-alterations into arrays', () => {
    const payload = buildComparisonRequest(baseFormState({
      priorTherapies: 'osimertinib, chemioterapia',
      coAlterations: 'TP53, MET amplification',
    }));
    expect(payload.prior_therapies).toEqual(['osimertinib', 'chemioterapia']);
    expect(payload.co_alterations).toEqual(['TP53', 'MET amplification']);
  });

  it('converts a selected ECOG value to a number, not a string', () => {
    const payload = buildComparisonRequest(baseFormState({ ecogStatus: '2' }));
    expect(payload.ecog_status).toBe(2);
    expect(typeof payload.ecog_status).toBe('number');
  });

  it('converts CNS metastases selection to a boolean, distinguishing present/absent/unspecified', () => {
    expect(buildComparisonRequest(baseFormState({ cnsMetastases: 'present' })).cns_metastases).toBe(true);
    expect(buildComparisonRequest(baseFormState({ cnsMetastases: 'absent' })).cns_metastases).toBe(false);
    expect(buildComparisonRequest(baseFormState({ cnsMetastases: '' })).cns_metastases).toBeNull();
  });

  it('carries execution_mode and core case fields through unchanged', () => {
    const payload = buildComparisonRequest(baseFormState({ mode: 'live', therapyLine: 'first-line' }));
    expect(payload.execution_mode).toBe('live');
    expect(payload.gene).toBe('EGFR');
    expect(payload.variant).toBe('L858R');
    expect(payload.tumor_type).toBe('Lung Adenocarcinoma');
    expect(payload.therapy_line).toBe('first-line');
    expect(payload.alteration_type).toBe('point_mutation');
  });
});
