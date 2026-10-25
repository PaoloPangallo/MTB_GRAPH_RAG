import { describe, expect, it } from 'vitest';
import { makeStage } from './testFactories';
import { stageTiming } from './stageTiming';

describe('Tempi operativi reali', () => {
  it('shows measured parser latency instead of post-hoc registration time', () => {
    expect(stageTiming(makeStage({ duration_ms: 15, metrics: { latency_ms: 2108.67 } })))
      .toEqual({ label: 'Latenza modello', milliseconds: 2108.67 });
  });
  it('labels cumulative Reader latency separately from stage time', () => {
    expect(stageTiming(makeStage({ stage_id: 'stage_9_paper_context_enricher', duration_ms: 15,
      metrics: { reader_transport_ms: 7075.715 } })))
      .toEqual({ label: 'Latenza Reader cumulativa', milliseconds: 7075.715 });
  });
  it('retains missing timing as missing', () => {
    expect(stageTiming(makeStage({ duration_ms: null })).milliseconds).toBeNull();
  });
});
