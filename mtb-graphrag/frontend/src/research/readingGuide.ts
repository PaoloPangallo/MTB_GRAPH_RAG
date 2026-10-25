import type { DossierReadingGuide, ReadingFinding } from './contracts.generated';

export function readingFor(guide: DossierReadingGuide | null | undefined, candidateId: string, findingIndex: number): ReadingFinding | undefined {
  return guide?.findings.find(item => item.candidate_id === candidateId && item.finding_index === findingIndex);
}
