import { afterEach, expect, it, vi } from 'vitest';
import fixture from './__fixtures__/runtime-contract.json';
import { parseCanonicalDossier, parsePublicEvent } from './contracts.generated';
import { getDossier, getRun, getStage } from './api';
import { matchesFilter } from './stageFilters';
import { makeRun, makeStage } from './testFactories';

afterEach(() => vi.unstubAllGlobals());

it('accepts the actual Python dossier without dropping extension provenance', () => {
  const payload = { ...fixture.unresolved_report, snapshot: { hash: 'source' } };
  expect(parseCanonicalDossier(payload)).toBe(payload);
});

it('rejects wrong authoritative support levels and relation branches', () => {
  for (const change of [{ support_level: 'DIRECT' }, { relation_family: 'KG_ONLY' }]) {
    const payload = structuredClone(fixture.unresolved_report);
    Object.assign(payload.paper_evidence[0], change);
    expect(() => parseCanonicalDossier(payload)).toThrow(/paper_evidence/);
  }
});

it('rejects a validated quote with missing source unit provenance', () => {
  const payload = structuredClone(fixture.unresolved_report);
  Object.assign(payload.paper_evidence[0], { quote: 'literal', quote_valid: true, document_id: 'pmid:123', quote_source_unit_id: null });
  expect(() => parseCanonicalDossier(payload)).toThrow(/source_unit/);
});

it('rejects a quote referring to an unselected source unit', () => {
  const payload = structuredClone(fixture.unresolved_report);
  Object.assign(payload.paper_evidence[0], { quote: 'literal', quote_valid: true, document_id: 'pmid:123', quote_source_unit_id: 'SU-WRONG', selected_source_unit_ids: ['SU-SELECTED'] });
  expect(() => parseCanonicalDossier(payload)).toThrow(/selected source/);
});

it('checks REST response states instead of casting an invalid authoritative status', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ run_id: 'r1', case_id: 'c1', stages: [], status: 'DIRECT' }) }));
  await expect(getRun('r1')).rejects.toThrow(/status/);
});

it('checks the nested dossier at its REST boundary', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ run_id: 'r1', status: 'COMPLETED', dossier: { ...fixture.empty_report, run_status: 'DIRECT' } }) }));
  await expect(getDossier('r1')).rejects.toThrow(/run_status/);
});

it('validates the ledger envelope while preserving unknown future event payload keys', () => {
  const event = { event_id: 'e1', sequence: 1, event_type: 'RUN_COMPLETED', created_at: 'now', actor: 'runtime', payload: { status: 'STOPPED', future_field: ['audit'] } };
  expect(parsePublicEvent(event)).toBe(event);
  expect(() => parsePublicEvent({ ...event, sequence: -1 })).toThrow(/sequence/);
});

it.each([undefined, null])('normalizes legacy stage arrays from REST run and stage responses (%s)', async absent => {
  const stage: Record<string, unknown> = { ...makeStage(), reason_codes: absent, warnings: absent, errors: absent,
    audit_extension: { source_hash: 'hash' } };
  if (absent === undefined) {
    delete stage.reason_codes;
    delete stage.warnings;
    delete stage.errors;
  }
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ...makeRun(), stages: [stage] }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ stage, run_id: 'r1' }) });
  vi.stubGlobal('fetch', fetch);
  const run = await getRun('r1');
  const detailed = await getStage('r1', 'stage_1_case_input');
  for (const received of [run.stages[0], detailed.stage]) {
    expect(matchesFilter(received, 'problems')).toBe(false);
    expect(received.reason_codes).toEqual([]);
    expect(received.warnings).toEqual([]);
    expect(received.errors).toEqual([]);
    expect(received).toHaveProperty('audit_extension', { source_hash: 'hash' });
  }
});
