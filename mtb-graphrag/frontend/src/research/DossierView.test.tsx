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
          // Il backend annota ogni voce con il proprio esito di validazione.
          presentation_state: 'VALIDATED_QUOTE',
          validation_outcome: 'ENRICHMENT_V2_ACCEPTED',
          validation_reason_codes: [],
        },
        {
          abstain: true, abstention_reason: 'nessuna frase letterale a supporto',
          presentation_state: 'ABSTAINED',
          validation_outcome: 'ENRICHMENT_V2_ABSTAINED',
          validation_reason_codes: [],
        },
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

/**
 * ISS-003 — la presentazione segue l'esito del validatore, mai la presenza
 * della quote. Ognuno di questi test fallisce con la regola precedente
 * `accepted = e.author_claim_quote != null`.
 */
describe('DossierView — presentazione e validazione', () => {
  const withAuthorContext = (author_context: unknown[]): Dossier => ({
    ...DOSSIER,
    candidate_therapies: [{ ...DOSSIER.candidate_therapies[0], author_context } as never],
  });

  const INVENTED = 'Panitumumab significantly prolonged overall survival';

  it('non presenta come citazione una quote rigettata dal validatore', () => {
    render(<DossierView dossier={withAuthorContext([{
      author_claim_quote: INVENTED,
      author_context_summary: 'Panitumumab prolonged survival.',
      source_unit_id: 'SU-1', paper_id: 'EB-1',
      presentation_state: 'REJECTED_QUOTE',
      validation_outcome: 'REJECTED_QUOTE_NOT_FOUND',
      validation_reason_codes: ['QUOTE_NOT_LITERAL_IN_SOURCE_UNIT'],
    }])} />);

    // La quote non compare fra le citazioni: niente virgolette tipografiche.
    expect(screen.queryByText(`“${INVENTED}”`)).not.toBeInTheDocument();
  });

  it('mostra la proposta rigettata in una sezione di solo audit, con il motivo', () => {
    render(<DossierView dossier={withAuthorContext([{
      author_claim_quote: INVENTED,
      presentation_state: 'REJECTED_QUOTE',
      validation_outcome: 'REJECTED_QUOTE_NOT_FOUND',
      validation_reason_codes: ['QUOTE_NOT_LITERAL_IN_SOURCE_UNIT'],
    }])} />);

    expect(screen.getByText('PROPOSTE NON VALIDATE — SOLO AUDIT')).toBeInTheDocument();
    expect(screen.getByText('REJECTED_QUOTE_NOT_FOUND')).toBeInTheDocument();
    expect(screen.getByText(/il validatore deterministico le ha scartate/i)).toBeInTheDocument();
  });

  it('non presenta una quote priva di esito di validazione', () => {
    render(<DossierView dossier={withAuthorContext([{
      author_claim_quote: INVENTED,
      source_unit_id: 'SU-1', paper_id: 'EB-1',
    }])} />);

    expect(screen.queryByText(`“${INVENTED}”`)).not.toBeInTheDocument();
    expect(screen.getByText('PROPOSTE NON VALIDATE — SOLO AUDIT')).toBeInTheDocument();
  });

  it('presenta la quote quando e solo quando il validatore l’ha accettata', () => {
    const quote = 'panitumumab did not derive benefit';
    render(<DossierView dossier={withAuthorContext([{
      author_claim_quote: quote,
      source_unit_id: 'SU-9', paper_id: 'EB-1',
      presentation_state: 'VALIDATED_QUOTE',
      validation_outcome: 'ENRICHMENT_V2_ACCEPTED',
      validation_reason_codes: [],
    }])} />);

    expect(screen.getByText(`“${quote}”`)).toBeInTheDocument();
    expect(screen.queryByText('PROPOSTE NON VALIDATE — SOLO AUDIT')).not.toBeInTheDocument();
  });

  it('non promuove una quote rigettata anche quando lo status canonico è positivo', () => {
    render(<DossierView dossier={withAuthorContext([{
      author_claim_quote: INVENTED,
      presentation_state: 'REJECTED_QUOTE',
      validation_outcome: 'REJECTED_QUOTE_NOT_FOUND',
      validation_reason_codes: [],
    }])} />);

    // Lo status resta quello deciso dal backend, ma la quote non e' presentata.
    expect(screen.getByText('DIRECT')).toBeInTheDocument();
    expect(screen.queryByText(`“${INVENTED}”`)).not.toBeInTheDocument();
  });
});
