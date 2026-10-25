import { expect, it, vi } from 'vitest';
import { getEvents, getRun, streamUrl } from './api';
import { makeRun } from './testFactories';

it('richiede payload compatti sia su REST sia sullo stream SSE', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => makeRun() })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ run_id: 'r1', append_only: true, hash_chain_valid: true, events: [], next_after_sequence: 42, has_more: false }) });
  vi.stubGlobal('fetch', fetch);
  try {
    await getRun('r1');
    expect(fetch.mock.calls[0][0]).toContain('/runs/r1?compact=true');
    await getEvents('r1', 42);
    expect(fetch.mock.calls[1][0]).toContain('after_sequence=42&limit=500&compact=true');
    expect(streamUrl('r1')).toContain('/stream?compact=true');
  } finally {
    vi.unstubAllGlobals();
  }
});
