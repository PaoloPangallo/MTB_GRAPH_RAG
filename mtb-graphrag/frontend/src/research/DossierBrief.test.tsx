import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import DossierBrief from './DossierBrief';
import type { DocumentaryFinding } from './contracts.generated';

const record: DocumentaryFinding = {
  candidate_id: 'C', evidence_id: 'E', disposition: 'RETAINED_RECORD',
  source: { public_source_identity: 'pmid:25265494' }, quotation: 'Reported source result.',
  observed: { intervention: 'vemurafenib + cobimetinib', disease: 'metastatic melanoma', effect_direction: 'SENSITIVITY_RESPONSE', evidence_context: { subject_level: 'COHORT' } },
  observed_origin: 'READER_EXTRACTION_NOT_INDEPENDENT_GOLD', checks: {}, limitations: {},
  scientific_correctness: 'NOT_INDEPENDENTLY_EVALUATED', clinical_applicability: 'NOT_EVALUATED',
};

it('rende visibili domanda e intervento osservato senza dichiararli equivalenti', () => {
  const navigate = vi.fn();
  render(<DossierBrief dossier={{ case_summary: { intervention: 'dabrafenib + trametinib', disease: 'melanoma', gene: 'BRAF', variant: 'V600E' }, paper_evidence: [{ candidate_id: 'C', documentary_findings: [record, { ...record, evidence_id: 'EX', disposition: 'EXCLUDED_RECORD', quotation: null }] }] }} onNavigate={navigate} />);
  expect(screen.getByText('dabrafenib + trametinib')).toBeVisible();
  expect(screen.getByText('vemurafenib + cobimetinib')).toBeVisible();
  expect(screen.getByRole('link', { name: 'pmid:25265494' })).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/25265494/');
  expect(screen.getByText(/1 record conservati.*1 record esclusi/)).toBeInTheDocument();
  expect(screen.getByText(/non stabilisce equivalenza/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Leggi osservazioni e fonti' }));
  expect(navigate).toHaveBeenCalledWith('dossier-paper');
});

it('non interpreta assenza di osservazioni come assenza di evidenze scientifiche', () => {
  render(<DossierBrief dossier={{ paper_evidence: [{ candidate_id: 'C', documentary_findings: [], documentary_attempts: [{ decision: 'ABSTAIN' }] }] }} />);
  expect(screen.getByText(/Nessuna osservazione conservata disponibile per questa sintesi/)).toBeVisible();
  expect(screen.getByText(/non dimostra assenza di evidenze/)).toBeVisible();
});

it('non dichiara zero evidenze quando il dossier usa il contratto precedente', () => {
  render(<DossierBrief dossier={{ paper_evidence: [{ candidate_id: 'OLD', accepted_evidence_records: [{ evidence_id: 'OLD-E', quote: 'Available old observation.', quote_valid: true }] }] }} />);
  expect(screen.getByText(/Sintesi documentale non disponibile per questa versione/)).toBeVisible();
  expect(screen.queryByText(/0 record conservati/)).not.toBeInTheDocument();
});
