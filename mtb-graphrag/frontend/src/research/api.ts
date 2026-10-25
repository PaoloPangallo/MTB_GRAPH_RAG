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
  PipelineStage,
  PipelineEvent,
  ProvenanceItem,
  RunMetrics,
} from './types';
import { apiUrl } from '../apiBase';
import {
  parseCreatedRunResponse, parseDossierResponse, parseEventPage,
  parsePublicPipelineRun, parseStageResponse,
  type DossierResponse, type PublicPipelineStage,
} from './contracts.generated';

export { API_BASE_URL } from '../apiBase';

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

async function request<T>(path: string, init?: RequestInit, validate?: (body: unknown) => unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(`${RESEARCH_PREFIX}${path}`), {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch {
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

  const body: unknown = await response.json();
  validate?.(body);
  return body as T;
}

export function listCases(): Promise<{ cases: DemoCase[] }> {
  return request('/cases');
}

export function getConfig(): Promise<Record<string, unknown>> {
  return request('/config');
}

export function createRun(body: { demo_case_key?: string; clinical_text?: string; case_id?: string }): Promise<CreatedRun> {
  return request('/runs', { method: 'POST', body: JSON.stringify(body) }, parseCreatedRunResponse);
}

/** Historical ledgers may omit empty stage collections or serialize them as null. */
type StageCollections = Pick<PublicPipelineStage, 'reason_codes' | 'warnings' | 'errors'>;
function normalizeStage<T extends StageCollections>(stage: T): Omit<T, keyof StageCollections> & Pick<PipelineStage, keyof StageCollections> {
  return {
    ...stage,
    reason_codes: stage.reason_codes ?? [],
    warnings: stage.warnings ?? [],
    errors: stage.errors ?? [],
  };
}

export async function getRun(runId: string): Promise<PipelineRun> {
  const run = await request<PipelineRun>(`/runs/${runId}?compact=true`, undefined, parsePublicPipelineRun);
  return { ...run, stages: run.stages.map(normalizeStage) };
}

export async function getStage(runId: string, stageId: string): Promise<{ stage: PipelineStage; events?: PipelineEvent[] }> {
  const response = await request<{ stage: PipelineStage; events?: PipelineEvent[] }>(`/runs/${encodeURIComponent(runId)}/stages/${encodeURIComponent(stageId)}`, undefined, parseStageResponse);
  return { ...response, stage: normalizeStage(response.stage) };
}

export function getEvents(runId: string, afterSequence = 0, limit = 500, compact = true): Promise<EventPage> {
  return request(`/runs/${runId}/events?after_sequence=${afterSequence}&limit=${limit}&compact=${compact}`, undefined, parseEventPage);
}

export function getDossier(runId: string): Promise<DossierResponse> {
  return request(`/runs/${runId}/dossier`, undefined, parseDossierResponse);
}

export function getProvenance(runId: string): Promise<{ items: ProvenanceItem[] }> {
  return request(`/runs/${runId}/provenance`);
}

export function getMetrics(runId: string): Promise<RunMetrics> {
  return request(`/runs/${runId}/metrics`);
}

export function streamUrl(runId: string): string {
  return apiUrl(`${RESEARCH_PREFIX}/runs/${runId}/stream?compact=true`);
}
