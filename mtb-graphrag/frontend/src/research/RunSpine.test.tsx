import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import RunSpine from './RunSpine';
import { makeStage } from './testFactories';
import type { PipelineStage } from './types';

function stage(overrides: Partial<PipelineStage> & { stage_id: string; sequence: number }): PipelineStage {
  return makeStage({ stage_type: 'X', duration_ms: 120, ...overrides });
}

const STAGES: PipelineStage[] = [
  stage({ stage_id: 'stage_1_case_input', sequence: 1 }),
  stage({
    stage_id: 'stage_2_casecontext_parser', sequence: 2,
    producer: { kind: 'LLM', component: 'parser', version: '1.0', model: 'gemma4:cloud', prompt_version: 'p/1.0' },
  }),
  // Documento letto dalla cache **durante** la run: è LIVE, non replay.
  stage({
    stage_id: 'stage_6_document_resolution', sequence: 6,
    artifact_origin: 'DETERMINISTIC_CACHE',
    metrics: { cache_hits: 1, cache_misses: 0 },
  }),
  // Artefatto registrato: questo, e solo questo, è REPLAY.
  stage({
    stage_id: 'stage_9_paper_context_enricher', sequence: 9,
    execution_mode: 'REPLAY', artifact_origin: 'RECORDED_REAL_RUN',
    producer: { kind: 'LLM', component: 'enricher', version: '2.0', model: 'gemma4:cloud', prompt_version: 'p/2.0' },
  }),
  stage({
    stage_id: 'stage_14_narrator', sequence: 14,
    status: 'SKIPPED', reason_codes: ['NOT_IMPLEMENTED'], duration_ms: null,
    artifact_origin: 'NOT_APPLICABLE',
  }),
];

describe('RunSpine', () => {
  it('mostra gli stage con la loro numerazione', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    expect(screen.getByText('01')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('CaseContext Parser')).toBeInTheDocument();
  });

  it('marca come LLM soltanto gli stage prodotti da un modello', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    // Solo parser ed enricher. Gate e status non devono averlo mai.
    expect(screen.getAllByText('LLM')).toHaveLength(2);
  });

  it('marca come REPLAY solo gli stage che rigiocano un artefatto registrato', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    const replay = screen.getAllByText('REPLAY');
    expect(replay).toHaveLength(1);
    expect(screen.getByTestId('stage-badge-stage_9_paper_context_enricher')).toHaveTextContent('REPLAY');
  });

  it('un documento dalla cache non è un replay', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    const badge = screen.getByTestId('stage-badge-stage_6_document_resolution');
    expect(badge).toHaveTextContent('CACHED DOCUMENT');
    expect(badge).not.toHaveTextContent('REPLAY');
  });

  it('marca come LIVE gli stage eseguiti ora', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByTestId('stage-badge-stage_1_case_input')).toHaveTextContent('LIVE');
  });

  it('mostra l’esito della cache per gli stage documentali', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/cache hit 1/)).toBeInTheDocument();
  });

  it('mostra modello, prompt e transport degli stage LLM', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    expect(screen.getAllByText('gemma4:cloud').length).toBeGreaterThan(0);
    expect(screen.getByText('prompt p/2.0')).toBeInTheDocument();
  });

  it('uno stage non implementato non è etichettato replay', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByTestId('stage-badge-stage_14_narrator')).toHaveTextContent('NOT IMPLEMENTED');
  });

  it('uno stage fallito lo dichiara prima della sua origine', () => {
    const failed = stage({
      stage_id: 'stage_6_document_resolution', sequence: 6, status: 'FAILED',
      artifact_origin: 'NOT_EXECUTED', reason_codes: ['DOCUMENT_CACHE_UNAVAILABLE'],
    });
    render(<RunSpine stages={[failed]} selectedStageId={null} onSelect={vi.fn()} />);

    expect(screen.getByTestId('stage-badge-stage_6_document_resolution')).toHaveTextContent('FAILED');
  });

  it('indica lo stato con un testo e non solo con il colore', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);

    expect(screen.getAllByText('Completato').length).toBeGreaterThan(0);
    expect(screen.getByText('Non eseguito')).toBeInTheDocument();
  });

  it('spiega perché uno stage non è stato eseguito', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Stage previsto dal contratto ma non implementato')).toBeInTheDocument();
  });

  it('mostra warning ed errori dello stage', () => {
    const warned = stage({
      stage_id: 'stage_6_document_resolution', sequence: 6, status: 'WARNING',
      artifact_origin: 'DETERMINISTIC_CACHE', warnings: ['DOCUMENT_UNAVAILABLE'],
    });
    render(<RunSpine stages={[warned]} selectedStageId={null} onSelect={vi.fn()} />);

    expect(screen.getByText(/Documento non presente nella cache/)).toBeInTheDocument();
  });

  it('mostra “non disponibile” invece di zero quando la durata manca', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('non disponibile')).toBeInTheDocument();
  });

  it('seleziona uno stage al click', () => {
    const onSelect = vi.fn();
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={onSelect} />);

    fireEvent.click(screen.getByText('CaseContext Parser'));
    expect(onSelect).toHaveBeenCalledWith('stage_2_casecontext_parser');
  });

  it('ogni stage è un controllo nativo, quindi raggiungibile da tastiera', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    const controls = screen.getAllByRole('button');

    expect(controls).toHaveLength(STAGES.length);
    controls.forEach((control) => expect(control.tagName).toBe('BUTTON'));
  });

  it('espone la lista come sequenza ordinata accessibile', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    const list = screen.getByRole('list', { name: 'Stage della pipeline' });

    expect(within(list).getAllByRole('listitem')).toHaveLength(STAGES.length);
  });

  it('segnala lo stage selezionato', () => {
    render(<RunSpine stages={STAGES} selectedStageId="stage_1_case_input" onSelect={vi.fn()} />);
    const selected = screen.getAllByRole('button').find((b) => b.getAttribute('aria-current') === 'true');

    expect(selected).toBeDefined();
  });

  it('mostra uno stato vuoto quando non c’è una run', () => {
    render(<RunSpine stages={[]} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/Nessuna run in corso/)).toBeInTheDocument();
  });
});
