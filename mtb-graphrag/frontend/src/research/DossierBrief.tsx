import { Box, Button, Typography } from '@mui/material';
import type { Dossier } from './DossierView';
import CaseSummaryView from './CaseSummaryView';
import DocumentaryObservation from './DocumentaryObservation';
import { color } from './tokens';
import { readingFor } from './readingGuide';

/** A readable projection of recorded findings; never a clinical recommendation. */
export default function DossierBrief({ dossier, onNavigate }: { dossier: Dossier; onNavigate?: (anchor: string) => void }) {
  const missingProjection = (dossier.paper_evidence ?? []).some(entry => !Array.isArray(entry.documentary_findings));
  const findings = (dossier.paper_evidence ?? []).flatMap(entry => (entry.documentary_findings ?? []).map((finding, index) => ({ finding, reading: readingFor(dossier.reading_guide, entry.candidate_id, index) })));
  const retained = findings.filter(item => item.finding.disposition === 'RETAINED_RECORD');
  const excluded = findings.filter(item => item.finding.disposition === 'EXCLUDED_RECORD');
  return <Box component="section" aria-label="Sintesi documentale" sx={{ my: 3, minWidth: 0 }}>
    <Typography component="h2" sx={{ fontSize: 22, fontWeight: 600, mb: 1.5 }}>Domanda esaminata</Typography>
    <CaseSummaryView value={dossier.case_summary} />
    <Typography component="h3" sx={{ fontSize: 20, fontWeight: 600, mt: 3, mb: 1 }}>Cosa riportano le fonti</Typography>
    <Typography sx={{ color: color.slate, maxWidth: '72ch', mb: 1.5 }}>Il confronto tra intervento richiesto e intervento osservato non stabilisce equivalenza o applicabilità al paziente. Popolazione e modello sperimentale vanno verificati nella fonte.</Typography>
    {missingProjection ? <Typography sx={{ mb: 1 }}>Sintesi documentale non disponibile per questa versione di alcune relazioni. Consulta Relazioni per tutti i record; le osservazioni eventualmente riportate sotto coprono soltanto il nuovo formato.</Typography> : <Typography sx={{ mb: 1 }}>{retained.length} record conservati / {excluded.length} record esclusi dalle osservazioni di pubblicazione registrate.</Typography>}
    {retained.length ? <>
      <Typography variant="body2" sx={{ color: color.slate }}>Prime {Math.min(3, retained.length)} osservazioni conservate nell’ordine del dossier; non è una graduatoria di rilevanza o efficacia.</Typography>
      {retained.slice(0, 3).map(({ finding, reading }, index) => <DocumentaryObservation key={`${finding.candidate_id}:${finding.evidence_id ?? index}`} finding={finding} reading={reading} />)}
    </> : !missingProjection && <Typography>Nessuna osservazione conservata disponibile per questa sintesi. Questo non dimostra assenza di evidenze scientifiche: consulta tentativi, esclusioni e limiti.</Typography>}
    {onNavigate && <Button onClick={() => onNavigate('dossier-paper')} sx={{ mt: 1 }}>Leggi osservazioni e fonti</Button>}
  </Box>;
}
