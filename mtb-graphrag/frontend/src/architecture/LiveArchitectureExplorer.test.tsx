import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LiveArchitectureExplorer from './LiveArchitectureExplorer';
import { createRun, getStage } from '../research/api';
import { initialRunState } from '../research/runReducer';
import { makeRun, makeStage } from '../research/testFactories';

const stream = vi.hoisted(() => ({ state: {} }));
vi.mock('../research/useRunStream', () => ({ useRunStream: () => ({ state: stream.state, refresh: vi.fn() }) }));
vi.mock('../research/api', () => ({
  listCases: vi.fn(async () => ({ cases: [] })),
  getConfig: vi.fn(async () => ({})),
  createRun: vi.fn(), getStage: vi.fn(),
}));

function open(path = '/architecture') { return render(<MemoryRouter initialEntries={[path]}><LiveArchitectureExplorer /></MemoryRouter>); }

describe('Explorer collegato al runtime', () => {
  beforeEach(() => { vi.clearAllMocks(); stream.state = initialRunState; });
  it('starts exactly one real request only after explicit submission', async () => {
    vi.mocked(createRun).mockResolvedValue({ run_id: 'new-run', case_id: 'case', status: 'RUNNING', execution_mode: 'LIVE', stream_url: '', research_notice: makeRun().research_notice });
    open();
    expect(createRun).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), { target: { value: 'Public EGFR L858R case' } });
    fireEvent.click(screen.getByTestId('run-pipeline'));
    await waitFor(() => expect(createRun).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createRun).mock.calls[0][0].clinical_text).toBe('Public EGFR L858R case');
    expect(await screen.findByText('new-run')).toBeInTheDocument();
  });
  it('opens an existing run without rerunning and shows recorded input and output', async () => {
    const stage = makeStage({ input_preview: { actual_input: 'recorded case text' }, output_preview: { actual_output: 'recorded result' } });
    stream.state = { ...initialRunState, run: makeRun({ stages: [stage] }) };
    vi.mocked(getStage).mockResolvedValue({ stage, events: [] });
    open('/architecture?run=r1');
    await waitFor(() => expect(getStage).toHaveBeenCalledWith('r1', stage.stage_id));
    expect(await screen.findByText(/recorded case text/)).toBeInTheDocument();
    expect(screen.getByText(/recorded result/)).toBeInTheDocument();
    expect(createRun).not.toHaveBeenCalled();
  });
  it('never substitutes demo output when a stage cannot be loaded', async () => {
    const stage = makeStage();
    stream.state = { ...initialRunState, run: makeRun({ stages: [stage] }) };
    vi.mocked(getStage).mockRejectedValue(new Error('stage unavailable'));
    open('/architecture?run=r1');
    expect(await screen.findByRole('alert')).toHaveTextContent('stage unavailable');
    expect(screen.queryByText('Input registrato')).not.toBeInTheDocument();
  });
  it('retries a failed stage detail on refresh even when the run is unchanged', async () => {
    const stage = makeStage({ output_preview: { recovered: 'backend recovered' } });
    stream.state = { ...initialRunState, run: makeRun({ stages: [stage] }) };
    vi.mocked(getStage).mockRejectedValueOnce(new Error('temporary error')).mockResolvedValue({ stage, events: [] });
    open('/architecture?run=r1');
    expect(await screen.findByRole('alert')).toHaveTextContent('temporary error');
    fireEvent.click(screen.getByRole('button', { name: 'Aggiorna' }));
    expect(await screen.findByText(/backend recovered/)).toBeInTheDocument();
    expect(getStage).toHaveBeenCalledTimes(2);
  });
});
