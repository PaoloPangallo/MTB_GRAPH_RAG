import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import RunSpine from './RunSpine';
import type { PipelineStage } from './types';

function stage(overrides: Partial<PipelineStage> & { stage_id: string; sequence: number }): PipelineStage {
  return {
    stage_type: 'X',
    status: 'SUCCEEDED',
    started_at: null,
    completed_at: null,
    duration_ms: 120,
    input_preview: {},
    output_preview: {},
    reason_codes: [],
    warnings: [],
    errors: [],
    producer: { kind: 'DETERMINISTIC', component: 'c', version: '1', model: null, prompt_version: null },
    metrics: {},
    lineage: {},
    ...overrides,
  } as PipelineStage;
}

const STAGES: PipelineStage[] = [
  stage({ stage_id: 'stage_1_case_input', sequence: 1 }),
  stage({
    stage_id: 'stage_2_casecontext_parser', sequence: 2,
    producer: { kind: 'LLM', component: 'parser', version: '1.0', model: 'gemma4:cloud', prompt_version: 'p/1.0' },
  }),
  stage({
    stage_id: 'stage_6_document_resolution', sequence: 6,
    output_preview: { replayed: true },
  }),
  stage({
    stage_id: 'stage_14_narrator', sequence: 14,
    status: 'SKIPPED', reason_codes: ['NOT_IMPLEMENTED'], duration_ms: null,
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

    // Un solo badge LLM: il parser. Gate e status non devono averlo mai.
    expect(screen.getAllByText('LLM')).toHaveLength(1);
  });

  it('marca gli stage rigiocati come replay', () => {
    render(<RunSpine stages={STAGES} selectedStageId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('REPLAY')).toBeInTheDocument();
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
