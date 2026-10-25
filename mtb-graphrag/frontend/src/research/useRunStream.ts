/**
 * Sottoscrizione SSE a una run, con snapshot iniziale e riconnessione.
 *
 * Ogni comportamento richiesto dal contratto SSE vive qui:
 * - snapshot REST prima dello stream, così un refresh non perde la trace;
 * - deduplicazione e ordinamento delegati al reducer, non rifatti qui;
 * - riconnessione con backoff esponenziale;
 * - **smontaggio del listener**: l'audit di Fase A segnalava gli SSE listener
 *   non smontati come difetto da eliminare, quindi la chiusura è esplicita e
 *   coperta da test;
 * - nessun polling in parallelo allo stream.
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { getEvents, getRun, streamUrl } from './api';
import { initialRunState, isTerminal, runReducer, type RunState } from './runReducer';
import { SSE_EVENT_TYPES, type PipelineEvent } from './types';
import { parsePublicEvent, ResearchContractError } from './contracts.generated';

const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000, 30000];

export interface UseRunStreamResult {
  state: RunState;
  refresh: () => Promise<void>;
}

export function useRunStream(runId: string | null): UseRunStreamResult {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const sourceRef = useRef<EventSource | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generationRef = useRef(0);
  const cursorRef = useRef(0);
  const pendingRefreshRef = useRef<number | null>(null);
  const refreshingRef = useRef<number | null>(null);
  const subscriptionRunRef = useRef<string | null>(null);
  const terminalRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!runId || subscriptionRunRef.current !== runId) return;
    const generation = generationRef.current;
    if (refreshingRef.current === generation) {
      pendingRefreshRef.current = generation;
      return;
    }
    refreshingRef.current = generation;
    try {
      do {
      pendingRefreshRef.current = null;
      const run = await getRun(runId);
      if (generationRef.current !== generation || run.run_id !== runId) return;
      const terminal = ['COMPLETED', 'PARTIAL', 'FAILED', 'STOPPED'].includes(run.status);
      if (terminalRef.current && !terminal) return;
      terminalRef.current = terminal;
      dispatch({ type: 'snapshot', run });
      let more = true;
      while (more) {
        const page = await getEvents(runId, cursorRef.current);
        if (generationRef.current !== generation || page.run_id !== runId) return;
        dispatch({ type: 'events', events: page.events });
        const previous = cursorRef.current;
        cursorRef.current = Math.max(previous, page.next_after_sequence);
        more = page.has_more && cursorRef.current > previous;
      }
      } while (pendingRefreshRef.current === generation && generationRef.current === generation);
    } catch (error) {
      if (generationRef.current !== generation) return;
      dispatch({
        type: 'error',
        message: error instanceof Error ? error.message : 'Impossibile leggere la run.',
      });
    } finally {
      if (refreshingRef.current === generation) refreshingRef.current = null;
    }
  }, [runId]);

  useEffect(() => {
    generationRef.current += 1;
    subscriptionRunRef.current = runId;
    cursorRef.current = 0;
    terminalRef.current = false;
    let active = true;
    if (!runId) {
      dispatch({ type: 'reset' });
      return undefined;
    }

    attemptRef.current = 0;
    dispatch({ type: 'reset' });

    // Gli eventi arrivano a raffica: si coalizzano in una sola rilettura, così
    // una run da 40 eventi non produce 40 richieste.
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleRefresh = () => {
      if (refreshTimer !== null || !active) return;
      refreshTimer = setTimeout(() => {
        refreshTimer = null;
        if (active) void refresh();
      }, 150);
    };

    const close = () => {
      sourceRef.current?.close();
      sourceRef.current = null;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (refreshTimer !== null) {
        clearTimeout(refreshTimer);
        refreshTimer = null;
      }
    };

    const connect = () => {
      if (!active || terminalRef.current) return;
      dispatch({ type: 'connection', connection: 'connecting' });

      const source = new EventSource(streamUrl(runId));
      sourceRef.current = source;

      source.onopen = () => {
        if (!active || terminalRef.current || sourceRef.current !== source) return;
        attemptRef.current = 0;
        dispatch({ type: 'connection', connection: 'open' });
        // Recover missed REST history even when reconnection emits no new stage event.
        void refresh();
      };

      const handle = (message: MessageEvent<string>) => {
        if (!active) return;
        try {
          const event = parsePublicEvent(JSON.parse(message.data)) as PipelineEvent;
          dispatch({ type: 'events', events: [event] });

          // Gli eventi portano l'avanzamento, ma gli **stage** vivono nello
          // snapshot: senza questo rinfresco la spina resterebbe ferma allo
          // stato che il backend aveva quando la run è stata aperta. Non è
          // polling — è una rilettura guidata dagli eventi, e la fonte di
          // verità resta una sola.
          if (event.event_type.startsWith('STAGE_') || event.event_type === 'RUN_COMPLETED') {
            scheduleRefresh();
          }
        } catch (error) {
          if (error instanceof ResearchContractError) {
            dispatch({ type: 'error', message: error.message });
            scheduleRefresh();
            return;
          }
          // Un frame illeggibile non deve interrompere lo stream: si scarta e
          // si prosegue, perché il resume lo recupererà per sequence.
        }
      };

      // Lo stream invia eventi **con nome**, e `onmessage` intercetta solo
      // quelli senza. Registrarlo da solo lascerebbe il client muto davanti a
      // uno stream perfettamente valido: serve un listener per ogni tipo.
      SSE_EVENT_TYPES.forEach((type) => source.addEventListener(type, handle as EventListener));
      source.onmessage = handle;

      source.onerror = () => {
        if (!active || sourceRef.current !== source) return;
        source.close();
        if (!active) return;
        sourceRef.current = null;

        const scheduleReconnect = () => {
          if (!active || terminalRef.current || timerRef.current !== null) return;
          const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)];
          attemptRef.current += 1;
          timerRef.current = setTimeout(() => {
            timerRef.current = null;
            connect();
          }, delay);
        };

        // Il server chiude lo stream a run conclusa: non è un errore.
        void getRun(runId)
          .then((run) => {
            if (!active || terminalRef.current || run.run_id !== runId) return;
            dispatch({ type: 'snapshot', run });
            const terminal = ['COMPLETED', 'PARTIAL', 'FAILED', 'STOPPED'].includes(run.status);
            if (terminal) {
              terminalRef.current = true;
              dispatch({ type: 'connection', connection: 'closed' });
              // Completion may have happened while offline; recover the final event tail.
              void refresh();
              return;
            }
            dispatch({ type: 'connection', connection: 'connecting' });
            scheduleReconnect();
          })
          .catch(() => {
            if (!active || terminalRef.current) return;
            dispatch({ type: 'error', message: 'Connessione persa e backend non raggiungibile. Riconnessione automatica in corso.' });
            scheduleReconnect();
          });
      };
    };

    // Lo stream si apre **subito**, e lo snapshot arriva in parallelo.
    //
    // Aspettare lo snapshot prima di sottoscrivere apriva una finestra in cui
    // gli eventi emessi nel frattempo andavano perduti, e legava l'apertura
    // dello stream alla risoluzione di una promise — fragile rispetto al doppio
    // montaggio di StrictMode, dove il cleanup interveniva prima. La
    // sovrapposizione fra storico dello stream e snapshot è innocua: il reducer
    // deduplica per event_id, ed è precisamente il caso per cui esiste.
    connect();
    void refresh();

    return () => {
      active = false;
      generationRef.current += 1;
      subscriptionRunRef.current = null;
      close();
    };
  }, [runId, refresh]);

  // A run conclusa lo stream non serve più: si chiude invece di restare aperto.
  useEffect(() => {
    if (state.run?.run_id === runId && isTerminal(state)) {
      terminalRef.current = true;
      sourceRef.current?.close();
      sourceRef.current = null;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (state.connection !== 'closed') dispatch({ type: 'connection', connection: 'closed' });
    }
  }, [state, runId]);

  return { state, refresh };
}
