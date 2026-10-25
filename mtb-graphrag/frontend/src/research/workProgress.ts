import type { PipelineEvent, RunStatus } from './types';

export type WorkPhase = 'SOURCEUNIT_SELECTION' | 'READER' | 'VERIFICATION'
  | 'SEMANTIC_VERIFICATION' | 'CANDIDATE_COMPLETED';

export interface WorkProgress {
  phase: WorkPhase;
  completedCandidates: number;
  totalCandidates: number;
  readerCalls: number;
  readerReuses: number;
  candidateId: string;
  documentId: string | null;
}

const phases: ReadonlySet<string> = new Set([
  'SOURCEUNIT_SELECTION', 'READER', 'VERIFICATION', 'SEMANTIC_VERIFICATION', 'CANDIDATE_COMPLETED',
]);

/** Absolute backend counters; replayed SSE frames never increment them. */
export function latestWorkProgress(events: readonly PipelineEvent[], status?: RunStatus): WorkProgress | null {
  if (status !== 'RUNNING') return null;
  let latest: PipelineEvent | undefined;
  for (const event of events) {
    if (event.event_type === 'PIPELINE_WORK_PROGRESS' && (!latest || event.sequence > latest.sequence)) latest = event;
  }
  if (!latest) return null;
  const p = latest.payload;
  const counters = [p.completed_candidates, p.total_candidates, p.reader_calls, p.reader_reuses];
  if (typeof p.phase !== 'string' || !phases.has(p.phase) || typeof p.candidate_id !== 'string'
    || counters.some(value => typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)) return null;
  const completed = p.completed_candidates as number;
  const total = p.total_candidates as number;
  if (total < 1 || completed > total) return null;
  return { phase: p.phase as WorkPhase, completedCandidates: completed, totalCandidates: total,
    readerCalls: p.reader_calls as number, readerReuses: p.reader_reuses as number,
    candidateId: p.candidate_id, documentId: typeof p.document_id === 'string' ? p.document_id : null };
}
