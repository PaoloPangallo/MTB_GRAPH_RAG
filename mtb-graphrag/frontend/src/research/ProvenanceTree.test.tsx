import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ProvenanceTree from './ProvenanceTree';
import type { ProvenanceItem } from './types';

const ITEMS: ProvenanceItem[] = [
  {
    candidate_id: 'GCA-1',
    chain: [
      { level: 'CASE_CONTEXT', ref: 'CASE-1' },
      { level: 'GRAPH_CANDIDATE_ASSERTION', ref: 'GCA-1', graph_derived: true, documentary_proof: false },
      { level: 'DOCUMENT', ref: ['doc-1', 'doc-2'], replayed: true },
      {
        level: 'SOURCE_UNIT',
        text_never_exposed: true,
        units: [
          { source_unit_id: 'SU-1', section: 'results', char_start: 120, char_end: 268, text: null },
          { source_unit_id: 'SU-2', section: 'methods', char_start: 10, char_end: 90, text: null },
        ],
      },
      { level: 'GATE_AND_STATUS', ref: { status: 'DIRECT' } },
    ],
  },
];

describe('ProvenanceTree', () => {
  it('rende la catena livello per livello', () => {
    render(<ProvenanceTree items={ITEMS} />);

    expect(screen.getByText('CaseContext')).toBeInTheDocument();
    expect(screen.getByText('Graph Candidate Assertion')).toBeInTheDocument();
    expect(screen.getByText('Source Unit')).toBeInTheDocument();
    expect(screen.getByText('Gate e status')).toBeInTheDocument();
  });

  it('marca la candidate come graph-derived e non prova documentale', () => {
    render(<ProvenanceTree items={ITEMS} />);

    expect(screen.getByText('GRAPH-DERIVED')).toBeInTheDocument();
    expect(screen.getByText('non è prova documentale')).toBeInTheDocument();
  });

  it('marca come replay i documenti risolti in una run precedente', () => {
    render(<ProvenanceTree items={ITEMS} />);
    expect(screen.getByText('REPLAY')).toBeInTheDocument();
  });

  it('dichiara che le Source Unit non portano testo del documento', () => {
    render(<ProvenanceTree items={ITEMS} />);
    expect(screen.getByText(/solo locatori e hash, nessun testo del documento/)).toBeInTheDocument();
  });

  it('mostra i locatori delle Source Unit', () => {
    render(<ProvenanceTree items={ITEMS} />);
    expect(screen.getByText(/SU-1 · results · 120–268/)).toBeInTheDocument();
  });

  it('espone la catena come lista ordinata accessibile', () => {
    render(<ProvenanceTree items={ITEMS} />);
    expect(screen.getByRole('list', { name: /Catena di provenienza per GCA-1/ })).toBeInTheDocument();
  });

  it('spiega l’assenza di catena invece di mostrare un vuoto', () => {
    render(<ProvenanceTree items={[]} />);
    expect(screen.getByText(/la run non ha prodotto candidate/)).toBeInTheDocument();
  });
});
