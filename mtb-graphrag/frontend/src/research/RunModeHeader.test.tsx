/**
 * L'intestazione di modalità è ciò che impedisce la lettura peggiore: che una
 * run che ha rigiocato artefatti registrati venga presa per una run eseguita.
 *
 * Questi test controllano soprattutto che l'intestazione **non** possa dire di
 * più di quanto il backend afferma.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RunModeHeader from './RunModeHeader';
import { makeRun } from './testFactories';
import { expectNoObjectObject } from './values/testing';

describe('RunModeHeader', () => {
  it('dichiara modalità, cache, chiamate e artefatti rigiocati', () => {
    render(<RunModeHeader run={makeRun()} />);

    expect(screen.getByTestId('execution-mode')).toHaveTextContent('LIVE');
    expect(screen.getByTestId('document-cache')).toHaveTextContent('AVAILABLE');
    expect(screen.getByTestId('llm-calls')).toHaveTextContent('2');
    expect(screen.getByTestId('replay-artifacts-used')).toHaveTextContent('0');
  });

  it('mostra zero artefatti rigiocati invece di nascondere il campo', () => {
    // Un campo che compare solo quando è diverso da zero non distingue
    // "nessun artefatto" da "non misurato".
    render(<RunModeHeader run={makeRun({ replay_artifacts_used: 0 })} />);
    expect(screen.getByTestId('replay-artifacts-used')).toBeInTheDocument();
  });

  it('etichetta FULLY LIVE solo una run senza artefatti registrati', () => {
    render(<RunModeHeader run={makeRun()} />);
    expect(screen.getByTestId('fully-live-badge')).toBeInTheDocument();
  });

  it('non etichetta FULLY LIVE una run con artefatti registrati', () => {
    render(<RunModeHeader run={makeRun({
      execution_mode: 'HYBRID', fully_live: false, replay_artifacts_used: 2,
    })} />);

    expect(screen.queryByTestId('fully-live-badge')).not.toBeInTheDocument();
    expect(screen.getByTestId('execution-mode')).toHaveTextContent('HYBRID');
    expect(screen.getByText(/non è completamente live/)).toBeInTheDocument();
  });

  it('dichiara quando la modalità effettiva differisce da quella richiesta', () => {
    render(<RunModeHeader run={makeRun({
      requested_mode: 'LIVE', execution_mode: 'HYBRID', fully_live: false,
      replay_artifacts_used: 1,
    })} />);

    expect(screen.getByText(/richiesta LIVE/)).toBeInTheDocument();
  });

  it('una run replay non viene mai mostrata come live', () => {
    render(<RunModeHeader run={makeRun({
      requested_mode: 'REPLAY', execution_mode: 'REPLAY', fully_live: false,
      replay_artifacts_used: 6, llm_calls: 0,
    })} />);

    expect(screen.getByTestId('execution-mode')).toHaveTextContent('REPLAY');
    expect(screen.queryByTestId('fully-live-badge')).not.toBeInTheDocument();
    expect(screen.getByTestId('llm-calls')).toHaveTextContent('0');
  });

  it('dichiara la cache assente invece di tacere', () => {
    render(<RunModeHeader run={makeRun({
      document_cache: { document_cache_available: false, reason_codes: ['CACHE_PATH_NOT_FOUND'] },
    })} />);

    expect(screen.getByTestId('document-cache')).toHaveTextContent('UNAVAILABLE');
  });

  it('mostra manifest e conteggi della cache senza il percorso locale', () => {
    render(<RunModeHeader run={makeRun()} />);

    expect(screen.getByText(/manifest: ece9d25d74b3/)).toBeInTheDocument();
    expect(screen.getByText(/documenti: 40/)).toBeInTheDocument();
    expect(screen.getByText(/\.\.\.\/data_cache\/document_grounding/)).toBeInTheDocument();
    expect(screen.queryByText(/C:\\/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Users/)).not.toBeInTheDocument();
  });

  it('segnala una run ricostruita dal registro', () => {
    render(<RunModeHeader run={makeRun({
      rehydrated: true, hash_chain_valid: true, recovery_status: 'COMPLETE',
    })} />);

    expect(screen.getByText(/ricostruita dal registro/)).toBeInTheDocument();
    expect(screen.getByText(/catena di hash verificata/)).toBeInTheDocument();
  });

  it('segnala una run interrotta come tale, non come fallita', () => {
    render(<RunModeHeader run={makeRun({
      rehydrated: true, recovery_status: 'RECOVERED_INCOMPLETE',
    })} />);

    expect(screen.getByText(/interrotta prima della conclusione/)).toBeInTheDocument();
  });

  it('non rende mai un oggetto come [object Object]', () => {
    const { container } = render(<RunModeHeader run={makeRun()} />);
    expectNoObjectObject(container);
  });

  it('senza run non mostra nulla', () => {
    const { container } = render(<RunModeHeader run={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
