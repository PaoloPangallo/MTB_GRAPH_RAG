/**
 * Contratti del research runtime verificabile.
 *
 * Rispecchiano `docs/verifiable_pipeline/api_contract.md`. Sono deliberatamente
 * separati da `src/types.ts`, che descrive i percorsi V2/V3 preesistenti: tenerli
 * distinti impedisce che il vocabolario della vecchia pipeline rientri da qui.
 */

export type RunStatus =
  | 'CREATED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'PARTIAL'
  | 'FAILED'
  | 'STOPPED';

export type StageStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'WARNING'
  | 'FAILED'
  | 'SKIPPED';

export type StopReason =
  | 'PARSER_TRANSPORT_FAILED'
  | 'CASECONTEXT_MISMATCH'
  | 'RETRIEVAL_NO_MATCH'
  | 'CALL_BUDGET_EXCEEDED';

export type ProducerKind = 'DETERMINISTIC' | 'LLM' | 'HYBRID';

export interface StageProducer {
  kind: ProducerKind;
  component: string;
  version: string;
  model: string | null;
  prompt_version: string | null;
  transport_version?: string | null;
}

export interface PipelineStage {
  stage_id: string;
  stage_type: string;
  sequence: number;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  input_preview: Record<string, unknown>;
  output_preview: Record<string, unknown>;
  reason_codes: string[];
  warnings: string[];
  errors: string[];
  producer: StageProducer;
  metrics: Record<string, unknown>;
  lineage: Record<string, unknown>;
}

export interface ResearchNotice {
  runtime: string;
  clinically_validated: boolean;
  not_for_clinical_decision_making: boolean;
  experimental_component: boolean;
}

export interface PipelineRun {
  run_id: string;
  case_id: string;
  status: RunStatus;
  started_at: string;
  completed_at: string | null;
  current_stage: string | null;
  stopped_at: StopReason | null;
  input_text: string;
  stages: PipelineStage[];
  dossier_id: string | null;
  warnings: string[];
  errors: string[];
  versions: Record<string, unknown>;
  metrics: Record<string, unknown>;
  research_notice: ResearchNotice;
}

export interface PipelineEvent {
  event_id: string;
  sequence: number;
  event_type: string;
  created_at: string;
  actor: string;
  stage_id: string | null;
  stage_type: string | null;
  producer: StageProducer | null;
  payload_hash: string | null;
  payload: Record<string, unknown>;
}

export interface EventPage {
  run_id: string;
  append_only: boolean;
  hash_chain_valid: boolean;
  events: PipelineEvent[];
  next_after_sequence: number;
  has_more: boolean;
}

export interface DemoCase {
  case_id: string;
  clinical_text: string;
  expected_query_intent: string | null;
  expected_result: string | null;
  frozen_artifacts_available: boolean;
}

export interface CreatedRun {
  run_id: string;
  case_id: string;
  status: RunStatus;
  execution_mode: 'FROZEN_REPLAY' | 'LIVE';
  stream_url: string;
  research_notice: ResearchNotice;
}

export interface ProvenanceLevel {
  level: string;
  ref?: unknown;
  graph_derived?: boolean;
  documentary_proof?: boolean;
  replayed?: boolean;
  units?: Array<Record<string, unknown>>;
  text_never_exposed?: boolean;
}

export interface ProvenanceItem {
  candidate_id: string;
  chain: ProvenanceLevel[];
}

export interface RunMetrics {
  run_id: string;
  duration_ms_total: number | null;
  duration_ms_by_stage: Record<string, number | null>;
  llm_calls: number;
  tokens_input: number | null;
  tokens_output: number | null;
  candidates_found: number;
  candidates_excluded: number;
  quotes_accepted: number;
  quotes_rejected: number;
  abstentions: number;
  warnings: number;
  errors: number;
  status_counts: Record<string, number>;
  computed_by: string;
}

/** Etichette italiane degli stage. L'ordine è quello del contratto. */
export const STAGE_LABELS: Record<string, string> = {
  stage_1_case_input: 'Caso clinico',
  stage_2_casecontext_parser: 'CaseContext Parser',
  stage_3_casecontext_match: 'CaseContext Match',
  stage_4_retrieval_plan: 'Piano di retrieval',
  stage_5_kg_retrieval: 'Knowledge Graph',
  stage_6_document_resolution: 'Document Resolution',
  stage_7_source_units: 'Source Unit',
  stage_8_paper_selection: 'Paper Selection',
  stage_9_paper_context_enricher: 'Paper Context Enricher',
  stage_10_enrichment_validation: 'Quote Validation',
  stage_11_deterministic_gates: 'Deterministic Gates',
  stage_12_status: 'Status',
  stage_13_dossier: 'Dossier',
  stage_14_narrator: 'Narratore',
  stage_15_narrative_verifier: 'Verifica narrativa',
};

/**
 * Spiegazioni brevi dei termini, mostrate come tooltip.
 * Servono a impedire la lettura più pericolosa: che una candidate del grafo sia
 * già una prova.
 */
export const TERM_TOOLTIPS: Record<string, string> = {
  graph_derived:
    'Associazione proposta dal Knowledge Graph. Non è ancora una prova documentale.',
  document_grounded:
    'Affermazione sostenuta da una citazione letterale verificata in una Source Unit.',
  replayed:
    'Artefatto congelato di una run precedente: risposta reale del modello, non rieseguita ora.',
  deterministic:
    'Prodotto da codice, non da un modello. Gate, status e bucket sono sempre deterministici.',
  llm:
    'Prodotto da un modello. Solo il parser e il Paper Context Enricher lo sono.',
  abstain:
    'Il modello non ha trovato una frase letterale a supporto e si è astenuto. È un esito normale.',
  stopped:
    'La pipeline si è fermata perché doveva: un campo essenziale non trova riscontro, o il grafo non propone candidate.',
};
