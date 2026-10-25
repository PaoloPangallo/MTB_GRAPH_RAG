import { Box, Typography } from '@mui/material';
import type { Dossier } from './DossierView';
import StructuredValue from './values/StructuredValue';
import { color } from './tokens';
import { graphEntityLabel } from './graphEntityLabel';

/** Proiezione dei campi canonici ricevuti, senza ricalcolare supporto o ammissione. */
export default function CanonicalProvenance({ dossier }: { dossier: Dossier | null }) {
  if (!dossier) return <Typography>Provenienza canonica non disponibile.</Typography>;
  const entries = [
    ...(dossier.paper_evidence ?? []), ...(dossier.clinical_trials ?? []), ...(dossier.kg_only_relations ?? []),
  ];
  return <Box>
    <Typography component="h3" sx={{ mb: 1 }}>Provenienza del dossier canonico</Typography>
    <Typography variant="body2" sx={{ mb: 2 }}>
      Relazioni del grafo, identità delle fonti, record ammessi e rigettati sono quelli
      restituiti dal dossier. Citazioni, osservazioni estratte e controlli restano distinti; i campi originali sono conservati per audit.
    </Typography>
    {entries.length === 0 && <Typography>Nessuna relazione nel dossier canonico.</Typography>}
    {entries.map(entry => <Box key={entry.candidate_id} sx={{ py: 2, borderTop: `1px solid ${color.hairline}` }}>
      <Typography component="h4" sx={{ mb: 1 }}>{graphEntityLabel(entry.subject) ?? entry.candidate_id} → {graphEntityLabel(entry.object) ?? entry.title ?? '—'}</Typography>
      <StructuredValue value={{
        candidate_id: entry.candidate_id, relation: entry.relation, graph_provenance: entry.graph_provenance,
        declared_source_identity: entry.declared_source_identity, document_id: entry.document_id,
        nct_id: entry.nct_id, trial_resolution_status: entry.trial_resolution_status,
        support_level: entry.support_level, claim: entry.claim,
        accepted_evidence_records: entry.accepted_evidence_records, rejected_evidence: entry.rejected_evidence,
      }} />
    </Box>)}
  </Box>;
}
