import { describe, expect, it } from 'vitest';
import { documentaryChecks, findingCounts } from './documentaryFindings';

describe('documentary observations without inferred scientific verdicts', () => {
  it('keeps authentication, structural ambiguity and unexecuted semantics separate', () => {
    expect(documentaryChecks({ quote_valid: true, document_verification: { structural_status: 'UNRESOLVED', final_admission: 'NOT_RUN_STRUCTURAL', semantic_assessment: {} } })).toEqual({ quotation: 'Autenticata', structural: 'UNRESOLVED', semantic: 'Non eseguita' });
  });
  it('distinguishes technical failures from completed assessments', () => {
    expect(documentaryChecks({ document_verification: { verification_status: 'TECHNICAL_ERROR', semantic_assessment: {} } }).semantic).toBe('Errore tecnico');
    expect(documentaryChecks({ document_verification: { verification_status: 'ASSESSED' } }).semantic).toBe('Valutazione registrata');
  });
  it('does not infer checks from a historical support label', () => {
    expect(documentaryChecks({ support_level: 'FULL_SUPPORT' })).toEqual({ quotation: 'Non registrata', structural: 'Non registrato', semantic: 'Non registrata' });
  });
  it('distinguishes statement policy from missing drug verification', () => {
    expect(documentaryChecks({ relation_family: 'EVIDENCE_STATEMENT' }).semantic).toBe('Non prevista dalla policy');
    expect(documentaryChecks({ relation_family: 'EVIDENCE_DRUG' }).semantic).toBe('Non registrata');
  });
  it('counts records and publications separately, deduplicating record identities', () => {
    const record = { evidence_id: 'E1', paper_id: 'pmid:1', quote_valid: true };
    expect(findingCounts({ paper_evidence: [{ candidate_id: 'A', accepted_evidence_records: [record, { ...record, evidence_id: 'E2' }] }, { candidate_id: 'B', accepted_evidence_records: [record] }] })).toEqual({ relations: 2, records: 2, authenticated: 2, publications: 1 });
  });
});
