import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DossierView, { type Dossier } from './DossierView';
import PublicationNotice from './PublicationNotice';
import DocumentaryObservation from './DocumentaryObservation';
import type { DocumentaryFinding } from './contracts.generated';

const finding: DocumentaryFinding = {
  evidence_id: 'E-READ', candidate_id: 'C-READ', disposition: 'RETAINED_RECORD',
  source: { public_source_identity: 'pmid:26554404', source_unit_id: 'SU-READ' },
  quotation: 'Drug X improved survival in mice.', observed: { intervention: 'Drug X', disease: 'Neuroblastoma', effect_direction: 'SENSITIVITY_RESPONSE', evidence_context: { subject_level: 'ANIMAL_MODEL' } },
  observed_origin: 'READER_EXTRACTION_NOT_INDEPENDENT_GOLD',
  checks: { quotation: { status: 'AUTHENTICATED' }, structural: { status: 'NOT_RECORDED' }, semantic: { status: 'NOT_REQUIRED_BY_POLICY' } },
  limitations: {}, scientific_correctness: 'NOT_INDEPENDENTLY_EVALUATED', clinical_applicability: 'NOT_EVALUATED',
};

describe('lettura del dossier per oncologo', () => {
  it('trova un farmaco presente soltanto negli interventi del registro trial', () => {
    render(<DossierView debug={false} dossier={{ clinical_trials: [{ candidate_id: 'T', nct_id: 'NCT03126916', title: 'Registry study', interventions: [{ name: 'lorlatinib' }], conditions: ['Neuroblastoma'], status: 'RECRUITING' }] }} />);
    for (const term of ['lorlatinib', 'Neuroblastoma', 'In reclutamento']) {
      fireEvent.change(screen.getByLabelText('Cerca nelle relazioni'), { target: { value: term } });
      expect(screen.getByRole('link', { name: 'NCT03126916' })).toBeInTheDocument();
    }
  });
  it('cerca identita pubbliche e contenuto osservato anche nei record esclusi', () => {
    render(<DossierView debug={false} dossier={{ paper_evidence: [{ candidate_id: 'C-READ', document_id: 'pmcid:PMC1', documentary_findings: [{ ...finding, disposition: 'EXCLUDED_RECORD', quotation: null }] }] }} />);
    for (const term of ['26554404', 'Drug X']) {
      fireEvent.change(screen.getByLabelText('Cerca nelle relazioni'), { target: { value: term } });
      expect(screen.getByRole('status')).toHaveTextContent('1 relazioni corrispondenti');
      expect(screen.getByRole('link', { name: 'pmid:26554404' })).toBeInTheDocument();
    }
    expect(screen.queryByText('Drug X improved survival in mice.')).not.toBeInTheDocument();
  });

  it('mostra una scheda per NCT mantenendo tutte le associazioni nei dettagli', () => {
    render(<DossierView debug={false} dossier={{ clinical_trials: [
      { candidate_id: 'T1', nct_id: 'NCT03126916', title: 'One study', object: { label: 'Drug X' } },
      { candidate_id: 'T2', nct_id: 'NCT03126916', title: 'One study', object: { label: 'Drug Y' } },
    ] }} />);
    expect(screen.getByText('1 studi distinti / 2 associazioni nel grafo')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'NCT03126916' })).toHaveLength(1);
    const details = screen.getByText('Associazioni nel grafo (2)').closest('details')!;
    details.open = true; fireEvent(details, new Event('toggle'));
    expect(within(details).getByText('T1')).toBeInTheDocument();
    expect(within(details).getByText('T2')).toBeInTheDocument();
  });

  it('non usa un paragrafo del grafo come titolo della pubblicazione', () => {
    const claim = 'Very long graph statement with numbers and background.';
    render(<DossierView debug={false} dossier={{ paper_evidence: [{ candidate_id: 'C', relation: 'has_evidence_statement', subject: { label: 'BRAF V600E' }, object: { label: claim }, documentary_findings: [finding] }] }} />);
    expect(screen.queryByRole('heading', { name: new RegExp(claim) })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /BRAF V600E/ })).toBeInTheDocument();
  });

  it('presenta i campi osservati con etichette leggibili e schema tecnico separato', () => {
    render(<DocumentaryObservation finding={finding} />);
    expect(screen.getByText('Intervento osservato')).toBeInTheDocument();
    expect(screen.getByText('Modello animale')).toBeInTheDocument();
    expect(screen.getByText('Sensibilità o risposta riportata')).toBeInTheDocument();
    expect(screen.queryByText('SENSITIVITY_RESPONSE')).not.toBeInTheDocument();
    expect(screen.getByText('Schema originale e tracciabilità')).toBeInTheDocument();
  });

  it('separa la pubblicazione completa dal recupero con fallback', () => {
    const dossier = { publication_status: 'COMPLETE', technical_run_status: 'COMPLETED', publication_integrity: { reconciliation_status: 'PASS' }, source_unit_retrieval: { fallbacks: [{ document_id: 'pmid:1', reason: 'ENCODING_WINDOW_BUDGET_EXCEEDED' }] } } as Dossier;
    render(<PublicationNotice dossier={dossier} />);
    expect(screen.getByText(/Dossier completo/)).toBeInTheDocument();
    expect(screen.getByText(/Recupero con limitazioni/)).toHaveTextContent('BM25');
    expect(screen.queryByText(/non risulta pubblicabile/)).not.toBeInTheDocument();
  });
});
