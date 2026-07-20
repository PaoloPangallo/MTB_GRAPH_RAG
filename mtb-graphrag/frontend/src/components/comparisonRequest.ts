import type { AlterationType, ExecutionMode } from '../types';

export interface ComparisonFormState {
  gene: string;
  variant: string;
  tumorType: string;
  alterationType: AlterationType;
  therapyLine: string;
  diseaseStage: string;
  diseaseSetting: string;
  priorTherapies: string;
  priorResponse: string;
  ecogStatus: string;
  cnsMetastases: string;
  coAlterations: string;
  jurisdiction: string;
  mtbGoal: string;
  mode: ExecutionMode;
}

export interface ComparisonRequestPayload {
  gene: string;
  variant: string;
  tumor_type: string;
  alteration_type: AlterationType;
  therapy_line: string;
  disease_stage: string | null;
  disease_setting: string | null;
  prior_therapies: string[];
  prior_response: string | null;
  ecog_status: number | null;
  cns_metastases: boolean | null;
  co_alterations: string[];
  jurisdiction: string | null;
  mtb_goal: string;
  enrich_with_oncokb: boolean;
  execution_mode: ExecutionMode;
}

export function splitClinicalValues(value: string): string[] {
  return value.split(',').map(item => item.trim()).filter(Boolean);
}

/**
 * Costruisce il payload inviato a /compare-architectures a partire dallo
 * stato del form. Dati clinici non compilati restano `null`/array vuoto —
 * nessun valore clinico viene mai dedotto o precompilato qui.
 */
export function buildComparisonRequest(formState: ComparisonFormState): ComparisonRequestPayload {
  return {
    gene: formState.gene,
    variant: formState.variant,
    tumor_type: formState.tumorType,
    alteration_type: formState.alterationType,
    therapy_line: formState.therapyLine,
    disease_stage: formState.diseaseStage || null,
    disease_setting: formState.diseaseSetting || null,
    prior_therapies: splitClinicalValues(formState.priorTherapies),
    prior_response: formState.priorResponse || null,
    ecog_status: formState.ecogStatus === '' ? null : Number(formState.ecogStatus),
    cns_metastases: formState.cnsMetastases === '' ? null : formState.cnsMetastases === 'present',
    co_alterations: splitClinicalValues(formState.coAlterations),
    jurisdiction: formState.jurisdiction || null,
    mtb_goal: formState.mtbGoal,
    enrich_with_oncokb: false,
    execution_mode: formState.mode,
  };
}
