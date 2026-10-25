import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchConsole from './ResearchConsole';
import { initialRunState } from './runReducer';
import { makeRun, makeStage } from './testFactories';
import { createRun, getDossier } from './api';
import liveResults from './__fixtures__/live-demo-results.json';
import type { PipelineStage } from './types';
import runtimeContract from './__fixtures__/runtime-contract.json';

const stream = vi.hoisted(() => ({ state: {} }));
vi.mock('./useRunStream', () => ({ useRunStream: () => stream }));
vi.mock('./api', () => ({
  createRun: vi.fn(), isRuntimeDisabled: () => false,
  listCases: async () => ({ cases: [] }), getConfig: async () => ({ runtime: { available: false } }),
  getDossier: vi.fn(), getEvents: async () => ({ events: [], hash_chain_valid: true }),
  getStage: async () => { throw new Error('No detailed stage in this fixture'); },
  getProvenance: async () => ({ items: [] }), getMetrics: async () => null,
}));

const dossier = { ...runtimeContract.empty_report, run_status: 'STOPPED' as const, case_summary: { disease: 'Test case' }, limitations: ['INSUFFICIENT_CASE_CONTEXT'] };
function renderRun(view = 'oncologist') {
  return render(<MemoryRouter initialEntries={[`/runs/r1?view=${view}`]}><Routes>
    <Route path="/runs/:runId" element={<ResearchConsole />} />
  </Routes></MemoryRouter>);
}
describe('console del runtime corrente', () => {
  it('mostra il progresso reale del Reader anche nella vista oncologo', async () => {
    stream.state = { ...initialRunState, run: makeRun({ status: 'RUNNING', stages: [] }), events: [{
      event_id: 'progress', sequence: 10, event_type: 'PIPELINE_WORK_PROGRESS',
      payload: { phase: 'READER', completed_candidates: 4, total_candidates: 30,
        reader_calls: 8, reader_reuses: 2, candidate_id: 'candidate', document_id: 'nct:NCT12345678' },
    }] };
    await act(async () => { renderRun(); });
    expect(screen.getByRole('progressbar', { name: 'Associazioni elaborate' })).toBeInTheDocument();
    expect(screen.getByText('4/30 associazioni elaborate')).toBeInTheDocument();
    expect(screen.getByText('Lettura del documento')).toBeInTheDocument();
    expect(screen.queryByText('nct:NCT12345678')).not.toBeInTheDocument();
  });
  // These integration checks exercise navigation, not cold chunk download time.
  beforeAll(async () => {
    await Promise.all([import('./StageDetail'), import('./RunSpine'), import('./RunModeHeader'),
      import('./CanonicalProvenance'), import('./ProvenanceTree'), import('./SupervisorPanel')]);
  });
  it('separa la vista oncologo dal debug mantenendo il dossier', async () => {
    renderRun();
    expect(await screen.findByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Stage della pipeline' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Relazioni' }));
    expect(screen.getByRole('navigation', { name: 'Sezioni del dossier' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Sintesi' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Debug' }));
    fireEvent.click(await screen.findByRole('tab', { name: 'Stage' }));
    expect(await screen.findByRole('list', { name: 'Stage della pipeline' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Oncologo' }));
    expect(screen.queryByRole('list', { name: 'Stage della pipeline' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
  });
  beforeEach(() => {
    vi.mocked(getDossier).mockClear();
    vi.mocked(getDossier).mockResolvedValue({ run_id: 'r1', status: 'COMPLETED', dossier, presentation_mode: 'STRUCTURED_DOSSIER_FALLBACK' });
    stream.state = { ...initialRunState, run: makeRun({ stages: [makeStage({ stage_id: 'stage_13_dossier' })] }) };
  });
  it('joins the separate reading guide into the local view without mutating canonical facts', async () => {
    vi.mocked(getDossier).mockResolvedValue({ run_id: 'r1', status: 'COMPLETED', dossier,
      presentation_mode: 'STRUCTURED_DOSSIER_FALLBACK', reading_guide: {
        version: 'dossier-reading/1.0', clinical_applicability: 'NOT_EVALUATED',
        verification_note: 'Backend reading guide: fidelity is not clinical validation.',
        findings: [], trial_groups: [], trial_association_count: 0,
        identified_study_count: 0, unidentified_trial_association_count: 0,
      } });
    renderRun();
    await screen.findByRole('heading', { name: 'Dossier canonico' });
    fireEvent.click(screen.getByRole('tab', { name: 'Relazioni' }));
    expect(screen.getByText('Backend reading guide: fidelity is not clinical validation.')).toBeVisible();
    expect('reading_guide' in dossier).toBe(false);
  });
  it('opens the source destination and moves keyboard focus there', async () => {
    renderRun();
    await screen.findByRole('heading', { name: 'Dossier canonico' });
    fireEvent.click(screen.getByRole('link', { name: 'Pubblicazioni 0' }));
    expect(screen.getByRole('tab', { name: 'Relazioni' })).toHaveAttribute('aria-selected', 'true');
    expect(document.getElementById('dossier-paper')).toHaveFocus();
  });
  it('keeps a historical report distinct from a canonical empty dossier', async () => {
    vi.mocked(getDossier).mockResolvedValue({ run_id: 'r1', status: 'COMPLETED', dossier: {}, presentation_mode: 'STRUCTURED_DOSSIER_FALLBACK' });
    renderRun();
    expect(await screen.findByText(/Questo dossier usa un contratto storico/)).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Relazioni' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Dossier canonico' })).not.toBeInTheDocument();
  });
  it.each(liveResults)('rappresenta la run live fallita di $case_id senza dossier presunto', async result => {
    stream.state = { ...initialRunState, run: makeRun({ status: 'FAILED', stopped_at: 'PARSER_TRANSPORT_FAILED',
      stages: [result.parser_stage as PipelineStage], relation_aware_report: null }) };
    renderRun();
    expect(await screen.findByText(/Nessun dossier: la run è FAILED/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Debug' }));
    fireEvent.click(await screen.findByRole('tab', { name: 'Stage' }));
    fireEvent.click(await screen.findByRole('tab', { name: 'Output' }, { timeout: 10000 }));
    expect(screen.getByText('TARGET_INTERVENTION_KEYS_INVALID')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Dossier canonico' })).not.toBeInTheDocument();
    expect(getDossier).not.toHaveBeenCalled();
  });
  it.each([null, 'CALL_BUDGET_EXCEEDED'] as const)('spiega il budget esaurito anche nelle run storiche (%s)', async stopped_at => {
    stream.state = { ...initialRunState, run: makeRun({ status: 'FAILED', stopped_at,
      stages: [], relation_aware_report: null,
      errors: ['RuntimeError: CALL_BUDGET_EXCEEDED: used=20/20'] }) };
    renderRun();
    expect(await screen.findByText(/è stato raggiunto il limite di chiamate al modello/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Dossier canonico' })).not.toBeInTheDocument();
    expect(getDossier).not.toHaveBeenCalled();
  });
  it('conserva il dossier corrente se il nuovo caso non viene avviato', async () => {
    vi.mocked(createRun).mockRejectedValueOnce(new Error('Avvio rifiutato'));
    renderRun();
    await screen.findByRole('heading', { name: 'Dossier canonico' });
    fireEvent.click(screen.getByText('Avvia un nuovo caso'));
    fireEvent.change(await screen.findByLabelText('Testo clinico in linguaggio libero'), { target: { value: 'Synthetic case with colorectal cancer and KRAS G12D evaluating panitumumab.' } });
    fireEvent.click(screen.getByTestId('run-pipeline'));
    await screen.findByText(/Avvio rifiutato/);
    expect(screen.getByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
    expect(screen.queryByText(/Caricamento del dossier/)).not.toBeInTheDocument();
  });
  it('indica il caricamento invece di dichiarare assente un dossier non ancora letto', () => {
    vi.mocked(getDossier).mockReturnValue(new Promise(() => {}));
    renderRun();
    expect(screen.getByText('Caricamento del dossier canonico…')).toBeInTheDocument();
    expect(screen.queryByText('Nessun dossier per questa run.')).not.toBeInTheDocument();
  });
  it('in Debug separa architettura, stage e audit', async () => {
    renderRun('debug');
    await screen.findByRole('tab', { name: 'Architettura' });
    expect(screen.queryByRole('list', { name: 'Stage della pipeline' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Stage' }));
    await screen.findByRole('list', { name: 'Stage della pipeline' });
    fireEvent.click(screen.getByRole('tab', { name: 'Audit' }));
    await screen.findByRole('heading', { name: 'Dossier canonico' });
    expect(within(screen.getByRole('tablist', { name: 'Audit della run' })).getAllByRole('tab')).toHaveLength(2);
    expect(within(screen.getByRole('tablist', { name: 'Audit della run' })).getByRole('tab', { name: 'Provenienza' })).toHaveAttribute('aria-controls', 'audit-panel-0');
    fireEvent.click(screen.getByRole('tab', { name: 'Metriche e integrità' }));
    expect(await screen.findByRole('tabpanel', { name: 'Metriche e integrità' })).toHaveAttribute('aria-labelledby', 'audit-tab-1');
  });
  it('monta la trace interna solo mentre la sezione è aperta', async () => {
    renderRun('debug');
    fireEvent.click(await screen.findByRole('tab', { name: 'Audit' }));
    await screen.findByRole('heading', { name: 'Dossier canonico' });
    const trace = screen.getByText('Trace degli stage e classificazioni interne').closest('details')!;
    const emptyTrace = /Nessuna catena di provenienza prodotta da questa run/;
    expect(within(trace).queryByText(emptyTrace)).not.toBeInTheDocument();
    trace.open = true;
    fireEvent(trace, new Event('toggle'));
    expect(await within(trace).findByText(emptyTrace)).toBeInTheDocument();
    trace.open = false;
    fireEvent(trace, new Event('toggle'));
    expect(within(trace).queryByText(emptyTrace)).not.toBeInTheDocument();
  });
  it('recupera il dossier vuoto fornito dal backend per uno stop controllato', async () => {
    stream.state = { ...initialRunState, run: makeRun({ status: 'STOPPED', stopped_at: 'OUT_OF_SCOPE',
      stages: [makeStage({ stage_id: 'stage_13_dossier', status: 'SKIPPED' })], relation_aware_report: dossier }) };
    renderRun();
    expect(await screen.findByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
    expect(getDossier).toHaveBeenCalledWith('r1');
  });
});
