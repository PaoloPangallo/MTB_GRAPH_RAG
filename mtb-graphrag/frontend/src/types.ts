export type AlterationType = "point_mutation" | "fusion" | "cna" | "itd" | "atypical" | "biomarker";

export interface MTBRequest {
  gene?: string;
  variant: string;
  tumor_type: string;
  alteration_type: AlterationType;
  therapy_line: string;
  enrich_with_oncokb: boolean;
  report?: string;
  driver_variant?: string;
  disease_stage?: string | null;
  disease_setting?: 'resected' | 'locally-advanced' | 'metastatic' | null;
  prior_therapies?: string[];
  prior_response?: string | null;
  ecog_status?: number | null;
  cns_metastases?: boolean | null;
  co_alterations?: string[];
  jurisdiction?: string | null;
  mtb_goal?: 'general-review' | 'treatment-evidence' | 'resistance' | 'clinical-trials' | null;
}


export interface DrugCandidate {
  drug_name: string;
  approved: boolean;
  companion_diagnostic?: string;
  cd_platform?: string;
  evidence_level: string;
}

export interface ResistanceData {
  variant: string;
  evidence_level: string;
  disease: string;
  statement: string;
  pmid?: number;
  citation_text?: string;
}

export interface TrialCandidate {
  nct_id: string;
  title: string;
  phase: string;
  status: string;
  drug_tested?: string;
}

export interface OncoKBEnrichment {
  drugs: string[];
  level: string;
  fda_level?: string;
  cancer_type?: string;
  pmids: number[];
  description: string;
}

export interface ReportResponse {
  complexity: string;
  escat_tier: string;
  report: string;
  cited_pmids: number[];
  drug_candidates: DrugCandidate[];
  resistance_data: ResistanceData[];
  trial_candidates: TrialCandidate[];
  oncokb_enrichment?: OncoKBEnrichment[] | null;
}

export interface JudgeRequest {
  report: string;
  gene?: string;
  variant: string;
  tumor_type: string;
}

export interface JudgeResponse {
  completezza?: number;
  utilita_clinica?: number;
  fedelta_evidenze?: number;
  accuratezza_clinica?: number;
  score_totale?: number;
  motivazione?: string;
  raw_response?: string;
  error?: string;
}

export type ExecutionMode = 'demo' | 'live';

export interface TraceStep {
  order: number;
  stage: string;
  actor: string;
  detail: string;
  status: 'completed' | 'warning' | 'blocked';
}

export interface EvidenceItem {
  subject: string;
  relation: string;
  object: string;
  context: string;
  source_id?: string | null;
  provenance: string;
  evidence_statement?: string | null;
  citation_text?: string | null;
  evidence_level?: string | null;
}

export interface ClaimCheck {
  claim: string;
  status: 'supported' | 'insufficient' | 'blocked' | 'not_checked';
  reason: string;
  source_id?: string | null;
  verification_level?: string | null;
  requires_human_review?: boolean;
}

export interface DossierCaseField {
  key: string;
  label: string;
  value?: string | null;
  confirmed: boolean;
}

export type DossierSection =
  | 'supported_compatible'
  | 'supported_indeterminate'
  | 'supported_not_compatible'
  | 'review'
  | 'excluded';

export interface DossierEvidence {
  evidence_id: string;
  claim: string;
  therapy: string;
  setting: string;
  source_id?: string | null;
  evidence_level?: string | null;
  source_support_status: 'supported_as_written' | 'supported_after_contextualization' | 'uncertain' | 'contradicted';
  source_support_reason: string;
  source_population?: string | null;
  source_line?: string | null;
  source_setting?: string | null;
  source_prerequisites?: string | null;
  derived_verified_claim?: string | null;
  applicability_status: 'compatible' | 'indeterminate' | 'not_compatible';
  applicability_reason: string;
  requires_source_review: boolean;
  requires_clinical_review: boolean;
  dossier_section: DossierSection;
}

export interface DossierFinding {
  title: string;
  detail: string;
  source_id?: string | null;
}

export interface ClinicalDossier {
  case_summary: DossierCaseField[];
  missing_data: string[];
  // Vista canonica unica: ogni evidenza compare una sola volta, con
  // entrambi gli assi di verifica; le sezioni cliniche si ottengono
  // raggruppando per dossier_section (vedi groupDossierEvidence).
  evidence: DossierEvidence[];
  resistance_findings: DossierFinding[];
  trial_findings: DossierFinding[];
  mtb_questions: string[];
}

export interface ArchitectureRun {
  architecture_id: 'deterministic' | 'agentic';
  title: string;
  subtitle: string;
  llm_roles: string[];
  trace: TraceStep[];
  evidence: EvidenceItem[];
  report: string;
  dossier: ClinicalDossier;
  claim_checks: ClaimCheck[];
  metrics: {
    elapsed_ms: number;
    tool_calls: number;
    evidence_count: number;
    verified_claims: number;
    blocked_claims: number;
    review_claims?: number;
    ledger_events?: number;
    stage_timings_ms?: Record<string, number>;
    // Conteggi distinti sui due assi — mai sommati fra loro né coi conteggi legacy sopra.
    source_supported_count?: number;
    source_uncertain_count?: number;
    source_unsupported_count?: number;
    // Suddivisione del conteggio "supported" sopra nella tassonomia
    // documentale a quattro valori (la somma dei due torna a source_supported_count).
    source_supported_as_written_count?: number;
    source_supported_after_contextualization_count?: number;
    applicability_compatible_count?: number;
    applicability_indeterminate_count?: number;
    applicability_not_compatible_count?: number;
    // Diagnostica tecnica del verificatore (cache del profilo sorgente,
    // batching, recupero via retry) — separata dai conteggi clinici sopra.
    cache_hits?: number;
    cache_misses?: number;
    verifier_batches?: number;
    failed_batches?: number;
    retry_items?: number;
    recovered_items?: number;
    permanently_failed_items?: number;
    source_profile_elapsed_ms?: number;
    applicability_elapsed_ms?: number;
  };
  limitations: string[];
  run_id?: string | null;
  ledger_valid?: boolean | null;
  planning_mode?: string | null;
  fallback_reason?: string | null;
  planner_attempts?: number | null;
  planner_elapsed_ms?: number | null;
  tool_call_timings?: Array<{ tool: string; sequence: number; elapsed_ms: number; status: string }>;
}

export interface ArchitectureComparisonResponse {
  execution_mode: ExecutionMode;
  case_label: string;
  disclaimer: string;
  deterministic: ArchitectureRun;
  agentic: ArchitectureRun;
  summary: {
    shared_sources: string[];
    deterministic_only_sources: string[];
    agentic_only_sources: string[];
    explanation: string;
  };
}


// ── Knowledge Graph 3D Types ──────────────────────────────

export type GraphNodeType =
  | 'gene'
  | 'variant'
  | 'molecular_profile'
  | 'drug'
  | 'evidence'
  | 'publication'
  | 'clinical_trial'
  | 'companion_diagnostic'
  | 'resistance'
  | 'llm_memory';

export interface GraphNodeMetadata {
  [key: string]: string | number | boolean | undefined;
  approved?: boolean;
  citation_text?: string;
  companion_diagnostic?: string;
  description?: string;
  disease?: string;
  drug_name?: string;
  escat_tier?: string;
  evidence_level?: string;
  hallucinated?: boolean;
  hugo_symbol?: string;
  nct_id?: string;
  phase?: string;
  pmid?: number;
  significance?: string;
  statement?: string;
  status?: string;
  title?: string;
  url?: string;
  variant_name?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: GraphNodeType;
  color: string;
  val?: number;          // node size weight for force-graph
  metadata: GraphNodeMetadata;
}

export interface GraphLink {
  source: string;
  target: string;
  label: string;
  type: string;
}

export interface SubGraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}
