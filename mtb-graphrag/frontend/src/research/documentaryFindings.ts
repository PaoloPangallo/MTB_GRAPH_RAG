import type { Dossier, EvidenceRecord } from './DossierView';

export function documentaryChecks(record: EvidenceRecord) {
  const v = record.document_verification;
  return {
    quotation: record.quote_valid === true ? 'Autenticata' : record.quote_valid === false ? 'Validazione non superata' : 'Non registrata',
    structural: typeof v?.structural_status === 'string' ? v.structural_status : 'Non registrato',
    semantic: v?.final_admission === 'TECHNICAL_ERROR' || v?.verification_status === 'TECHNICAL_ERROR' ? 'Errore tecnico'
      : (typeof v?.final_admission === 'string' && v.final_admission.startsWith('NOT_RUN')) || v?.verification_status === 'SEMANTIC_ASSESSMENT_NOT_RUN' ? 'Non eseguita'
        : v?.verification_status === 'ASSESSED' ? 'Valutazione registrata'
          : record.relation_family === 'EVIDENCE_STATEMENT' ? 'Non prevista dalla policy' : 'Non registrata',
  };
}

export function findingCounts(dossier: Dossier) {
  const entries = dossier.paper_evidence ?? [];
  const records = new Map<string, EvidenceRecord>();
  for (const entry of entries) {
    const observations = entry.accepted_evidence_records?.length ? entry.accepted_evidence_records
      : entry.quote ? [{ quote: entry.quote, quote_valid: entry.quote_valid, paper_id: entry.representative_document_id ?? entry.document_id, source_unit_id: entry.quote_source_unit_id }] : [];
    observations.forEach((record, index) => records.set(record.evidence_id ?? `${entry.candidate_id}:${index}`, record));
  }
  return { relations: entries.length, records: records.size,
    authenticated: [...records.values()].filter(record => record.quote_valid === true).length,
    publications: new Set([...records.values()].map(record => record.public_source_identity ?? record.document_id ?? record.paper_id).filter(Boolean)).size };
}
