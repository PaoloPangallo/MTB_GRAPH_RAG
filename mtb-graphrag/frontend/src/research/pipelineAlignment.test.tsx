import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DossierView from './DossierView';
import StageOutput from './stages';
import { makeStage } from './testFactories';

describe('contratto corrente della pipeline', () => {
  it('legge quote e relazione osservata dal Reader corrente', () => {
    render(<StageOutput stage={makeStage({ stage_id: 'stage_9_paper_context_enricher', output_preview: {
      calls: [{ candidate_id: 'GCA4-1', paper_id: 'pmid:1234', enrichment: {
        decision: 'QUOTE', quote: 'The combination reduced response.', source_unit_id: 'SU-1',
        observed_relation: { observed_stance: 'DOES_NOT_SUPPORT', relation_scope: 'COMBINATION' },
      } }],
    } })} />);
    expect(screen.getByText(/The combination reduced response/)).toBeInTheDocument();
    expect(screen.getByText('COMBINATION')).toBeInTheDocument();
  });

  it('distingue quote valida e ammissione della relazione', () => {
    render(<StageOutput stage={makeStage({ stage_id: 'stage_10_enrichment_validation', output_preview: {
      accepted_outcomes: ['ENRICHMENT_V3_ACCEPTED'],
      validations: [{ candidate_id: 'GCA4-1', outcome: 'ENRICHMENT_V3_ACCEPTED', quote_valid: true,
        candidate_support: { result: 'UNVERIFIABLE', fields: { variant: 'NOT_ESTABLISHED' } },
        document_verification: { structural_status: 'PASS', relation_alignment: 'AMBIGUOUS',
          final_admission: 'UNVERIFIABLE', assertion_scope: 'UNKNOWN' } }],
    } })} />);
    expect(screen.getByText('Citazione valida')).toBeInTheDocument();
    expect(screen.getAllByText('UNVERIFIABLE').length).toBeGreaterThan(0);
    expect(screen.queryByText('ENTRA NEL DOSSIER')).not.toBeInTheDocument();
  });

  it('non mostra una quote priva di validazione nel dossier corrente', () => {
    render(<DossierView dossier={{ paper_evidence: [{ candidate_id: 'GCA4-1', quote: 'FABBRICATA', quote_valid: false }],
      clinical_trials: [], kg_only_relations: [] }} />);
    expect(screen.queryByText(/FABBRICATA/)).not.toBeInTheDocument();
  });

  it('mostra tutte le osservazioni accettate e la contraddizione', () => {
    render(<DossierView dossier={{ paper_evidence: [{ candidate_id: 'GCA4-1', contradiction_present: true,
      support_level: 'CONTRADICTORY', accepted_evidence_records: [
        { evidence_id: 'E1', paper_id: 'pmid:1234', source_unit_id: 'SU-1', quote: 'First validated passage.', quote_valid: true },
        { evidence_id: 'E2', paper_id: 'pmid:5678', source_unit_id: 'SU-2', quote: 'Second validated passage.', quote_valid: true },
      ] }], clinical_trials: [], kg_only_relations: [] }} />);
    expect(screen.getByText(/First validated passage/)).toBeInTheDocument();
    expect(screen.getByText(/Second validated passage/)).toBeInTheDocument();
    expect(screen.getByText(/Le fonti riportano osservazioni in conflitto/)).toBeInTheDocument();
  });
});
