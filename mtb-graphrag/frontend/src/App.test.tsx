/**
 * Le due pipeline devono restare su rotte distinte.
 *
 * Il difetto che questi test bloccano è già accaduto una volta: la vista
 * storica era la schermata iniziale, e uno screenshot della home mostrava
 * `qualified_claim_repository/1.4` come se fosse la pipeline verificabile.
 * Non era un errore di lettura — la pagina non offriva alcun modo di
 * distinguerle.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { VERIFIABLE_PIPELINE_ROUTE } from './routes';
import { expectNoObjectObject } from './research/values/testing';

/** Il backend non è in gioco qui: si verificano rotte, non dati. */
function stubBackend() {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('offline nel test'))));
  vi.stubGlobal('EventSource', class {
    close() {}
    addEventListener() {}
  } as unknown as typeof EventSource);
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('rotte', () => {
  beforeEach(() => {
    stubBackend();
  });

  it('la radice porta alla pipeline verificabile, non alla vista storica', async () => {
    renderAt('/');
    expect(await screen.findByText(/Dal testo clinico al dossier/i)).toBeInTheDocument();
  });

  it('un percorso sconosciuto porta alla pipeline verificabile', async () => {
    renderAt('/qualcosa/che-non-esiste');
    expect(await screen.findByText(/Dal testo clinico al dossier/i)).toBeInTheDocument();
  });

  it('la rotta della pipeline mostra l’ingresso in testo libero', async () => {
    renderAt(VERIFIABLE_PIPELINE_ROUTE);
    expect(
      await screen.findByLabelText('Testo clinico in linguaggio libero'),
    ).toBeInTheDocument();
  });

  it('un vecchio URL porta al runtime corrente', async () => {
    renderAt('/legacy/v3-deterministic');
    expect(await screen.findByLabelText('Testo clinico in linguaggio libero')).toBeInTheDocument();
    expect(screen.queryByText(/Legacy V3/i)).not.toBeInTheDocument();
  });

  it('la rotta architecture apre il caso reale senza avviare automaticamente una run', async () => {
    renderAt('/architecture');
    expect(await screen.findByLabelText('Testo clinico in linguaggio libero')).toBeInTheDocument();
    expect(screen.getByText('Run reale')).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false);
  });

  it('la rotta architecture apre la demo offline senza chiamare il backend', async () => {
    renderAt('/architecture?mode=demo');
    expect(await screen.findByRole('heading', { name: 'Come GCA4 costruisce un dossier' })).toBeInTheDocument();
    expect(screen.getByText(/Nessuna chiamata al backend/)).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('la console non contiene un collegamento al runtime rimosso', async () => {
    renderAt(VERIFIABLE_PIPELINE_ROUTE);
    await screen.findByLabelText('Testo clinico in linguaggio libero');
    expect(screen.queryByRole('link', { name: /Legacy V3/i })).not.toBeInTheDocument();
  });
});

describe('vocabolario della rotta nuova', () => {
  beforeEach(() => {
    stubBackend();
  });

  /** Termini della pipeline precedente. Qui significherebbero trace mescolate. */
  const legacyTerms = [
    /qualified[_ ]claim/i,
    /Parent GraphEvidenceRecord/i,
    /Evidenze principali/i,
    /Applicabilità non valutata separatamente/i,
  ];

  it.each(legacyTerms)('non contiene %s', async (term) => {
    const { container } = renderAt(VERIFIABLE_PIPELINE_ROUTE);
    await screen.findByLabelText('Testo clinico in linguaggio libero');
    expect(container.textContent).not.toMatch(term);
  });

  it('dichiara che il sistema non formula raccomandazioni cliniche', async () => {
    renderAt(VERIFIABLE_PIPELINE_ROUTE);
    expect(
      await screen.findByText(/non formula raccomandazioni cliniche/i),
    ).toBeInTheDocument();
  });

  it('non rende alcun oggetto come stringa', async () => {
    const { container } = renderAt(VERIFIABLE_PIPELINE_ROUTE);
    await screen.findByLabelText('Testo clinico in linguaggio libero');
    await waitFor(() => expectNoObjectObject(container));
  });
});
