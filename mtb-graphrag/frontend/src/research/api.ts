/**
 * Client del research runtime.
 *
 * Unico punto in cui il frontend conosce un URL. L'audit di Fase A aveva
 * trovato `http://localhost:8000` scritto a mano in quattro chiamate su sei,
 * con `VITE_API_BASE_URL` definito ma ignorato: la variabile dava l'impressione
 * di essere configurabile senza esserlo.
 */

import type {
  CreatedRun,
  DemoCase,
  EventPage,
  PipelineRun,
  ProvenanceItem,
  RunMetrics,
} from './types';

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000';

export const RESEARCH_PREFIX = '/api/v1/research/pipeline';

export class ResearchApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ResearchApiError';
    this.status = status;
  }
}

/** 404 sulle rotte di ricerca significa flag disattivo, non rotta inesistente. */
export function isRuntimeDisabled(error: unknown): boolean {
  return error instanceof ResearchApiError && error.status === 404;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${RESEARCH_PREFIX}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch (cause) {
    // Backend irraggiungibile. Non si restituisce un risultato vuoto: la UI
    // deve poter mostrare che non ha parlato con nessuno.
    throw new ResearchApiError(0, 'Backend non raggiungibile.');
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new ResearchApiError(response.status, detail ?? `Richiesta fallita (${response.status})`);
  }

  return (await response.json()) as T;
}

export function listCases(): Promise<{ cases: DemoCase[] }> {
  return request('/cases');
}

export function getConfig(): Promise<Record<string, unknown>> {
  return request('/config');
}

export function createRun(body: { demo_case_key?: string; clinical_text?: string; case_id?: string }): Promise<CreatedRun> {
  return request('/runs', { method: 'POST', body: JSON.stringify(body) });
}

export function getRun(runId: string): Promise<PipelineRun> {
  return request(`/runs/${runId}`);
}

export function getEvents(runId: string, afterSequence = 0, limit = 1000): Promise<EventPage> {
  return request(`/runs/${runId}/events?after_sequence=${afterSequence}&limit=${limit}`);
}

export function getDossier(runId: string): Promise<Record<string, unknown>> {
  return request(`/runs/${runId}/dossier`);
}

export function getProvenance(runId: string): Promise<{ items: ProvenanceItem[] }> {
  return request(`/runs/${runId}/provenance`);
}

export function getMetrics(runId: string): Promise<RunMetrics> {
  return request(`/runs/${runId}/metrics`);
}

export function streamUrl(runId: string): string {
  return `${API_BASE_URL}${RESEARCH_PREFIX}/runs/${runId}/stream`;
}
