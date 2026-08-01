import { fireEvent, render, screen } from '@testing-library/react';
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

  it('offers the coordinated pipeline, provenance and technical views', () => {
    render(<V3EvidenceView data={response} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Pipeline' }));
    expect(screen.getByText('CaseContext normalizzato')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Provenienza' }));
    expect(screen.getByText(/Catena verificabile/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Dati tecnici' }));
    expect(screen.getByText(/non sono evidenze cliniche/)).toBeInTheDocument();
  });

  it('renders missing native score as unavailable instead of zero', () => {
    render(<V3EvidenceView data={{ ...response, evidence: { ...response.evidence, primary: [{ ...response.evidence.primary[0], score: {} }] } }} />);
    expect(screen.getByText('Punteggio strutturale: non disponibile')).toBeInTheDocument();
  });

  it('renders source-aware claim fallback and separates case comparison values', () => {
    const enriched = {
      ...response,
      case_context: {
        original: { gene: 'EGFR', alteration: 'L858R', interventions: [], direction: '' },
        normalized_biomarker: 'EGFR L858R',
        normalized_interventions: [],
      },
      evidence: {
        ...response.evidence,
        primary: [{
          ...response.evidence.primary[0],
          claim_text: null,
          subject: null,
          relation: null,
          object: null,
          direction: 'sensitivity',
          applicability: null,
          bucket: 'primary',
          claim: {
            claim_text: null,
            subject: null,
            relation: null,
            object: null,
            biomarker: 'EGFR L858R',
            intervention: 'gefitinib',
            direction: 'sensitivity',
            structured_tuple_complete: false,
          },
          decision: {
            bucket: 'primary',
            applicability: null,
            structural_score: 0,
            structural_score_eligible: false,
          },
          case_comparison: {
            biomarker: {
              query_value_original: 'L858R',
              query_value_normalized: 'EGFR L858R',
              claim_value: 'EGFR L858R',
              comparison_result: 'exact',
              availability: 'AVAILABLE',
            },
            intervention: {
              query_value_original: [],
              query_value_normalized: [],
              claim_value: 'gefitinib',
              comparison_result: 'no_intervention_constraint',
              not_applicable_reason: 'NOT_PROVIDED_BY_CASE',
              availability: 'NOT_PROVIDED_BY_CASE',
            },
            direction: {
              query_value_original: '',
              query_value_normalized: null,
              claim_value: 'sensitivity',
              comparison_result: 'not_constrained',
              not_applicable_reason: 'NOT_PROVIDED_BY_CASE',
              availability: 'NOT_PROVIDED_BY_CASE',
            },
          },
          reason_codes: [
            { code: 'BIOMARKER_EXACT_LITERAL_MATCH', gate: 'biomarker', human_message: 'Il biomarcatore coincide esattamente.' },
            { code: 'DISEASE_EXACT_MATCH', gate: 'disease', human_message: 'La malattia coincide esattamente.' },
          ],
        } as any],
      },
    } as V3RetrieveResponse;

    render(<V3EvidenceView data={enriched} />);
    expect(screen.getByText('CaseContext')).toBeInTheDocument();
    expect(screen.getByText('Tripla strutturata non disponibile nel record sorgente')).toBeInTheDocument();
    expect(screen.getByText('Sensibilità')).toBeInTheDocument();
    expect(screen.getByText(/Caso: L858R/)).toBeInTheDocument();
    expect(screen.getByText(/Claim: EGFR L858R/)).toBeInTheDocument();
    expect(screen.getByText(/Caso: nessun intervento richiesto/)).toBeInTheDocument();
    expect(screen.getByText(/Claim: gefitinib/)).toBeInTheDocument();
    expect(screen.getByText('Applicabilità non valutata separatamente')).toBeInTheDocument();
    expect(screen.getByText('Punteggio strutturale: Non applicabile')).toBeInTheDocument();
    expect(screen.queryByText('not_constrained')).not.toBeInTheDocument();
  });

  it('renders an eligible structural score as the real value and translates resistance', () => {
    const enriched = {
      ...response,
      evidence: {
        ...response.evidence,
        primary: [{
          ...response.evidence.primary[0],
          direction: 'resistance',
          score: { total: 108 },
          claim: { claim_text: 'ALK G1202R confers resistance to alectinib', structured_tuple_complete: false, direction: 'resistance' },
          decision: { bucket: 'primary', applicability: 'primary', structural_score: 108, structural_score_eligible: true },
          case_comparison: {
            direction: {
              query_value_original: 'resistance',
              query_value_normalized: 'resistance',
              claim_value: 'resistance',
              comparison_result: 'exact',
              availability: 'AVAILABLE',
            },
          },
        } as any],
      },
    } as V3RetrieveResponse;

    render(<V3EvidenceView data={enriched} />);
    expect(screen.getByText('Resistenza')).toBeInTheDocument();
    expect(screen.getByText('Punteggio strutturale: 108')).toBeInTheDocument();
  });

  it('preserves claim text and a complete structured tuple when supplied by the source', () => {
    const sourceClaim = {
      ...response.evidence.primary[0],
      claim_text: 'EGFR L858R predicts response to gefitinib',
      subject: 'EGFR L858R',
      relation: 'predicts response to',
      object: 'gefitinib',
      claim: {
        claim_text: 'EGFR L858R predicts response to gefitinib',
        subject: 'EGFR L858R',
        relation: 'predicts response to',
        object: 'gefitinib',
        structured_tuple_complete: true,
      },
    } as any;
    render(<V3EvidenceView data={{ ...response, evidence: { ...response.evidence, primary: [sourceClaim] } }} />);
    expect(screen.getByText('EGFR L858R predicts response to gefitinib')).toBeInTheDocument();
    expect(screen.queryByText('Tripla strutturata non disponibile nel record sorgente')).not.toBeInTheDocument();
  });

  it('distinguishes missing claim values and unavailable decision scores', () => {
    const missing = {
      ...response.evidence.primary[0],
      claim_text: null,
      decision: { bucket: 'primary', applicability: null, structural_score: null, structural_score_eligible: true },
      case_comparison: {
        biomarker: {
          query_value_original: 'EGFR L858R',
          query_value_normalized: 'EGFR L858R',
          claim_value: null,
          comparison_result: null,
          not_applicable_reason: 'MISSING_IN_CLAIM',
          availability: 'MISSING_IN_CLAIM',
        },
      },
    } as any;
    render(<V3EvidenceView data={{ ...response, evidence: { ...response.evidence, primary: [missing] } }} />);
    expect(screen.getByText('Punteggio strutturale: non disponibile')).toBeInTheDocument();
    expect(screen.getByText(/Stato: MISSING_IN_CLAIM/)).toBeInTheDocument();
  });

  it('shows clinical abstention before excluded candidates for an RMI2 case', () => {
    const excluded = {
      ...response.evidence.primary[0],
      claim_id: 'CLM-EXCLUDED-RMI2',
      biomarker: 'FGFR2::BICC1 Fusion',
      bucket: 'rejected',
      intervention: 'infigratinib + pd173074',
    };
    const view = render(<V3EvidenceView data={{
      ...response,
      summary: { ...response.summary, total_records: 2, claim_records: 1, technical_records: 1, primary: 0, rejected_claims: 1 },
      abstention: true,
      evidence: { ...response.evidence, primary: [], rejected: [excluded] },
    }} />);
    const text = view.container.textContent || '';
    expect(screen.getByText(/Nessuna evidenza direttamente applicabile/)).toBeInTheDocument();
    expect(screen.getByText('Evidenze principali (0)')).toBeInTheDocument();
    expect(screen.getByText('Evidenze escluse (1)')).toBeInTheDocument();
    expect(screen.queryByText('Evidenze principali (1)')).not.toBeInTheDocument();
    expect(text.indexOf('Nessuna evidenza direttamente applicabile')).toBeLessThan(text.indexOf('Evidenze escluse (1)'));
  });
});
