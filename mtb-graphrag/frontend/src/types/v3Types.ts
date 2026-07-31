export type ClaimDomain = 'therapeutic' | 'diagnostic' | 'prognostic' | 'untyped';
export type EvidenceBucket = 'primary' | 'warning' | 'audit' | 'rejected';
export type GateStepStatus = 'pass' | 'warning' | 'fail' | 'not_applicable';

export interface V3Query {
  query_id?: string;
  claim_domain: string;
  biomarker: string;
  disease: string;
  gene?: string;
  alteration?: string;
  interventions?: string[];
  policy_mode?: string;
  result_limit?: number;
}

export interface V3RetrievalRequest {
  domain: string;
  biomarker: string;
  disease: string;
  intervention?: string | null;
  policy_mode?: string;
  result_limit?: number | null;
  query_id?: string | null;
  include_warning?: boolean;
  include_audit?: boolean;
  include_rejected?: boolean;
}

export interface V3MetadataResponse {
  backend_identifier: string;
  corpus_version: string;
  corpus_digest: string;
  gate_version: string;
  scoring_version: string;
  retriever_version: string;
  rendering_model_identifier: string;
  rendering_enabled: boolean;
  service_status: string;
  promoted_at: string;
  policy_mode: string;
}

export interface V3BucketSummary {
  total: number;
  primary: number;
  warning: number;
  audit: number;
  rejected: number;
}

export interface Locator {
  pmid?: number | string;
  locator_type?: string;
  locator_value?: string;
  section_title?: string;
}

export interface GraphEvidenceLineage {
  claim_id?: string;
  parent_id?: string;
  graph_evidence_id?: string;
  source_ids?: string[];
  source_unit_ids?: string[];
  legacy_statement_ids?: string[];
  locators?: Locator[];
  adapter_lineage?: {
    adapter_version?: string;
    [key: string]: unknown;
  };
  disease_relation_provenance?: {
    relation_verified?: boolean;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface GateTraceStep {
  step_key?: string;
  stage_name: string;
  status: GateStepStatus | string;
  reason_code: string;
  explanation: string;
  query_value: string;
  claim_value: string;
}

export interface V3ClaimResult {
  claim_id: string;
  parent_id: string;
  graph_evidence_id: string;
  claim_domain: string;
  claim_type: string;
  bucket: EvidenceBucket | string;
  section?: string;
  rank: number;
  biomarker: string;
  disease_scope: string;
  canonical_intervention: string;
  intervention_members?: string[];
  source_literal_members?: string[];
  gate?: Record<string, unknown>;
  score?: {
    total_score?: number;
    [key: string]: unknown;
  } | number | any;
  provenance?: GraphEvidenceLineage | Record<string, any>;
  warnings: string[];
  reason_codes: string[];
  explanation_codes?: string[];
  gate_trace?: {
    steps?: GateTraceStep[];
    dominant_gate?: string;
    gate_version?: string;
    [key: string]: unknown;
  } | GateTraceStep[] | any;
  schema_version?: string;
}

export interface V3Metadata {
  corpus_version: string;
  corpus_digest: string;
  gate_version: string;
  retriever_version: string;
  run_id: string;
  policy_mode: string;
  elapsed_ms: number;
  latency_ms?: Record<string, number>;
  gate_decisions?: Record<string, unknown>;
}

export interface V3RetrievalResponse {
  query_id: string;
  query: Record<string, unknown>;
  summary: V3BucketSummary;
  buckets: {
    primary: V3ClaimResult[];
    warning: V3ClaimResult[];
    audit: V3ClaimResult[];
    rejected: V3ClaimResult[];
  };
  metadata: V3Metadata;
  warnings: string[];
}

export interface V3RenderRequest {
  query_id?: string;
  claims: V3ClaimResult[];
  include_disclaimer?: boolean;
}

export interface V3RenderResponse {
  query_id: string;
  rendered_report: string;
  claim_ids_used: string[];
  cited_pmids: string[];
  disclaimer: string;
  model_identifier: string;
}

export type V3RetrievalResult = V3RetrievalResponse;
