import { Box, Typography } from '@mui/material';
import type { Dossier } from './DossierView';
import { findingCounts } from './documentaryFindings';
import { color } from './tokens';

export default function SupportSummary({ dossier }: { dossier: Dossier }) {
  const counts = findingCounts(dossier);
  if (!counts.relations) return null;
  const summary = dossier.documentary_summary;
  const documentary = dossier.documentary_contract_version && summary;
  return <Box aria-label="Osservazioni documentali" sx={{ mb: 2 }}>
    <Typography sx={{ fontWeight: 600, fontSize: 14 }}>Osservazioni documentali</Typography>
    <Typography sx={{ fontSize: 14, color: color.slate }}>{documentary
      ? `${counts.relations} relazioni cercate / ${summary.retained_record_count ?? 'non registrato'} record conservati / ${summary.excluded_record_count ?? 'non registrato'} record esclusi / ${summary.authenticated_record_count ?? 'non registrato'} citazioni autenticate / ${summary.distinct_source_identifier_count ?? 'non registrato'} identificativi di fonte distinti`
      : `${counts.relations} relazioni cercate / ${counts.records} record conservati / ${counts.authenticated} citazioni autenticate / ${counts.publications} identificativi di pubblicazione distinti`}</Typography>
    <Typography sx={{ fontSize: 12, color: color.slate }}>Autenticazione, corrispondenza con il target e completezza della run sono controlli distinti. Questi conteggi non misurano correttezza clinica.</Typography>
  </Box>;
}
