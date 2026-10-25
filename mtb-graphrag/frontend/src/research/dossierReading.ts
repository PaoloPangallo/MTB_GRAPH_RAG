import type { CanonicalEntry } from './DossierView';

/** Display transformations only: no inferred relevance, efficacy or eligibility. */
export function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}
export function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
const vocabulary: Record<string, string> = {
  SENSITIVITY_RESPONSE: 'Sensibilità o risposta riportata', RESISTANCE: 'Resistenza riportata',
  ADVERSE_RESPONSE: 'Risposta avversa riportata', NOT_APPLICABLE: 'Non applicabile',
  RESISTANCE_NON_RESPONSE: 'Resistenza o mancata risposta riportata', UNKNOWN: 'Non determinato',
  COHORT: 'Coorte', PATIENT: 'Paziente', CELL_MODEL: 'Modello cellulare', ANIMAL_MODEL: 'Modello animale',
  INDIVIDUAL: 'Singolo individuo', POPULATION: 'Popolazione',
  PRECLINICAL: 'Preclinico', CLINICAL: 'Clinico', SINGLE_AGENT: 'Singolo agente', COMBINATION: 'Combinazione',
  SINGLE: 'Singolo elemento', NOT_SPECIFIED: 'Non specificato',
  ALTERNATIVES: 'Varianti alternative o coorti distinte',
  RECRUITING: 'In reclutamento', NOT_YET_RECRUITING: 'Reclutamento non ancora iniziato',
  ACTIVE_NOT_RECRUITING: 'Attivo, non in reclutamento', COMPLETED: 'Concluso', TERMINATED: 'Interrotto',
  SUSPENDED: 'Sospeso', WITHDRAWN: 'Ritirato', PHASE1: 'Fase 1', PHASE2: 'Fase 2', PHASE3: 'Fase 3', PHASE4: 'Fase 4',
};
export function readable(value: unknown): string | null {
  const raw = text(value);
  return raw ? vocabulary[raw] ?? raw : null;
}
export function studyGroups(entries: CanonicalEntry[]): CanonicalEntry[][] {
  const groups = new Map<string, CanonicalEntry[]>();
  entries.forEach((entry, index) => {
    const nct = entry.nct_id?.replace(/^nct:/i, '').toUpperCase();
    const key = nct && /^NCT\d{8}$/.test(nct) ? nct : `unresolved:${index}`;
    groups.set(key, [...(groups.get(key) ?? []), entry]);
  });
  return [...groups.values()];
}
export function entrySearchText(entry: CanonicalEntry): string {
  return JSON.stringify([
    entry.subject, entry.object, entry.title, entry.document_id, entry.representative_document_id,
    entry.declared_source_identity, entry.nct_id, entry.relation, entry.source_database,
    entry.support_level, entry.interventions, entry.conditions, entry.status, readable(entry.status),
    entry.phase, (Array.isArray(entry.phase) ? entry.phase : [entry.phase]).map(readable), entry.arm_groups,
    entry.accepted_evidence_records, entry.documentary_findings?.map(finding => ({
      source: finding.source, observed: finding.observed, quotation: finding.quotation,
    })),
  ]).toLocaleLowerCase('it');
}
