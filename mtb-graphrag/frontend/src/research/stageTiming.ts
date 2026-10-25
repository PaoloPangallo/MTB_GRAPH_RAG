import type { PipelineStage } from './types';

/** Prefer the measured call latency over post-hoc stage registration time. */
export function stageTiming(stage: PipelineStage): { label: string; milliseconds: number | null } {
  const key = stage.stage_id === 'stage_8_paper_selection' ? 'selection_wall_ms'
    : stage.stage_id === 'stage_9_paper_context_enricher' ? 'reader_transport_ms' : 'latency_ms';
  const measured = stage.metrics?.[key];
  if (typeof measured === 'number' && Number.isFinite(measured) && measured >= 0) {
    return { label: key === 'selection_wall_ms' ? 'Tempo selezione cumulativo'
      : key === 'reader_transport_ms' ? 'Latenza Reader cumulativa' : 'Latenza modello', milliseconds: measured };
  }
  return { label: 'Durata stage registrata', milliseconds: stage.duration_ms };
}
