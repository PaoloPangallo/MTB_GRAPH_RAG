import type { PipelineStage } from './types';

export const STAGE_FILTERS = [
  { key: 'all', label: 'Tutti' },
  { key: 'problems', label: 'Warning ed errori' },
  { key: 'llm', label: 'Producer LLM' },
  { key: 'deterministic', label: 'Producer codice' },
] as const;

export type StageFilterKey = (typeof STAGE_FILTERS)[number]['key'];

/** Filtro applicato a uno stage. */
export function matchesFilter(stage: PipelineStage, filter: StageFilterKey): boolean {
  switch (filter) {
    case 'problems':
      return stage.status === 'FAILED' || stage.status === 'WARNING'
        || stage.warnings.length > 0 || stage.errors.length > 0;
    case 'llm':
      return stage.producer.kind === 'LLM';
    case 'deterministic':
      return stage.producer.kind === 'DETERMINISTIC';
    default:
      return true;
  }
}
