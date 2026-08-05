import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DossierView, { type Dossier } from './DossierView';

const DOSSIER: Dossier = {
  case_id: 'CASE-1',
  limitations: ['research_only_pilot', 'gemma_used_only_as_enricher'],
  provenance: {
    gemma_role: 'paper_context_enricher_only',
    gemma_never_decides: ['support_status', 'direction', 'gate', 'score', 'bucket'],
  },
  candidate_therapies: [
    {
      candidate_id: 'GCA-1',
      drug: 'panitumumab',
      graph_relation: 'RESISTANCE_TO',
      document_support: { selected_papers: ['EB-1'], excluded_papers: [] },
      author_context: [
        {
          author_claim_quote: 'panitumumab showed resistance',
          author_context_summary: 'Gli autori riportano resistenza.',
          source_unit_id: 'SU-1', paper_id: 'EB-1',
        },
        { abstain: true, abstention_reason: 'nessuna frase letterale a supporto' },
      ],
      validation_results: [{ paper_id: 'EB-1', outcome: 'ENRICHMENT_V2_ACCEPTED' }],
      gate_results: { bucket: 'PRIMARY_BUCKET', support_mask: { disease: 'SUPPORTED', direction: 'SUPPORTED' } },
      status: 'DIRECT',
      warnings: ['NO_VALIDATED_ENRICHMENT_AVAILABLE'],
    },
  ],
};

describe('DossierView', () => {
  it('tiene separate le tre sezioni', () => {
    render(<DossierView dossier={DOSSIER} />);

    expect(screen.getByText('Evidenza deterministica')).toBeInTheDocument();
    expect(screen.getByText('Author context')).toBeInTheDocument();
    expect(screen.getByText('Limitazioni')).toBeInTheDocument();
  });

  it('dichiara che il contesto d’autore non modifica lo status', () => {
    render(<DossierView dossier={DOSSIER} />);
    expect(screen.getByText(/Non modifica lo status né i gate/)).toBeInTheDocument();
  });

  it('mostra status e bucket come valori deterministici', () => {
    render(<DossierView dossier={DOSSIER} />);

    expect(screen.getByText('DIRECT')).toBeInTheDocument();
    expect(screen.getByText('PRIMARY_BUCKET')).toBeInTheDocument();
  });

  it('etichetta la relazione del grafo come non ancora prova documentale', () => {
    render(<DossierView dossier={DOSSIER} />);
    expect(screen.getByText(/non ancora prova documentale/)).toBeInTheDocument();
  });

  it('mostra la citazione con la sua Source Unit', () => {
    render(<DossierView dossier={DOSSIER} />);

    expect(screen.getByText(/panitumumab showed resistance/)).toBeInTheDocument();
    expect(screen.getByText(/SU-1/)).toBeInTheDocument();
  });

  it('mostra un’astensione come esito normale, non come errore', () => {
    render(<DossierView dossier={DOSSIER} />);
    expect(screen.getByText(/Astensione — nessuna frase letterale a supporto/)).toBeInTheDocument();
  });

  it('dichiara che il modello non decide status, gate, score o bucket', () => {
    render(<DossierView dossier={DOSSIER} />);
    expect(screen.getByText(/Il modello non decide:.*support_status.*gate.*score.*bucket/)).toBeInTheDocument();
  });

  it('traduce i reason code delle limitazioni quando possibile', () => {
    render(<DossierView dossier={DOSSIER} />);
    expect(screen.getByText('research_only_pilot')).toBeInTheDocument();
  });

  it('gestisce l’assenza di dossier senza inventare contenuto', () => {
    render(<DossierView dossier={null} />);
    expect(screen.getByText('Nessun dossier per questa run.')).toBeInTheDocument();
  });

  it('gestisce un dossier senza candidate', () => {
    render(<DossierView dossier={{ ...DOSSIER, candidate_therapies: [] }} />);
    expect(screen.getByText('Nessuna candidate terapeutica nel dossier.')).toBeInTheDocument();
  });
});
