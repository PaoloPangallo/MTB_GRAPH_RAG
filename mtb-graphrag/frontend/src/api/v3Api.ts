/**
 * Client API V3 dedicato per l'interazione con il backend FastAPI reale.
 * Invia richieste HTTP a /api/v1/v3/metadata, /api/v1/v3/retrieve e /api/v1/v3/render.
 */

import type {
  V3MetadataResponse,
  V3RetrievalRequest,
  V3RetrievalResponse,
  V3RenderRequest,
  V3RenderResponse,
} from '../types/v3Types';

const getBaseUrl = (): string => {
  return (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
};

const DEFAULT_TIMEOUT_MS = 15000;

async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: options.signal || controller.signal,
    });
    clearTimeout(id);
    return response;
  } catch (error: any) {
    clearTimeout(id);
    if (error.name === 'AbortError') {
      throw new Error(`Richiesta scaduta (timeout di ${timeoutMs}ms)`);
    }
    throw error;
  }
}

export async function getV3Metadata(signal?: AbortSignal): Promise<V3MetadataResponse> {
  const baseUrl = getBaseUrl();
  const res = await fetchWithTimeout(`${baseUrl}/api/v1/v3/metadata`, { signal });
  if (!res.ok) {
    const errorDetail = await res.text().catch(() => res.statusText);
    throw new Error(`Impossibile recuperare i metadati V3 (${res.status}): ${errorDetail}`);
  }
  return res.json();
}

export async function retrieveV3Evidence(
  request: V3RetrievalRequest,
  signal?: AbortSignal
): Promise<V3RetrievalResponse> {
  const baseUrl = getBaseUrl();
  const res = await fetchWithTimeout(
    `${baseUrl}/api/v1/v3/retrieve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    },
    20000
  );

  if (!res.ok) {
    const errorDetail = await res.text().catch(() => res.statusText);
    throw new Error(`Errore durante il retrieval V3 (${res.status}): ${errorDetail}`);
  }
  return res.json();
}

export async function renderV3Report(
  request: V3RenderRequest,
  signal?: AbortSignal
): Promise<V3RenderResponse> {
  const baseUrl = getBaseUrl();
  const res = await fetchWithTimeout(
    `${baseUrl}/api/v1/v3/render`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    },
    25000
  );

  if (!res.ok) {
    const errorDetail = await res.text().catch(() => res.statusText);
    throw new Error(`Errore durante il rendering V3 (${res.status}): ${errorDetail}`);
  }
  return res.json();
}
