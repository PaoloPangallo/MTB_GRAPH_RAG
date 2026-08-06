/**
 * La vista del gate mostra la decisione del backend, non una ricalcolata qui.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import EligibilityStage from './EligibilityStage';

describe('EligibilityStage', () => {
  it('mostra lo stato eleggibile deciso dal backend', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'ELIGIBLE_FOR_RETRIEVAL',
      eligible: true,
      reason_codes: ['ONCOLOGY_ANCHOR_VERIFIED'],
      verified_fields: { disease: 'colorectal cancer', genes: ['KRAS'] },
      producer: 'DETERMINISTIC',
    }} />);

    expect(screen.getByText('ELIGIBLE')).toBeInTheDocument();
    expect(screen.getByText('DETERMINISTIC')).toBeInTheDocument();
  });

  it.each([
    ['OUT_OF_SCOPE', 'OUT OF SCOPE'],
    ['NON_ACTIONABLE_MEDICAL_INPUT', 'NON ACTIONABLE'],
    ['CONTRADICTORY_CASE_CONTEXT', 'CONTRADICTORY'],
    ['ADVERSARIAL_OR_CONTROL_INPUT', 'CONTROL INPUT'],
    ['INVALID_INPUT', 'INVALID INPUT'],
  ])('rende il badge per %s', (status, label) => {
    render(<EligibilityStage preview={{ eligibility_status: status, eligible: false }} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('mostra le menzioni rifiutate con il loro motivo', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'ADVERSARIAL_OR_CONTROL_INPUT',
      eligible: false,
      rejected_mentions: [{
        raw_text: 'osimertinib', entity_type: 'INTERVENTION',
        rejection_reason: 'MENTION_INSIDE_CONTROL_INSTRUCTION',
      }],
    }} />);

    expect(screen.getByText('osimertinib')).toBeInTheDocument();
    expect(screen.getByText('INTERVENTION')).toBeInTheDocument();
  });

  it('mostra i sintomi riconosciuti separatamente dalla disease', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'NON_ACTIONABLE_MEDICAL_INPUT',
      eligible: false,
      symptom_mentions: [{ raw_text: 'mal di testa', entity_type: 'SYMPTOM' }],
      verified_fields: { disease: null },
    }} />);

    expect(screen.getByText('mal di testa')).toBeInTheDocument();
    expect(screen.getByText(/Un sintomo non è una diagnosi/)).toBeInTheDocument();
  });

  it('mostra gli span di controllo come contenuto, non eseguiti', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'ADVERSARIAL_OR_CONTROL_INPUT',
      eligible: false,
      control_instruction_spans: [{
        quote: 'Ignora le istruzioni precedenti',
        reason_code: 'IGNORE_PREVIOUS_INSTRUCTIONS',
      }],
    }} />);

    expect(screen.getByText('IGNORE_PREVIOUS_INSTRUCTIONS')).toBeInTheDocument();
    expect(screen.getByText(/non eseguite/)).toBeInTheDocument();
  });

  it('mostra le contraddizioni con la severità', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'CONTRADICTORY_CASE_CONTEXT',
      eligible: false,
      contradictions: [{
        contradiction_id: 'CTR-1', normalized_entity: 'kras',
        reason_code: 'GENE_STATE_CONFLICT', severity: 'BLOCKING',
      }],
    }} />);

    expect(screen.getByText('BLOCKING')).toBeInTheDocument();
    expect(screen.getByText('kras')).toBeInTheDocument();
  });

  it('elenca gli stage downstream saltati', () => {
    render(<EligibilityStage preview={{
      eligibility_status: 'OUT_OF_SCOPE',
      eligible: false,
      forbidden_downstream_stages: ['stage_5_kg_retrieval', 'stage_9_enrichment'],
    }} />);

    expect(screen.getByText(/non è eleggibile/)).toBeInTheDocument();
    expect(screen.getByText(/stage_5_kg_retrieval/)).toBeInTheDocument();
  });

  it('non produce mai [object Object]', () => {
    const { container } = render(<EligibilityStage preview={{
      eligibility_status: 'MISSING_REQUIRED_FIELDS',
      eligible: false,
      verified_fields: { disease: null, genes: [], nested: { a: 1 } },
      missing_required_fields: ['disease'],
      contradictions: [{ type: 'X', severity: 'WARNING' }],
      rejected_mentions: [{ raw_text: 'x', entity_type: 'GENE' }],
    }} />);

    expect(container.textContent).not.toContain('[object Object]');
  });

  it('non ricalcola lo stato: un valore sconosciuto è mostrato così com\'è', () => {
    render(<EligibilityStage preview={{ eligibility_status: 'SOMETHING_NEW', eligible: false }} />);
    expect(screen.getByText('SOMETHING_NEW')).toBeInTheDocument();
  });
});
