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
  | 'CALL_BUDGET_EXCEEDED'
  | 'DOCUMENT_CACHE_UNAVAILABLE'
  | 'NO_DOCUMENT_RESOLVED'
  | 'LIVE_STAGE_FAILED';

/**
 * Modalità di esecuzione. `HYBRID` non è richiedibile: è la classificazione di
 * una run avviata LIVE che ha comunque usato un artefatto registrato.
 */
export type ExecutionMode = 'LIVE' | 'REPLAY' | 'HYBRID';

export type RequestableMode = 'LIVE' | 'REPLAY';

/**
 * Da dove viene il risultato di uno stage.
 *
 * `DETERMINISTIC_CACHE` e `RECORDED_REAL_RUN` non sono la stessa cosa e non
 * vanno resi con lo stesso badge: un documento letto dalla cache locale
 * appartiene a una run live, una risposta del modello registrata no.
 */
export type ArtifactOrigin =
  | 'GENERATED_NOW'
  | 'RECORDED_REAL_RUN'
  | 'DETERMINISTIC_CACHE'
  | 'NOT_APPLICABLE'
  | 'NOT_EXECUTED';

export interface DocumentCacheStatus {
  document_cache_available: boolean;
  cache_path_redacted?: string;
  cache_version?: string;
  manifest_hash?: string | null;
  manifest_rows?: number;
  document_count?: number;
  documents_with_text?: number;
  documents_unavailable?: number;
  source_unit_count?: number;
  reason_codes?: string[];
}

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
  execution_mode: ExecutionMode;
  artifact_origin: ArtifactOrigin;
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
  /** Modalità richiesta all'avvio. */
  requested_mode: RequestableMode;
  /** Modalità **effettiva**, derivata dalle origini degli stage dal backend. */
  execution_mode: ExecutionMode;
  /** Vero solo con `execution_mode === 'LIVE'` e zero artefatti registrati. */
  fully_live: boolean;
  replay_artifacts_used: number;
  origin_counts: Partial<Record<ArtifactOrigin, number>>;
  document_cache: DocumentCacheStatus;
  llm_calls: number;
  /** Presenti solo su una run ricostruita dal ledger. */
  rehydrated?: boolean;
  recovery_status?: 'COMPLETE' | 'RECOVERED_INCOMPLETE';
  hash_chain_valid?: boolean;
  stages_missing?: string[];
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
  requested_mode: RequestableMode;
  execution_mode: ExecutionMode;
  /** Esiste una run registrata equivalente da poter consultare a parte. */
  replay_run_available: boolean;
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
  accepted_quotes?: Array<Record<string, unknown>>;
  rejected_quotes?: Array<Record<string, unknown>>;
  abstentions?: Array<Record<string, unknown>>;
  validations?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
}

export interface ProvenanceItem {
  candidate_id: string;
  chain: ProvenanceLevel[];
  /** Vero solo con almeno una citazione accettata. */
  document_grounded?: boolean;
  /** `DOCUMENT_GROUNDED` oppure `PARENT_LEVEL_ONLY`. */
  provenance_level?: string;
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

/**
 * Tipi di evento emessi dal backend.
 *
 * Servono a registrare un listener per ciascuno: lo stream SSE invia eventi
 * **con nome** (`event: STAGE_COMPLETED`), e `EventSource.onmessage` scatta
 * soltanto per quelli senza nome. Senza queste registrazioni il browser non
 * riceve nulla, pur essendo lo stream perfettamente valido.
 */
export const SSE_EVENT_TYPES: readonly string[] = [
  'RUN_CREATED',
  'STAGE_STARTED',
  'STAGE_COMPLETED',
  'STAGE_WARNING',
  'STAGE_FAILED',
  'STAGE_SKIPPED',
  'RUN_COMPLETED',
  'CASECONTEXT_PARSED',
  'CASECONTEXT_VERIFIED',
  'RETRIEVAL_COMPLETED',
  'CANDIDATES_FOUND',
  'DOCUMENT_RESOLVED',
  'SOURCE_UNIT_MATERIALIZED',
  'PAPER_SELECTED',
  'ENRICHMENT_PROPOSED',
  'ENRICHMENT_VALIDATED',
  'GATES_COMPUTED',
  'STATUS_ASSIGNED',
  'DOSSIER_BUILT',
] as const;

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
  live:
    'Eseguito al momento della run. Il risultato è stato prodotto ora, non recuperato.',
  cached_document:
    'Documento letto dalla cache autorizzata durante la run. È lettura di una fonte, non un replay: lo stage resta parte di una run live.',
  hybrid:
    'Run avviata in LIVE che ha comunque usato almeno un artefatto registrato. Non può essere presentata come completamente live.',
  fully_live:
    'Ogni stage applicabile è stato eseguito ora e nessun artefatto registrato è stato usato.',
  deterministic:
    'Prodotto da codice, non da un modello. Gate, status e bucket sono sempre deterministici.',
  llm:
    'Prodotto da un modello. Solo il parser e il Paper Context Enricher lo sono.',
  abstain:
    'Il modello non ha trovato una frase letterale a supporto e si è astenuto. È un esito normale.',
  stopped:
    'La pipeline si è fermata perché doveva: un campo essenziale non trova riscontro, o il grafo non propone candidate.',
};
