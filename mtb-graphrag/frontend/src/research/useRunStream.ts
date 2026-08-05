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
import type { PipelineEvent } from './types';

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
  const closedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!runId) return;
    try {
      const [run, page] = await Promise.all([getRun(runId), getEvents(runId)]);
      dispatch({ type: 'snapshot', run });
      dispatch({ type: 'events', events: page.events });
    } catch (error) {
      dispatch({
        type: 'error',
        message: error instanceof Error ? error.message : 'Impossibile leggere la run.',
      });
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) {
      dispatch({ type: 'reset' });
      return undefined;
    }

    closedRef.current = false;
    attemptRef.current = 0;
    dispatch({ type: 'reset' });

    const close = () => {
      sourceRef.current?.close();
      sourceRef.current = null;
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const connect = () => {
      if (closedRef.current) return;
      dispatch({ type: 'connection', connection: 'connecting' });

      const source = new EventSource(streamUrl(runId));
      sourceRef.current = source;

      source.onopen = () => {
        attemptRef.current = 0;
        dispatch({ type: 'connection', connection: 'open' });
      };

      source.onmessage = (message: MessageEvent<string>) => {
        try {
          const event = JSON.parse(message.data) as PipelineEvent;
          dispatch({ type: 'events', events: [event] });
        } catch {
          // Un frame illeggibile non deve interrompere lo stream: si scarta e
          // si prosegue, perché il resume lo recupererà per sequence.
        }
      };

      source.onerror = () => {
        source.close();
        sourceRef.current = null;
        if (closedRef.current) return;

        // Il server chiude lo stream a run conclusa: non è un errore.
        void getRun(runId)
          .then((run) => {
            dispatch({ type: 'snapshot', run });
            const terminal = ['COMPLETED', 'PARTIAL', 'FAILED', 'STOPPED'].includes(run.status);
            if (terminal) {
              dispatch({ type: 'connection', connection: 'closed' });
              return;
            }
            const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)];
            attemptRef.current += 1;
            dispatch({ type: 'connection', connection: 'connecting' });
            timerRef.current = setTimeout(connect, delay);
          })
          .catch(() => {
            dispatch({ type: 'error', message: 'Connessione persa e backend non raggiungibile.' });
          });
      };
    };

    void refresh().then(connect);

    return () => {
      closedRef.current = true;
      close();
    };
  }, [runId, refresh]);

  // A run conclusa lo stream non serve più: si chiude invece di restare aperto.
  useEffect(() => {
    if (isTerminal(state) && sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
  }, [state]);

  return { state, refresh };
}
