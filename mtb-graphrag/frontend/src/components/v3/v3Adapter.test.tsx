import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import V3EvidenceExplorer from './V3EvidenceExplorer';
import V2V3ComparisonView from './V2V3ComparisonView';
import { normalizeV3Claim, createEmptyV3Response } from '../../utils/v3Adapter';

// Mock per le chiamate API Reali
vi.mock('../../api/v3Api', () => ({
  getV3Metadata: vi.fn().mockResolvedValue({
    backend_identifier: 'qualified_claim_v3',
    corpus_version: 'qualified_claim_repository/1.4',
    corpus_digest: 'digest_123',
    gate_version: 'qualified_claim_structural_gate/1.3',
    scoring_version: 'v3_operational_scoring/1.0',
    retriever_version: 'qualified_claim_retriever/1.0',
    rendering_model_identifier: 'google/gemma-2-9b-it',
    rendering_enabled: true,
    service_status: 'healthy',
    promoted_at: '2026-07-31T00:00:00Z',
    policy_mode: 'strict_verified',
  }),
  retrieveV3Evidence: vi.fn().mockResolvedValue({
    query_id: 'q_test_1',
    query: { claim_domain: 'therapeutic', biomarker: 'EGFR L858R', disease: 'Non-Small Cell Lung Cancer' },
    summary: { total: 12, primary: 3, warning: 2, audit: 4, rejected: 3 },
    buckets: {
      primary: [
        {
          claim_id: 'claim_real_001',
          parent_id: 'parent_01',
          graph_evidence_id: 'graph_01',
          claim_domain: 'therapeutic',
          claim_type: 'therapeutic_responsiveness_claim',
          bucket: 'primary',
          rank: 1,
          biomarker: 'EGFR L858R',
          disease_scope: 'Non-Small Cell Lung Cancer',
          canonical_intervention: 'Osimertinib',
          warnings: [],
          reason_codes: ['EXACT_BIOMARKER_MATCH'],
        },
      ],
      warning: [],
      audit: [],
      rejected: [],
    },
    metadata: {
      corpus_version: 'qualified_claim_repository/1.4',
      corpus_digest: 'digest_123',
      gate_version: 'qualified_claim_structural_gate/1.3',
      retriever_version: 'qualified_claim_retriever/1.0',
      run_id: 'RUN-12345678',
      policy_mode: 'strict_verified',
      elapsed_ms: 35,
    },
    warnings: [],
  }),
  renderV3Report: vi.fn().mockResolvedValue({
    query_id: 'q_test_1',
    rendered_report: 'Report generato dalle claim reali',
    claim_ids_used: ['claim_real_001'],
    cited_pmids: ['29151359'],
    disclaimer: 'Il modello genera il testo dalle claim già qualificate.',
    model_identifier: 'google/gemma-2-9b-it',
  }),
}));

describe('V3 Real API & Component Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizza correttamente una claim isolata', () => {
    const claim = normalizeV3Claim({ claim_id: 'claim_99', biomarker: 'BRAF V600E' }, 'primary', 0);
    expect(claim.claim_id).toBe('claim_99');
    expect(claim.biomarker).toBe('BRAF V600E');
    expect(claim.bucket).toBe('primary');
  });

  it('restituisce una risposta vuota ma sicura con createEmptyV3Response', () => {
    const empty = createEmptyV3Response('Errore simulato');
    expect(empty.summary.total).toBe(0);
    expect(empty.warnings).toContain('Errore simulato');
  });

  it('renderizza correttamente i metadati e la risposta reale in V3EvidenceExplorer', async () => {
    render(<V3EvidenceExplorer />);

    await waitFor(() => {
      expect(screen.getByText('MTB-GraphRAG V3')).toBeInTheDocument();
      expect(screen.getByText(/V3 LIVE RETRIEVER/i)).toBeInTheDocument();
    });

    expect(screen.getByText('claim_real_001')).toBeInTheDocument();
  });

  it('renderizza la vista di confronto V2/V3 mostrando la nota metodologica obbligatoria', () => {
    render(<V2V3ComparisonView />);

    expect(screen.getByText(/Il confronto descrive l’evoluzione della rappresentazione delle evidenze/i)).toBeInTheDocument();
    expect(screen.getByText(/V2: Record-centric/i)).toBeInTheDocument();
    expect(screen.getByText(/V3: Evidence-centric/i)).toBeInTheDocument();
  });
});
