import { describe, expect, it } from 'vitest';
import {
  derivedCounts,
  eventsForStage,
  initialRunState,
  isTerminal,
  runReducer,
  stageById,
  stagesInOrder,
  type RunState,
} from './runReducer';
import type { PipelineEvent, PipelineRun, PipelineStage } from './types';

function event(sequence: number, overrides: Partial<PipelineEvent> = {}): PipelineEvent {
  return {
    event_id: `evt-${sequence}`,
    sequence,
    event_type: 'STAGE_COMPLETED',
    created_at: '2026-08-04T00:00:00Z',
    actor: 'orchestrator',
    stage_id: 'stage_1_case_input',
    stage_type: 'CASE_INPUT',
    producer: {
      kind: 'DETERMINISTIC',
      component: 'orchestrator',
      version: '1.0',
      model: null,
      prompt_version: null,
    },
    payload_hash: 'abc',
    payload: {},
    ...overrides,
  };
}

function stage(sequence: number, overrides: Partial<PipelineStage> = {}): PipelineStage {
  return {
    stage_id: `stage_${sequence}_x`,
    stage_type: 'X',
    sequence,
    status: 'SUCCEEDED',
    started_at: null,
    completed_at: null,
    duration_ms: 10,
    input_preview: {},
    output_preview: {},
    reason_codes: [],
    warnings: [],
    errors: [],
    producer: {
      kind: 'DETERMINISTIC',
      component: 'c',
      version: '1',
      model: null,
      prompt_version: null,
    },
    metrics: {},
    lineage: {},
    ...overrides,
  };
}

function run(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    run_id: 'r1',
    case_id: 'CASE-1',
    status: 'RUNNING',
    started_at: '2026-08-04T00:00:00Z',
    completed_at: null,
    current_stage: null,
    stopped_at: null,
    input_text: 'testo',
    stages: [],
    dossier_id: null,
    warnings: [],
    errors: [],
    versions: {},
    metrics: {},
    research_notice: {
      runtime: 'VERIFIABLE_RESEARCH_RUNTIME',
      clinically_validated: false,
      not_for_clinical_decision_making: true,
      experimental_component: true,
    },
    ...overrides,
  };
}

function withEvents(events: PipelineEvent[]): RunState {
  return runReducer(initialRunState, { type: 'events', events });
}

describe('deduplicazione degli eventi', () => {
  it('scarta un evento già visto', () => {
    const once = withEvents([event(1)]);
    const twice = runReducer(once, { type: 'events', events: [event(1)] });

    expect(twice.events).toHaveLength(1);
  });

  it('restituisce lo stesso oggetto quando non c’è nulla di nuovo', () => {
    const once = withEvents([event(1)]);
    const again = runReducer(once, { type: 'events', events: [event(1)] });

    // Identità referenziale: evita un render inutile.
    expect(again).toBe(once);
  });

  it('accetta un evento nuovo insieme a uno duplicato', () => {
    const once = withEvents([event(1)]);
    const merged = runReducer(once, { type: 'events', events: [event(1), event(2)] });

    expect(merged.events.map((e) => e.sequence)).toEqual([1, 2]);
  });

  it('un resume che rinvia la coda non duplica nulla', () => {
    const initial = withEvents([event(1), event(2), event(3)]);
    const resumed = runReducer(initial, { type: 'events', events: [event(2), event(3), event(4)] });

    expect(resumed.events.map((e) => e.sequence)).toEqual([1, 2, 3, 4]);
  });
});

describe('ordinamento', () => {
  it('ordina per sequence anche se gli eventi arrivano fuori ordine', () => {
    const state = withEvents([event(3), event(1), event(2)]);
    expect(state.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
  });

  it('non si affida al timestamp', () => {
    const state = withEvents([
      event(2, { created_at: '2026-01-01T00:00:00Z' }),
      event(1, { created_at: '2026-12-31T00:00:00Z' }),
    ]);

    expect(state.events.map((e) => e.sequence)).toEqual([1, 2]);
  });

  it('tiene traccia della sequenza massima per il resume', () => {
    expect(withEvents([event(1), event(7), event(3)]).lastSequence).toBe(7);
  });
});

describe('immutabilità', () => {
  it('non muta lo stato precedente', () => {
    const before = withEvents([event(1)]);
    const eventsBefore = before.events;
    runReducer(before, { type: 'events', events: [event(2)] });

    expect(before.events).toBe(eventsBefore);
    expect(before.events).toHaveLength(1);
  });

  it('reset riparte da zero', () => {
    const populated = withEvents([event(1), event(2)]);
    const cleared = runReducer(populated, { type: 'reset' });

    expect(cleared.events).toHaveLength(0);
    expect(cleared.lastSequence).toBe(0);
  });
});

describe('connessione ed errore', () => {
  it('registra lo stato della connessione', () => {
    const state = runReducer(initialRunState, { type: 'connection', connection: 'open' });
    expect(state.connection).toBe('open');
  });

  it('un errore non produce una run', () => {
    const state = runReducer(initialRunState, { type: 'error', message: 'backend offline' });

    expect(state.connection).toBe('error');
    expect(state.error).toBe('backend offline');
    expect(state.run).toBeNull();
  });

  it('uno snapshot cancella l’errore precedente', () => {
    const failed = runReducer(initialRunState, { type: 'error', message: 'x' });
    const recovered = runReducer(failed, { type: 'snapshot', run: run() });

    expect(recovered.error).toBeNull();
  });
});

describe('selettori', () => {
  const state = runReducer(initialRunState, {
    type: 'snapshot',
    run: run({
      stages: [
        stage(3, { status: 'SKIPPED', reason_codes: ['NOT_IMPLEMENTED'] }),
        stage(1),
        stage(2, { status: 'WARNING', producer: { kind: 'LLM', component: 'e', version: '2', model: 'gemma4:cloud', prompt_version: 'p/2' } }),
      ],
    }),
  });

  it('ordina gli stage per sequence', () => {
    expect(stagesInOrder(state).map((s) => s.sequence)).toEqual([1, 2, 3]);
  });

  it('trova uno stage per id', () => {
    expect(stageById(state, 'stage_2_x')?.sequence).toBe(2);
  });

  it('restituisce null per uno stage inesistente', () => {
    expect(stageById(state, 'stage_99_x')).toBeNull();
  });

  it('filtra gli eventi di uno stage', () => {
    const withStageEvents = runReducer(state, {
      type: 'events',
      events: [event(1, { stage_id: 'stage_1_case_input' }), event(2, { stage_id: 'stage_2_x' })],
    });

    expect(eventsForStage(withStageEvents, 'stage_2_x')).toHaveLength(1);
  });

  it('i conteggi derivati si dichiarano tali', () => {
    const counts = derivedCounts(state);

    expect(counts.total).toBe(3);
    expect(counts.warning).toBe(1);
    expect(counts.skipped).toBe(1);
    expect(counts.llmStages).toBe(1);
    expect(counts.derivedInBrowser).toBe(true);
  });
});

describe('terminalità', () => {
  it.each(['COMPLETED', 'PARTIAL', 'FAILED', 'STOPPED'] as const)(
    '%s è terminale',
    (status) => {
      const state = runReducer(initialRunState, { type: 'snapshot', run: run({ status }) });
      expect(isTerminal(state)).toBe(true);
    },
  );

  it.each(['CREATED', 'RUNNING'] as const)('%s non è terminale', (status) => {
    const state = runReducer(initialRunState, { type: 'snapshot', run: run({ status }) });
    expect(isTerminal(state)).toBe(false);
  });

  it('senza run non è terminale', () => {
    expect(isTerminal(initialRunState)).toBe(false);
  });
});

describe('il browser non calcola nulla di clinico', () => {
  it('lo status arriva dal backend e non viene ricalcolato', () => {
    const state = runReducer(initialRunState, { type: 'snapshot', run: run({ status: 'STOPPED', stopped_at: 'RETRIEVAL_NO_MATCH' }) });

    expect(state.run?.status).toBe('STOPPED');
    expect(state.run?.stopped_at).toBe('RETRIEVAL_NO_MATCH');
  });

  it('il reducer non espone alcuna funzione che derivi status o gate', () => {
    const exported = Object.keys({ runReducer, stagesInOrder, stageById, eventsForStage, derivedCounts, isTerminal });
    const forbidden = exported.filter((name) => /status|gate|bucket|score|mask/i.test(name));

    expect(forbidden).toEqual([]);
  });
});
