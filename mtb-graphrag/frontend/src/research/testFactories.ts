/**
 * Fabbriche condivise per i test del research runtime.
 *
 * Esistono perché ogni file di test ne aveva una propria: aggiungere un campo al
 * contratto costringeva a modificarle tutte, e finché non lo si faceva i test
 * continuavano a costruire oggetti che il backend non produce più. Una sola
 * fabbrica rende quella divergenza un errore di compilazione in un punto solo.
 *
 * I default descrivono lo **stato normale**: uno stage eseguito ora, dentro una
 * run live. Un test che vuole un replay deve chiederlo esplicitamente, così la
 * differenza resta leggibile nel test stesso.
 */

import type { PipelineRun, PipelineStage, StageProducer } from './types';

export const DETERMINISTIC_PRODUCER: StageProducer = {
  kind: 'DETERMINISTIC', component: 'orchestrator', version: '2.0',
  model: null, prompt_version: null,
};

export const LLM_PRODUCER: StageProducer = {
  kind: 'LLM', component: 'paper_context_enricher_v2', version: 'paper-context-enricher/2.0',
  model: 'gemma4:cloud', prompt_version: 'paper-context-enricher-prompt/2.0',
  transport_version: 'paper-context-enrichment-transport/2.0',
};

export function makeStage(overrides: Partial<PipelineStage> = {}): PipelineStage {
  return {
    stage_id: 'stage_1_case_input',
    stage_type: 'CASE_INPUT',
    sequence: 1,
    status: 'SUCCEEDED',
    started_at: null,
    completed_at: null,
    duration_ms: 10,
    input_preview: {},
    output_preview: {},
    reason_codes: [],
    warnings: [],
    errors: [],
    producer: DETERMINISTIC_PRODUCER,
    metrics: {},
    lineage: {},
    execution_mode: 'LIVE',
    artifact_origin: 'GENERATED_NOW',
    ...overrides,
  };
}

export function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    run_id: 'r1',
    case_id: 'CASE-1',
    status: 'COMPLETED',
    started_at: '2026-08-06T00:00:00Z',
    completed_at: '2026-08-06T00:00:05Z',
    current_stage: null,
    stopped_at: null,
    input_text: 'testo clinico',
    stages: [],
    dossier_id: 'CASE-1',
    warnings: [],
    errors: [],
    versions: {},
    metrics: {},
    research_notice: {
      runtime: 'VERIFIABLE_RESEARCH_RUNTIME',
      clinically_validated: false,
      not_for_clinical_decision_making: true,
      experimental_component: true,
    },
    requested_mode: 'LIVE',
    execution_mode: 'LIVE',
    fully_live: true,
    replay_artifacts_used: 0,
    origin_counts: { GENERATED_NOW: 11, DETERMINISTIC_CACHE: 2 },
    document_cache: {
      document_cache_available: true,
      cache_path_redacted: '.../data_cache/document_grounding',
      cache_version: 'authorized-document-cache/1.0',
      manifest_hash: 'ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b',
      document_count: 40,
      source_unit_count: 3402,
      reason_codes: [],
    },
    llm_calls: 2,
    ...overrides,
  };
}
