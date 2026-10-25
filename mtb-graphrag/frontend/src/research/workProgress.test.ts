import { describe, expect, it } from 'vitest';
import { latestWorkProgress } from './workProgress';
import type { PipelineEvent } from './types';

function event(sequence: number, payload: Record<string, unknown>): PipelineEvent {
  return { event_id: `e-${sequence}`, sequence, event_type: 'PIPELINE_WORK_PROGRESS',
    created_at: '2026-10-03T12:00:00Z', actor: 'orchestrator', stage_id: 'stage_9_paper_context_enricher',
    stage_type: 'PAPER_CONTEXT_ENRICHER', producer: { kind: 'DETERMINISTIC', component: 'orchestrator',
      version: '2.1', model: null, prompt_version: null }, payload_hash: 'h', payload };
}

describe('avanzamento del lavoro effettivo', () => {
  it('mostra Reader e documenti dalla sequenza più recente, senza contare due volte gli eventi', () => {
    const early = event(1, { phase: 'SOURCEUNIT_SELECTION', completed_candidates: 0, total_candidates: 30,
      reader_calls: 0, reader_reuses: 0, candidate_id: 'a' });
    const latest = event(2, { phase: 'READER', completed_candidates: 4, total_candidates: 30,
      reader_calls: 8, reader_reuses: 2, candidate_id: 'b', document_id: 'nct:NCT12345678' });
    expect(latestWorkProgress([latest, early, latest], 'RUNNING')).toEqual({
      phase: 'READER', completedCandidates: 4, totalCandidates: 30, readerCalls: 8,
      readerReuses: 2, candidateId: 'b', documentId: 'nct:NCT12345678',
    });
  });
  it('non mostra attività in corso per una run terminata o payload incompleti', () => {
    expect(latestWorkProgress([event(1, {})], 'RUNNING')).toBeNull();
    expect(latestWorkProgress([event(1, {})], 'FAILED')).toBeNull();
    const valid = event(2, { phase: 'READER', completed_candidates: 1, total_candidates: 3,
      reader_calls: 2, reader_reuses: 0, candidate_id: 'a' });
    expect(latestWorkProgress([valid], 'COMPLETED')).toBeNull();
    expect(latestWorkProgress([valid], 'FAILED')).toBeNull();
  });
});
