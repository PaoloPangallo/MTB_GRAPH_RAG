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
import { LEGACY_V3_ROUTE, VERIFIABLE_PIPELINE_ROUTE } from './routes';
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

  it('la rotta legacy si dichiara come vista storica', async () => {
    renderAt(LEGACY_V3_ROUTE);
    expect(await screen.findByText(/Legacy V3 deterministic/i)).toBeInTheDocument();
    expect(screen.getByText(/qualified_claim_repository/i)).toBeInTheDocument();
  });

  it('la rotta legacy non è la pipeline verificabile', async () => {
    renderAt(LEGACY_V3_ROUTE);
    await screen.findByText(/Legacy V3 deterministic/i);
    expect(screen.queryByText(/Dal testo clinico al dossier/i)).not.toBeInTheDocument();
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
