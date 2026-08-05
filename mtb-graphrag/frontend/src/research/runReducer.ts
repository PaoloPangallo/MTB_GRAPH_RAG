/**
 * Stato canonico di una run, derivato da `snapshot REST + eventi SSE`.
 *
 * Regole che questo modulo fa rispettare, e che il resto della UI eredita:
 *
 * - **niente calcolo clinico nel browser.** Status, gate, bucket, score e
 *   support mask arrivano dal backend e vengono solo trasportati. Qui non
 *   esiste una funzione che li derivi;
 * - **deduplicazione per `event_id`.** Un resume SSE può rinviare eventi già
 *   visti; contarli due volte falserebbe le metriche derivate;
 * - **ordinamento per `sequence`**, mai per timestamp: due eventi possono
 *   condividere il millisecondo, la sequenza no;
 * - **stato immutabile.** Ogni transizione produce un nuovo oggetto, così una
 *   vista non può alterare quella di un'altra.
 */

import type { PipelineEvent, PipelineRun, PipelineStage } from './types';

export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface RunState {
  run: PipelineRun | null;
  events: PipelineEvent[];
  seenEventIds: ReadonlySet<string>;
  lastSequence: number;
  connection: ConnectionState;
  error: string | null;
}

export type RunAction =
  | { type: 'reset' }
  | { type: 'snapshot'; run: PipelineRun }
  | { type: 'events'; events: PipelineEvent[] }
  | { type: 'connection'; connection: ConnectionState }
  | { type: 'error'; message: string };

export const initialRunState: RunState = {
  run: null,
  events: [],
  seenEventIds: new Set<string>(),
  lastSequence: 0,
  connection: 'idle',
  error: null,
};

/** Ordina per `sequence`. Stabile a parità di sequenza, che non dovrebbe darsi. */
function bySequence(a: PipelineEvent, b: PipelineEvent): number {
  return a.sequence - b.sequence;
}

/**
 * Aggiunge eventi scartando i duplicati.
 * Restituisce `null` quando non c'è nulla di nuovo, così il chiamante può
 * evitare un render inutile.
 */
function mergeEvents(
  state: RunState,
  incoming: PipelineEvent[],
): { events: PipelineEvent[]; seen: Set<string>; lastSequence: number } | null {
  const fresh = incoming.filter((event) => !state.seenEventIds.has(event.event_id));
  if (fresh.length === 0) {
    return null;
  }

  const seen = new Set(state.seenEventIds);
  fresh.forEach((event) => seen.add(event.event_id));

  const events = [...state.events, ...fresh].sort(bySequence);
  const lastSequence = events.reduce(
    (max, event) => (event.sequence > max ? event.sequence : max),
    state.lastSequence,
  );

  return { events, seen, lastSequence };
}

export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case 'reset':
      return { ...initialRunState, seenEventIds: new Set<string>() };

    case 'snapshot':
      return { ...state, run: action.run, error: null };

    case 'events': {
      const merged = mergeEvents(state, action.events);
      if (merged === null) {
        return state;
      }
      return {
        ...state,
        events: merged.events,
        seenEventIds: merged.seen,
        lastSequence: merged.lastSequence,
      };
    }

    case 'connection':
      return { ...state, connection: action.connection };

    case 'error':
      return { ...state, connection: 'error', error: action.message };

    default:
      return state;
  }
}

// --- Selettori ---------------------------------------------------------------
// Aggregano soltanto dati già presenti nello stato. Nessuno di essi decide
// alcunché: contano, raggruppano, ordinano.

export function stagesInOrder(state: RunState): PipelineStage[] {
  if (!state.run) return [];
  return [...state.run.stages].sort((a, b) => a.sequence - b.sequence);
}

export function stageById(state: RunState, stageId: string): PipelineStage | null {
  return stagesInOrder(state).find((stage) => stage.stage_id === stageId) ?? null;
}

export function eventsForStage(state: RunState, stageId: string): PipelineEvent[] {
  return state.events.filter((event) => event.stage_id === stageId);
}

/**
 * Conteggi derivabili dallo stato, dichiaratamente calcolati nel browser.
 * Le metriche canoniche vivono in `GET /runs/{id}/metrics` e non vanno confuse
 * con questi: servono solo a etichettare la timeline.
 */
export interface DerivedCounts {
  total: number;
  succeeded: number;
  warning: number;
  failed: number;
  skipped: number;
  llmStages: number;
  derivedInBrowser: true;
}

export function derivedCounts(state: RunState): DerivedCounts {
  const stages = stagesInOrder(state);
  const count = (status: string) => stages.filter((s) => s.status === status).length;
  return {
    total: stages.length,
    succeeded: count('SUCCEEDED'),
    warning: count('WARNING'),
    failed: count('FAILED'),
    skipped: count('SKIPPED'),
    llmStages: stages.filter((s) => s.producer.kind === 'LLM').length,
    derivedInBrowser: true,
  };
}

/** Vero quando la run non può più cambiare: lo stream può chiudersi. */
export function isTerminal(state: RunState): boolean {
  const status = state.run?.status;
  return status === 'COMPLETED' || status === 'PARTIAL' || status === 'FAILED' || status === 'STOPPED';
}
