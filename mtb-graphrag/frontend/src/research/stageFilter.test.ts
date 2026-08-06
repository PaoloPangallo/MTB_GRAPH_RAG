/**
 * Il filtro degli stage.
 *
 * Il punto delicato è "Solo LIVE": deve includere gli stage documentali, che
 * hanno origine `DETERMINISTIC_CACHE`. Escluderli darebbe l'impressione che la
 * catena documentale non sia stata percorsa proprio nelle run in cui lo è stata.
 */

import { describe, expect, it } from 'vitest';
import { matchesFilter } from './RunSpine';
import { LLM_PRODUCER, makeStage } from './testFactories';

const LIVE_STAGE = makeStage({ stage_id: 'stage_1_case_input' });
const CACHED_STAGE = makeStage({
  stage_id: 'stage_6_document_resolution', artifact_origin: 'DETERMINISTIC_CACHE',
});
const REPLAY_STAGE = makeStage({
  stage_id: 'stage_9_paper_context_enricher', execution_mode: 'REPLAY',
  artifact_origin: 'RECORDED_REAL_RUN', producer: LLM_PRODUCER,
});
const FAILED_STAGE = makeStage({
  stage_id: 'stage_6_document_resolution', status: 'FAILED',
  artifact_origin: 'NOT_EXECUTED', errors: ['boom'],
});
const LLM_STAGE = makeStage({ stage_id: 'stage_2_casecontext_parser', producer: LLM_PRODUCER });

describe('filtro degli stage', () => {
  it('“tutti” non esclude nulla', () => {
    for (const stage of [LIVE_STAGE, CACHED_STAGE, REPLAY_STAGE, FAILED_STAGE]) {
      expect(matchesFilter(stage, 'all')).toBe(true);
    }
  });

  it('“solo LIVE” include gli stage documentali letti dalla cache', () => {
    expect(matchesFilter(LIVE_STAGE, 'live')).toBe(true);
    expect(matchesFilter(CACHED_STAGE, 'live')).toBe(true);
  });

  it('“solo LIVE” esclude gli artefatti registrati', () => {
    expect(matchesFilter(REPLAY_STAGE, 'live')).toBe(false);
  });

  it('“solo REPLAY” include solo gli artefatti registrati', () => {
    expect(matchesFilter(REPLAY_STAGE, 'replay')).toBe(true);
    expect(matchesFilter(CACHED_STAGE, 'replay')).toBe(false);
    expect(matchesFilter(LIVE_STAGE, 'replay')).toBe(false);
  });

  it('“warning ed errori” raccoglie fallimenti e riserve', () => {
    expect(matchesFilter(FAILED_STAGE, 'problems')).toBe(true);
    expect(matchesFilter(LIVE_STAGE, 'problems')).toBe(false);
    expect(matchesFilter(
      makeStage({ status: 'WARNING' }), 'problems')).toBe(true);
    expect(matchesFilter(
      makeStage({ warnings: ['DOCUMENT_UNAVAILABLE'] }), 'problems')).toBe(true);
  });

  it('“LLM” e “deterministici” si escludono a vicenda', () => {
    expect(matchesFilter(LLM_STAGE, 'llm')).toBe(true);
    expect(matchesFilter(LLM_STAGE, 'deterministic')).toBe(false);
    expect(matchesFilter(LIVE_STAGE, 'deterministic')).toBe(true);
    expect(matchesFilter(LIVE_STAGE, 'llm')).toBe(false);
  });
});
