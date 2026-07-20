import type { DossierEvidence, DossierSection } from '../types';

export const DOSSIER_SECTION_ORDER: DossierSection[] = [
  'supported_compatible',
  'supported_indeterminate',
  'supported_not_compatible',
  'review',
  'excluded',
];

export const DOSSIER_SECTION_TITLES: Record<DossierSection, string> = {
  supported_compatible: 'Evidenze supportate e compatibili con il contesto dichiarato',
  supported_indeterminate: 'Evidenze supportate con applicabilità indeterminata',
  supported_not_compatible: 'Evidenze supportate ma non compatibili con il contesto dichiarato',
  review: 'Evidenze con supporto documentale incerto',
  excluded: 'Claim non supportate dalla fonte',
};

export const DOSSIER_SECTION_SEVERITY: Record<DossierSection, 'success' | 'warning' | 'error'> = {
  supported_compatible: 'success',
  supported_indeterminate: 'warning',
  supported_not_compatible: 'warning',
  review: 'warning',
  excluded: 'error',
};

/**
 * Raggruppa la vista canonica delle evidenze nelle 5 sezioni cliniche, senza
 * duplicare o perdere elementi: ogni evidenza appartiene a una sola sezione,
 * derivata lato backend nel campo `dossier_section`.
 */
export function groupDossierEvidence(evidence: DossierEvidence[]): Record<DossierSection, DossierEvidence[]> {
  const grouped: Record<DossierSection, DossierEvidence[]> = {
    supported_compatible: [],
    supported_indeterminate: [],
    supported_not_compatible: [],
    review: [],
    excluded: [],
  };
  for (const item of evidence) {
    grouped[item.dossier_section].push(item);
  }
  return grouped;
}
