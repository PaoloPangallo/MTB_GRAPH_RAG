import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DossierView, { type Dossier } from './DossierView';
const dossier: Dossier = {
  case_summary: { disease: 'colorectal cancer', gene: 'KRAS', variant: 'G12D' },
  paper_evidence: [{ candidate_id: 'GCA4-P', subject: { label: 'KRAS' }, object: { label: 'panitumumab' },
    support_level: 'PARTIAL_SUPPORT', document_id: 'pmid:19223544', quote: 'Validated passage.', quote_valid: true }],
  clinical_trials: [{ candidate_id: 'GCA4-T', nct_id: 'NCT05176665', title: 'Structured trial', eligibility_status: 'NOT_EVALUATED' }],
  kg_only_relations: [{ candidate_id: 'GCA4-K', subject: { label: 'CYP2D6' }, object: { label: 'RACLOPRIDE' } }],
  limitations: ['CANDIDATE_PARTIALLY_SUPPORTED'],
};

it('shows observed direction without promoting an authenticated unresolved quote', () => {
  render(<DossierView debug={false} dossier={{ paper_evidence: [{ candidate_id: 'scope', support_level: 'FULL_SUPPORT', accepted_evidence_records: [{ evidence_id: 'obs', paper_id: 'pmid:1', source_unit_id: 'SU-1', quote_valid: true, quote: 'No response was observed.', observed_relation: { intervention: 'drug A', effect_direction: 'RESISTANCE', evidence_context: { subject_level: 'CELL_MODEL' } }, document_verification: { structural_status: 'UNRESOLVED', final_admission: 'NOT_RUN_STRUCTURAL', semantic_assessment: {} } }] }] }} />);
  expect(screen.getByText(/No response was observed/)).toBeInTheDocument();
  expect(screen.getByText(/Gate strutturale: UNRESOLVED/)).toHaveTextContent('Verifica semantica: Non eseguita');
  expect(screen.getByText('RESISTANCE')).toBeInTheDocument();
  expect(screen.queryByText('Supporto documentale completo')).not.toBeInTheDocument();
});
describe('dossier canonico corrente', () => {
  it('costruisce i dettagli di elaborazione solo quando vengono aperti', () => {
    render(<DossierView dossier={{ ...dossier, pipeline_accounting: { diagnostic: 'ACCOUNTING_ONLY_ON_OPEN' } }} />);
    expect(screen.queryByText('ACCOUNTING_ONLY_ON_OPEN')).not.toBeInTheDocument();
    const details = screen.getByText('Conteggi e percorso di elaborazione').closest('details')!;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    const pipeline = screen.getByText(/pipeline.*1 campo/).closest('details')!;
    pipeline.open = true;
    fireEvent(pipeline, new Event('toggle'));
    expect(screen.getByText('ACCOUNTING_ONLY_ON_OPEN')).toBeInTheDocument();
    details.open = false;
    fireEvent(details, new Event('toggle'));
    expect(screen.queryByText('ACCOUNTING_ONLY_ON_OPEN')).not.toBeInTheDocument();
  });
  it('ricerca anche le relazioni oltre il primo gruppo e conserva limiti e conflitti', () => {
    const entries = Array.from({ length: 12 }, (_, index) => ({ candidate_id: `P-${index}`, subject: { label: `GENE-${index}` }, object: { label: `DRUG-${index}` }, contradiction_present: index === 11 }));
    render(<DossierView debug={false} dossier={{ ...dossier, paper_evidence: entries }} />);
    expect(screen.getByText('Mostrate 8 di 12 relazioni.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /GENE-11/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Cerca nelle relazioni'), { target: { value: 'DRUG-11' } });
    expect(screen.getByRole('heading', { name: /GENE-11/ })).toBeInTheDocument();
    expect(screen.getByText(/Il dossier contiene evidenze in conflitto/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Limitazioni e/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Cerca nelle relazioni'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /Mostra altre relazioni/ }));
    expect(screen.getByText('Mostrate 12 di 12 relazioni.')).toBeInTheDocument();
  });
  it('mantiene separati i tre percorsi', () => {
    render(<DossierView dossier={dossier} />);
    expect(screen.getByRole('heading', { name: /Evidenze da pubblicazioni/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Studi clinici/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Relazioni del Knowledge Graph/ })).toBeInTheDocument();
    expect(screen.queryByText('Supporto documentale parziale')).not.toBeInTheDocument();
    expect(screen.getByText(/Citazione: Autenticata/)).toBeInTheDocument();
    expect(screen.getByText(/non costituisce prova di efficacia/)).toBeInTheDocument();
    expect(screen.getByText(/del paziente non valutata/)).toBeInTheDocument();
  });
  it('collega la citazione alla fonte pubblica', () => {
    render(<DossierView dossier={dossier} />);
    expect(screen.getByText(/Validated passage/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'pmid:19223544' })).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/19223544/');
  });
  it('non trasforma identificatori non riconosciuti in URL', () => {
    render(<DossierView dossier={{ ...dossier, paper_evidence: [{ candidate_id: 'P', document_id: 'javascript:alert(1)' }] }} />);
    expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).not.toBeInTheDocument();
  });
  it('gestisce assenza e contratto storico senza inventare evidenze', () => {
    const view = render(<DossierView dossier={null} />);
    expect(screen.getByText('Nessun dossier per questa run.')).toBeInTheDocument();
    view.rerender(<DossierView dossier={{}} />);
    expect(screen.getByText(/contratto storico/)).toBeInTheDocument();
  });
  it('un dossier vuoto mantiene tutte le sezioni e le limitazioni', () => {
    render(<DossierView dossier={{ paper_evidence: [], clinical_trials: [], kg_only_relations: [] }} />);
    expect(screen.getAllByText('Nessuna relazione in questo percorso.')).toHaveLength(3);
    expect(screen.getByText('Nessuna limitazione registrata.')).toBeInTheDocument();
  });
  it('separa le destinazioni senza link a sezioni assenti e conserva gli avvisi', () => {
    const conflict = { ...dossier, paper_evidence: [{ ...dossier.paper_evidence![0], contradiction_present: true }] };
    const view = render(<DossierView debug={false} section="relations" dossier={conflict} />);
    expect(screen.getByLabelText('Cerca nelle relazioni')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Limiti' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /Limitazioni e/ })).not.toBeInTheDocument();
    view.rerender(<DossierView debug={false} section="limits" dossier={conflict} />);
    expect(screen.queryByLabelText('Cerca nelle relazioni')).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Sezioni del dossier' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Limitazioni e/ })).toBeInTheDocument();
    expect(screen.getByText(/Il dossier contiene evidenze in conflitto/)).toBeInTheDocument();
    expect(screen.getByText('Conteggi e percorso di elaborazione')).toBeInTheDocument();
  });

});

it('shows publication failure independently of evidence support', () => {
  render(<DossierView dossier={{ ...dossier, publication_status: 'INCOMPLETE', technical_run_status: 'PARTIAL', publication_integrity: { reconciliation_status: 'FAIL' } }} />);
  expect(screen.getByText(/Riconciliazione: FAIL/)).toBeInTheDocument();
  expect(screen.getByText(/Dossier incompleto/)).toBeInTheDocument();
});


it('distinguishes partial execution from failed reconciliation', () => {
  render(<DossierView debug={false} section="limits" dossier={{ ...dossier, publication_status: 'INCOMPLETE', technical_run_status: 'PARTIAL', publication_integrity: { reconciliation_status: 'PASS' } }} />);
  expect(screen.getByText(/Riconciliazione: PASS/)).toBeInTheDocument();
  expect(screen.getByText(/Dossier incompleto/)).toBeInTheDocument();
});

it('shows insufficient information and mixed record composition', () => {
  render(<DossierView debug={false} dossier={{ ...dossier, paper_evidence: [{ candidate_id: 'mixed', support_level: 'INSUFFICIENT_INFORMATION', evidence_composition: { record_count: 2, unique_publication_count: 1, mixed_support: true } }] }} />);
  expect(screen.queryByText('Informazioni insufficienti per stabilire il supporto')).not.toBeInTheDocument();
  const details = screen.getAllByText('Tracciabilit\u00e0 e dettagli della relazione')[0].closest('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  expect(screen.getByText('INSUFFICIENT_INFORMATION')).toBeInTheDocument();
  expect(screen.getByText(/2 record da 1 pubblicazioni distinte/)).toBeInTheDocument();
  expect(screen.getByText(/Esiti misti/)).toBeInTheDocument();
});


it('does not hide partial execution when integrity metadata is unavailable', () => {
  render(<DossierView dossier={{ ...dossier, technical_run_status: 'PARTIAL' }} />);
  expect(screen.getByText(/Dossier incompleto/)).toBeInTheDocument();
  expect(screen.getByText(/Riconciliazione: UNKNOWN/)).toBeInTheDocument();
});
