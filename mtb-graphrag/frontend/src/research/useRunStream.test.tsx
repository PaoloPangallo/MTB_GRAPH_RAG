import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useRunStream } from './useRunStream';
import { getEvents, getRun } from './api';
import { DETERMINISTIC_PRODUCER, makeRun, makeStage } from './testFactories';
import type { PipelineRun } from './types';

vi.mock('./api', () => ({ getRun: vi.fn(), getEvents: vi.fn(), streamUrl: (id: string) => `/stream/${id}` }));
class Source {
  static instances: Source[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn();
  constructor() { Source.instances.push(this); }
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
describe('ownership della sottoscrizione alla run', () => {
  beforeEach(() => {
    vi.resetAllMocks(); Source.instances = [];
    vi.stubGlobal('EventSource', Source);
    vi.mocked(getEvents).mockImplementation(async id => ({ run_id: id, events: [], append_only: true,
      hash_chain_valid: true, next_after_sequence: 0, has_more: false }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
  it('surfaces an invalid SSE contract frame and refreshes REST on a healthy socket', async () => {
    const recovered = deferred<PipelineRun>();
    vi.mocked(getRun).mockResolvedValueOnce(makeRun({ run_id: 'A', status: 'RUNNING' }))
      .mockReturnValueOnce(recovered.promise);
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    act(() => Source.instances[0].onopen?.());
    act(() => Source.instances[0].onmessage?.(new MessageEvent('message', { data: JSON.stringify({
      event_id: 'invalid-stage', sequence: 0, event_type: 'STAGE_COMPLETED', created_at: 'now', actor: 'runtime',
      payload: { stage_id: 'stage_1_case_input' },
    }) })));
    expect(result.current.state.error).toContain('sequence');
    expect(result.current.state.events).toEqual([]);
    expect(Source.instances[0].close).not.toHaveBeenCalled();
    await waitFor(() => expect(getRun).toHaveBeenCalledTimes(2));
    await act(async () => recovered.resolve(makeRun({ run_id: 'A', status: 'RUNNING', stages: [makeStage()] })));
    expect(result.current.state.run?.stages[0].status).toBe('SUCCEEDED');
  });
  it('keeps the existing discard policy for corrupted JSON frames', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.useFakeTimers();
    act(() => Source.instances[0].onmessage?.(new MessageEvent('message', { data: '{broken json' })));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(getRun).toHaveBeenCalledTimes(1);
    expect(result.current.state.error).toBeNull();
  });
  it('pagina lo storico e richiede solo gli eventi successivi al cursore REST', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    vi.mocked(getEvents).mockImplementation(async (id, after = 0) => ({ run_id: id, events: [], append_only: true,
      hash_chain_valid: true, next_after_sequence: after === 0 ? 10 : 20, has_more: after === 0 }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(getEvents).toHaveBeenCalledWith('A', 10));
    await act(async () => { await result.current.refresh(); });
    expect(getEvents).toHaveBeenLastCalledWith('A', 20);
  });
  it('riesegue lo snapshot se un refresh arriva durante una pagina lenta', async () => {
    const page = deferred<Awaited<ReturnType<typeof getEvents>>>();
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    vi.mocked(getEvents).mockReturnValueOnce(page.promise).mockResolvedValue({ run_id: 'A', events: [], append_only: true, hash_chain_valid: true, next_after_sequence: 1, has_more: false });
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(getEvents).toHaveBeenCalledTimes(1));
    await act(async () => { await result.current.refresh(); });
    await act(async () => { page.resolve({ run_id: 'A', events: [], append_only: true, hash_chain_valid: true, next_after_sequence: 1, has_more: false }); });
    await waitFor(() => expect(getRun).toHaveBeenCalledTimes(2));
    expect(getEvents).toHaveBeenLastCalledWith('A', 1);
  });
  it('ignora uno snapshot lento di A dopo la navigazione a B', async () => {
    const old = deferred<PipelineRun>();
    vi.mocked(getRun).mockImplementation(id => id === 'A' ? old.promise : Promise.resolve(makeRun({ run_id: 'B', status: 'RUNNING' })));
    const { result, rerender } = renderHook(({ id }) => useRunStream(id), { initialProps: { id: 'A' } });
    rerender({ id: 'B' });
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('B'));
    await act(async () => { old.resolve(makeRun({ run_id: 'A' })); });
    expect(result.current.state.run?.run_id).toBe('B');
    expect(Source.instances[1].close).not.toHaveBeenCalled();
  });
  it('recovers automatically after both SSE and REST fail and refreshes missed history on open', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.useFakeTimers();
    vi.mocked(getRun).mockRejectedValueOnce(new Error('offline'));
    await act(async () => Source.instances[0].onerror?.());
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(Source.instances).toHaveLength(2);
    const priorPages = vi.mocked(getEvents).mock.calls.length;
    await act(async () => Source.instances[1].onopen?.());
    expect(vi.mocked(getEvents).mock.calls.length).toBeGreaterThan(priorPages);
    expect(result.current.state.error).toBeNull();
  });
  it('retries repeated outages with backoff and cancels its timer on unmount', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result, unmount } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.useFakeTimers();
    vi.mocked(getRun).mockRejectedValue(new Error('offline'));
    await act(async () => Source.instances[0].onerror?.());
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(Source.instances).toHaveLength(2);
    await act(async () => Source.instances[1].onerror?.());
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(Source.instances).toHaveLength(2);
    unmount();
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(Source.instances).toHaveLength(2);
  });
  it('cancels a pending reconnect when a terminal REST refresh arrives', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.useFakeTimers();
    await act(async () => Source.instances[0].onerror?.());
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'COMPLETED' }));
    await act(async () => result.current.refresh());
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(Source.instances).toHaveLength(1);
  });
  it('does not schedule recovery from a stale failed probe after a terminal refresh', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.useFakeTimers();
    let rejectProbe!: (error: Error) => void;
    vi.mocked(getRun).mockReturnValueOnce(new Promise((_, reject) => { rejectProbe = reject; }));
    act(() => Source.instances[0].onerror?.());
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'COMPLETED' }));
    await act(async () => result.current.refresh());
    await act(async () => rejectProbe(new Error('late failure')));
    await act(async () => vi.advanceTimersByTimeAsync(30000));
    expect(Source.instances).toHaveLength(1);
    expect(result.current.state.connection).toBe('closed');
  });
  it('recovers final REST events when the disconnect probe finds the run already completed', async () => {
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'RUNNING' }));
    const { result } = renderHook(() => useRunStream('A'));
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    vi.mocked(getRun).mockResolvedValue(makeRun({ run_id: 'A', status: 'COMPLETED' }));
    vi.mocked(getEvents).mockResolvedValue({ run_id: 'A', events: [{
      event_id: 'final', sequence: 2, event_type: 'RUN_COMPLETED', created_at: 'now', actor: 'runtime', payload: {},
      stage_id: null, stage_type: null, producer: DETERMINISTIC_PRODUCER, payload_hash: 'final-hash',
    }], append_only: true, hash_chain_valid: true, next_after_sequence: 2, has_more: false });
    await act(async () => Source.instances[0].onerror?.());
    expect(result.current.state.events.some(event => event.event_id === 'final')).toBe(true);
    expect(result.current.state.connection).toBe('closed');
  });
  it('ignora una risposta di riconnessione della precedente run', async () => {
    const old = deferred<PipelineRun>();
    vi.mocked(getRun).mockResolvedValueOnce(makeRun({ run_id: 'A', status: 'RUNNING' }))
      .mockReturnValueOnce(old.promise).mockResolvedValue(makeRun({ run_id: 'B', status: 'RUNNING' }));
    const { result, rerender } = renderHook(({ id }) => useRunStream(id), { initialProps: { id: 'A' } });
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('A'));
    act(() => Source.instances[0].onerror?.());
    rerender({ id: 'B' });
    await waitFor(() => expect(result.current.state.run?.run_id).toBe('B'));
    await act(async () => { old.resolve(makeRun({ run_id: 'A' })); });
    expect(result.current.state.run?.run_id).toBe('B');
  });
});
