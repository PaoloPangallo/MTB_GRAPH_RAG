import type {
  EvidenceBucket,
  GateTraceStep,
  Locator,
  V3ClaimResult,
  V3RetrievalResponse,
} from '../types/v3Types';

export function createEmptyV3Response(errorMessage?: string): V3RetrievalResponse {
  return {
    query_id: 'q_empty',
    query: {},
    summary: {
      total: 0,
      primary: 0,
      warning: 0,
      audit: 0,
      rejected: 0,
    },
    buckets: {
      primary: [],
      warning: [],
      audit: [],
      rejected: [],
    },
    metadata: {
      corpus_version: 'qualified_claim_repository/1.4',
      corpus_digest: '',
      gate_version: 'qualified_claim_structural_gate/1.3',
      retriever_version: 'qualified_claim_retriever/1.0',
      run_id: '',
      policy_mode: 'strict_verified',
      elapsed_ms: 0,
    },
    warnings: errorMessage ? [errorMessage] : [],
  };
}

export function normalizeV3Claim(raw: unknown, defaultBucket: EvidenceBucket = 'primary', index: number = 0): V3ClaimResult {
  if (!raw || typeof raw !== 'object') {
    return {
      claim_id: `claim_unknown_${index}`,
      parent_id: '',
      graph_evidence_id: '',
      claim_domain: 'therapeutic',
      claim_type: 'therapeutic_responsiveness_claim',
      bucket: defaultBucket,
      rank: index + 1,
      biomarker: 'Unknown Biomarker',
      disease_scope: 'Unknown Scope',
      canonical_intervention: 'Unknown Intervention',
      warnings: [],
      reason_codes: [],
    };
  }

  const obj = raw as Record<string, unknown>;
  const provenance = (obj.provenance && typeof obj.provenance === 'object' ? obj.provenance : {}) as Record<string, unknown>;
  const gate = (obj.gate && typeof obj.gate === 'object' ? obj.gate : {}) as Record<string, unknown>;
  const score = (obj.score && typeof obj.score === 'object' ? obj.score : {}) as Record<string, unknown>;

  const rawTrace = obj.gate_trace || gate.gate_trace;
  let steps: GateTraceStep[] = [];

  if (Array.isArray(rawTrace)) {
    steps = rawTrace.map(s => ({
      stage_name: String(s.stage_name || s.step_key || 'Gate Step'),
      status: String(s.status || 'pass'),
      reason_code: String(s.reason_code || 'CODE_OK'),
      explanation: String(s.explanation || ''),
      query_value: String(s.query_value || ''),
      claim_value: String(s.claim_value || ''),
    }));
  } else if (rawTrace && typeof rawTrace === 'object' && Array.isArray((rawTrace as any).steps)) {
    steps = (rawTrace as any).steps.map((s: any) => ({
      stage_name: String(s.stage_name || s.step_key || 'Gate Step'),
      status: String(s.status || 'pass'),
      reason_code: String(s.reason_code || 'CODE_OK'),
      explanation: String(s.explanation || ''),
      query_value: String(s.query_value || ''),
      claim_value: String(s.claim_value || ''),
    }));
  }

  return {
    claim_id: String(obj.claim_id || `claim_${index + 1}`),
    parent_id: String(obj.parent_id || provenance.parent_id || ''),
    graph_evidence_id: String(obj.graph_evidence_id || provenance.graph_evidence_id || ''),
    claim_domain: String(obj.claim_domain || 'therapeutic'),
    claim_type: String(obj.claim_type || 'therapeutic_responsiveness_claim'),
    bucket: (obj.bucket as EvidenceBucket) || defaultBucket,
    section: String(obj.section || ''),
    rank: typeof obj.rank === 'number' ? obj.rank : index + 1,
    biomarker: String(obj.biomarker || 'Biomarcatore non specificato'),
    disease_scope: String(obj.disease_scope || 'Patologia non specificata'),
    canonical_intervention: String(obj.canonical_intervention || 'Intervento non specificato'),
    intervention_members: Array.isArray(obj.intervention_members) ? obj.intervention_members.map(String) : [],
    source_literal_members: Array.isArray(obj.source_literal_members) ? obj.source_literal_members.map(String) : [],
    gate,
    score,
    provenance: {
      ...provenance,
      claim_id: String(provenance.claim_id || obj.claim_id || ''),
      parent_id: String(provenance.parent_id || obj.parent_id || ''),
      source_ids: Array.isArray(provenance.source_ids) ? provenance.source_ids.map(String) : [],
      source_unit_ids: Array.isArray(provenance.source_unit_ids) ? provenance.source_unit_ids.map(String) : [],
      legacy_statement_ids: Array.isArray(provenance.legacy_statement_ids) ? provenance.legacy_statement_ids.map(String) : [],
      locators: Array.isArray(provenance.locators) ? provenance.locators as Locator[] : [],
    },
    warnings: Array.isArray(obj.warnings) ? obj.warnings.map(String) : [],
    reason_codes: Array.isArray(obj.reason_codes) ? obj.reason_codes.map(String) : [],
    explanation_codes: Array.isArray(obj.explanation_codes) ? obj.explanation_codes.map(String) : [],
    gate_trace: {
      steps,
      dominant_gate: String(gate.dominant_gate || 'structural_gate'),
      gate_version: String(gate.gate_version || '1.3'),
    },
    schema_version: String(obj.schema_version || 'qualified_claim_result/1.4'),
  };
}

export function normalizeV3RetrievalResult(raw: unknown): V3RetrievalResponse {
  if (!raw || typeof raw !== 'object') {
    return createEmptyV3Response('Non valido');
  }
  const obj = raw as Record<string, unknown>;
  const rawBuckets = (obj.buckets && typeof obj.buckets === 'object' ? obj.buckets : {}) as Record<string, unknown>;

  const rawPrimary = (rawBuckets.primary || obj.primary_ranked_results || []) as any[];
  const rawWarning = (rawBuckets.warning || obj.retained_with_warning || []) as any[];
  const rawAudit = (rawBuckets.audit || obj.audit_only_results || []) as any[];
  const rawRejected = (rawBuckets.rejected || obj.rejected_by_native_constraints || []) as any[];

  const primary = Array.isArray(rawPrimary) ? rawPrimary.map((c: any, i: number) => normalizeV3Claim(c, 'primary', i)) : [];
  const warning = Array.isArray(rawWarning) ? rawWarning.map((c: any, i: number) => normalizeV3Claim(c, 'warning', i)) : [];
  const audit = Array.isArray(rawAudit) ? rawAudit.map((c: any, i: number) => normalizeV3Claim(c, 'audit', i)) : [];
  const rejected = Array.isArray(rawRejected) ? rawRejected.map((c: any, i: number) => normalizeV3Claim(c, 'rejected', i)) : [];

  const rawSummary = (obj.summary && typeof obj.summary === 'object' ? obj.summary : {}) as Record<string, number>;

  return {
    query_id: String(obj.query_id || 'q_demo'),
    query: (obj.query && typeof obj.query === 'object' ? obj.query : {}) as Record<string, unknown>,
    summary: {
      total: rawSummary.total ?? (primary.length + warning.length + audit.length + rejected.length),
      primary: rawSummary.primary ?? primary.length,
      warning: rawSummary.warning ?? warning.length,
      audit: rawSummary.audit ?? audit.length,
      rejected: rawSummary.rejected ?? rejected.length,
    },
    buckets: { primary, warning, audit, rejected },
    metadata: {
      corpus_version: String((obj.metadata as any)?.corpus_version || obj.repository_version || 'qualified_claim_repository/1.4'),
      corpus_digest: String((obj.metadata as any)?.corpus_digest || obj.corpus_hash || ''),
      gate_version: String((obj.metadata as any)?.gate_version || obj.gate_version || 'qualified_claim_structural_gate/1.3'),
      retriever_version: 'qualified_claim_retriever/1.0',
      run_id: String((obj.metadata as any)?.run_id || obj.run_id || ''),
      policy_mode: String((obj.metadata as any)?.policy_mode || obj.policy_mode || 'strict_verified'),
      elapsed_ms: Number((obj.metadata as any)?.elapsed_ms || 35),
    },
    warnings: Array.isArray(obj.warnings) ? obj.warnings.map(String) : [],
  };
}

export const createEmptyV3Result = createEmptyV3Response;
