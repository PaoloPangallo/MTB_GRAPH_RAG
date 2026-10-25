import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import DossierView from './DossierView';
import type { DossierReadingGuide, DocumentaryFinding } from './contracts.generated';

const finding: DocumentaryFinding = {
  candidate_id: 'P', evidence_id: 'E', disposition: 'RETAINED_RECORD',
  source: { paper_id: 'pmid:28891408' }, quotation: 'Adjuvant therapy reduced recurrence.',
  observed: { disease: 'stage III melanoma', effect_direction: 'SENSITIVITY_RESPONSE' },
  checks: {}, limitations: {}, observed_origin: 'READER_EXTRACTION_NOT_INDEPENDENT_GOLD',
  scientific_correctness: 'NOT_INDEPENDENTLY_EVALUATED', clinical_applicability: 'NOT_EVALUATED',
};
const guide: DossierReadingGuide = {
  version: 'dossier-reading/1.0', clinical_applicability: 'NOT_EVALUATED',
  verification_note: 'La verifica narrativa controlla la fedeltà al dossier, non la correttezza scientifica.',
  trial_association_count: 0, identified_study_count: 0, unidentified_trial_association_count: 0,
  trial_groups: [], findings: [{
    paper_index: 0, finding_index: 0, candidate_id: 'P', evidence_id: 'E',
    requested_disease: 'metastatic melanoma', observed_disease: 'stage III melanoma',
    requested_intervention: 'dabrafenib + trametinib', observed_intervention: null,
    disease_text_comparison: 'DIFFERENT_RECORDED_TEXT', intervention_text_comparison: 'NOT_RECORDED',
    notices: [{ code: 'DISEASE_DESCRIPTIONS_DIFFER', message: 'Descrizioni della patologia diverse: verificare stadio e contesto.' }],
  }],
};

it('shows backend scope warnings beside quotations and labels broad outcomes honestly', () => {
  render(<DossierView debug={false} dossier={{ reading_guide: guide, paper_evidence: [{ candidate_id: 'P', documentary_findings: [finding] }] }} />);
  const article = screen.getByText('Osservazione conservata').closest('article')!;
  expect(within(article).getByText('metastatic melanoma')).toBeVisible();
  expect(within(article).getAllByText('stage III melanoma').length).toBeGreaterThan(0);
  expect(within(article).getByText(/Descrizioni della patologia diverse/)).toBeVisible();
  expect(within(article).getByText('Classificazione generale del risultato')).toBeVisible();
  expect(screen.getByText(guide.verification_note)).toBeVisible();
});

it('keeps conflicting snapshots visible when only one association matches a study search', () => {
  const entries = [
    { candidate_id: 'T1', nct_id: 'NCT02465060', title: 'Matching Drug', status: 'RECRUITING' },
    { candidate_id: 'T2', nct_id: 'NCT02465060', title: 'Other snapshot', status: 'COMPLETED' },
  ];
  render(<DossierView debug={false} dossier={{ clinical_trials: entries, reading_guide: { ...guide,
    trial_association_count: 2, identified_study_count: 1,
    trial_groups: [{ nct_id: 'NCT02465060', entry_indexes: [0, 1], snapshot_indexes: [0, 1], conflicting_snapshots: true }],
  } }} />);
  fireEvent.change(screen.getByLabelText('Cerca nelle relazioni'), { target: { value: 'Matching Drug' } });
  expect(screen.getByText(/Dati di registro discordanti/)).toBeVisible();
  expect(screen.getByText(/Dati registrati 2: Other snapshot/)).toBeVisible();
  expect(screen.getByText('1 studi distinti / 2 associazioni nel grafo')).toBeVisible();
});

it('does not calculate clinical equivalence in the browser when a historical guide is absent', () => {
  render(<DossierView debug={false} dossier={{ paper_evidence: [{ candidate_id: 'P', documentary_findings: [finding] }] }} />);
  expect(screen.getByText(/Confronto con il caso non disponibile per questa versione/)).toBeVisible();
  expect(screen.queryByText(/Descrizioni della patologia diverse/)).not.toBeInTheDocument();
});
