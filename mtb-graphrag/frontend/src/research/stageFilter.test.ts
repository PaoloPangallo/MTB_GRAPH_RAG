/**
 * Il filtro degli stage.
 *
 * I tagli per modalità — "Solo LIVE", "Solo REPLAY" — sono spariti insieme alle
 * modalità stesse. Restano i tagli che descrivono cosa uno stage *è*: chi lo ha
 * prodotto e com'è andato. Il primo test fissa proprio l'assenza dei due tagli
 * rimossi, perché reintrodurli sarebbe il modo più silenzioso di rimettere in
 * vista una distinzione che il runtime non fa più.
 */

import { describe, expect, it } from 'vitest';
import { STAGE_FILTERS, matchesFilter } from './RunSpine';
import { LLM_PRODUCER, makeStage } from './testFactories';

const CANONICAL_STAGE = makeStage({ stage_id: 'stage_1_case_input' });
const CACHED_STAGE = makeStage({
  stage_id: 'stage_6_document_resolution', artifact_origin: 'DETERMINISTIC_CACHE',
});
const ARCHIVED_STAGE = makeStage({
  stage_id: 'stage_9_paper_context_enricher', execution_mode: 'REPLAY',
  artifact_origin: 'RECORDED_REAL_RUN', producer: LLM_PRODUCER,
});
const FAILED_STAGE = makeStage({
  stage_id: 'stage_6_document_resolution', status: 'FAILED',
  artifact_origin: 'NOT_EXECUTED', errors: ['boom'],
});
const LLM_STAGE = makeStage({ stage_id: 'stage_2_casecontext_parser', producer: LLM_PRODUCER });

describe('filtro degli stage', () => {
  it('non offre alcun filtro di modalità', () => {
    const keys = STAGE_FILTERS.map((filter) => filter.key);
    expect(keys).not.toContain('live');
    expect(keys).not.toContain('replay');
    expect(STAGE_FILTERS.map((filter) => filter.label).join(' ')).not.toMatch(/LIVE|REPLAY/);
  });

  it('“tutti” non esclude nulla', () => {
    for (const stage of [CANONICAL_STAGE, CACHED_STAGE, ARCHIVED_STAGE, FAILED_STAGE]) {
      expect(matchesFilter(stage, 'all')).toBe(true);
    }
  });

  it('“warning ed errori” raccoglie fallimenti e riserve', () => {
    expect(matchesFilter(FAILED_STAGE, 'problems')).toBe(true);
    expect(matchesFilter(CANONICAL_STAGE, 'problems')).toBe(false);
    expect(matchesFilter(
      makeStage({ status: 'WARNING' }), 'problems')).toBe(true);
    expect(matchesFilter(
      makeStage({ warnings: ['DOCUMENT_UNAVAILABLE'] }), 'problems')).toBe(true);
  });

  it('“LLM” e “deterministici” si escludono a vicenda', () => {
    expect(matchesFilter(LLM_STAGE, 'llm')).toBe(true);
    expect(matchesFilter(LLM_STAGE, 'deterministic')).toBe(false);
    expect(matchesFilter(CANONICAL_STAGE, 'deterministic')).toBe(true);
    expect(matchesFilter(CANONICAL_STAGE, 'llm')).toBe(false);
  });

  it('uno stage di una run archiviata resta filtrabile per produttore', () => {
    // I metadati storici non sono più un asse di filtro, ma lo stage resta uno
    // stage: chi lo ha prodotto continua a valere.
    expect(matchesFilter(ARCHIVED_STAGE, 'llm')).toBe(true);
    expect(matchesFilter(ARCHIVED_STAGE, 'deterministic')).toBe(false);
  });
});
