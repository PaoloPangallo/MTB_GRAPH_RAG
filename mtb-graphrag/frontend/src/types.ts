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

export interface GraphNode {
  id: string;
  label: string;
  type: GraphNodeType;
  color: string;
  val?: number;          // node size weight for force-graph
  metadata: Record<string, any>;
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

