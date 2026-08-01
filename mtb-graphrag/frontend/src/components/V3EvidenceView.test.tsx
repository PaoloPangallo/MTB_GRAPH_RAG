import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import V3EvidenceView from './V3EvidenceView';
import type { V3RetrieveResponse } from '../types';

const response: V3RetrieveResponse = {
  case_context: { query_id: 'ui-test', direction: 'resistance' },
  summary: { total_records: 3, claim_records: 1, technical_records: 2, primary: 1, warning: 0, audit_claims: 0, rejected_claims: 0 },
  evidence: {
    primary: [{
      claim_id: 'CLM-1', candidate_kind: 'evidence_claim', subject: null, relation: null, object: null,
      structured_tuple_complete: false, claim_text: 'ALK ? NSCLC ? alectinib', disease: 'NSCLC', biomarker: 'ALK',
      intervention: 'alectinib', formulation: null, regimen: null, direction: 'exact', evidence_type: 'atomic_intervention_claim',
      applicability: 'primary', separability: null, status: 'active_claim', bucket: 'primary', score: { total: 108 }, rank: 1,
      reason_codes: [{ code: 'BIOMARKER_EXACT_LITERAL_MATCH', human_message: 'match' }], gate_trace: [{ gate: 'biomarker', status: 'pass', message: 'match' }], qualifiers: [],
      parent_graph_evidence_record: { parent_id: 'GEP-1' }, source_unit: null, provenance: { status: 'PARENT_ONLY', is_verifiable: false },
    }], warning: [], audit: [], rejected: [],
  },
  technical_records: { provenance_containers: [{ claim_id: 'GEP-1' } as any], unresolved_associations: [], unsupported_associations: [], deprecated_claims: [], other: [] },
  abstention: false,
  metadata: { latency_ms: 12 },
};

describe('V3EvidenceView', () => {
  it('separates clinical evidence from technical records and shows gate trace', () => {
    render(<V3EvidenceView data={response} />);
    expect(screen.getByText('Evidenze principali (1)')).toBeInTheDocument();
    expect(screen.getByText('1 claim')).toBeInTheDocument();
    expect(screen.getByText('2 record tecnici')).toBeInTheDocument();
    expect(screen.getByText(/biomarker: pass/)).toBeInTheDocument();
  });

  it('shows abstention when there are no primary or warning claims', () => {
    render(<V3EvidenceView data={{ ...response, abstention: true, summary: { ...response.summary, primary: 0 }, evidence: { ...response.evidence, primary: [] } }} />);
    expect(screen.getByText(/Nessuna evidenza direttamente applicabile/)).toBeInTheDocument();
  });
});
