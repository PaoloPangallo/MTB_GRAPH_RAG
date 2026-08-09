/**
 * L'intestazione operativa risponde alle domande che restano aperte a run
 * conclusa: da dove sono arrivati i documenti, se qualcuno è degradato, quante
 * volte è stato chiamato il modello, se la pipeline si è arrestata.
 *
 * Non risponde più a «in quale modalità è stata eseguita», perché la domanda non
 * esiste. Questi test fissano soprattutto due cose: che una run canonica non
 * mostri alcun concetto di modalità, e che una run storica archiviata resti
 * comunque distinguibile — nasconderla la farebbe passare per canonica.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RunModeHeader from './RunModeHeader';
import { makeRun } from './testFactories';
import { expectNoObjectObject } from './values/testing';

describe('RunModeHeader', () => {
  it('dichiara acquisizione documentale, cache e chiamate al modello', () => {
    render(<RunModeHeader run={makeRun()} />);

    expect(screen.getByTestId('document-acquisition')).toHaveTextContent('2 da cache');
    expect(screen.getByTestId('document-cache')).toHaveTextContent('AVAILABLE');
    expect(screen.getByTestId('llm-calls')).toHaveTextContent('2');
  });

  it('su una run canonica non mostra alcun concetto di modalità', () => {
    render(<RunModeHeader run={makeRun()} />);

    expect(screen.queryByTestId('historical-run-metadata')).not.toBeInTheDocument();
    expect(screen.queryByTestId('execution-mode')).not.toBeInTheDocument();
    expect(screen.queryByTestId('fully-live-badge')).not.toBeInTheDocument();
    expect(screen.queryByText(/REPLAY/)).not.toBeInTheDocument();
  });

  it('distingue le acquisizioni via API dai cache hit', () => {
    render(<RunModeHeader run={makeRun({
      document_acquisition: {
        executed: true, cache_hits: 1, cache_misses: 2, network_fetches: 2,
        degraded_to_abstract: 0, documents_unavailable: 0,
        sources: ['NCBI E-utilities', 'PMC OAI'], reason_codes: [],
      },
    })} />);

    expect(screen.getByTestId('document-acquisition')).toHaveTextContent('1 da cache · 2 da API');
    expect(screen.getByTestId('document-sources')).toHaveTextContent('NCBI E-utilities · PMC OAI');
  });

  it('dichiara la degradazione ad abstract invece di tacerla', () => {
    render(<RunModeHeader run={makeRun({
      document_acquisition: {
        executed: true, cache_hits: 0, cache_misses: 1, network_fetches: 1,
        degraded_to_abstract: 1, documents_unavailable: 0,
        sources: ['NCBI E-utilities'], reason_codes: [],
      },
    })} />);

    expect(screen.getByTestId('degraded-to-abstract')).toHaveTextContent('1');
  });

  it('distingue «non misurato» da «nessun documento»', () => {
    // La catena documentale non è stata raggiunta: uno zero direbbe un'altra cosa.
    render(<RunModeHeader run={makeRun({
      document_acquisition: {
        executed: false, cache_hits: null, cache_misses: null, network_fetches: null,
        degraded_to_abstract: null, documents_unavailable: null,
        sources: [], reason_codes: ['RETRIEVAL_NO_MATCH'],
      },
    })} />);

    expect(screen.getByTestId('document-acquisition')).toHaveTextContent('non raggiunta');
  });

  it('segnala l’arresto della pipeline', () => {
    render(<RunModeHeader run={makeRun({
      status: 'FAILED', stopped_at: 'NO_DOCUMENT_RESOLVED',
    })} />);

    expect(screen.getByTestId('pipeline-abort')).toHaveTextContent('PIPELINE ABORT');
  });

  it('mostra i metadati storici solo su una run archiviata', () => {
    render(<RunModeHeader run={makeRun({
      requested_mode: 'REPLAY', execution_mode: 'REPLAY', fully_live: false,
      replay_artifacts_used: 6, llm_calls: 0,
    })} />);

    expect(screen.getByTestId('historical-run-metadata')).toBeInTheDocument();
    expect(screen.getByTestId('historical-execution-mode')).toHaveTextContent('REPLAY');
    expect(screen.getByTestId('replay-artifacts-used')).toHaveTextContent('6');
    expect(screen.getByText(/Non è una\s+modalità selezionabile/)).toBeInTheDocument();
    expect(screen.getByTestId('llm-calls')).toHaveTextContent('0');
  });

  it('mostra i metadati storici anche su una run HYBRID', () => {
    render(<RunModeHeader run={makeRun({
      execution_mode: 'HYBRID', fully_live: false, replay_artifacts_used: 2,
    })} />);

    expect(screen.getByTestId('historical-execution-mode')).toHaveTextContent('HYBRID');
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
