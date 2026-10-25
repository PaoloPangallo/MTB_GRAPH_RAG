import { Box, LinearProgress, Typography } from '@mui/material';
import { color, font } from './tokens';
import type { WorkPhase, WorkProgress } from './workProgress';

const labels: Record<WorkPhase, string> = {
  SOURCEUNIT_SELECTION: 'Selezione dei passaggi documentali',
  READER: 'Lettura del documento',
  VERIFICATION: 'Verifica della citazione e della relazione',
  SEMANTIC_VERIFICATION: 'Verifica semantica della relazione',
  CANDIDATE_COMPLETED: 'Associazione elaborata',
};

export default function WorkProgressPanel({ progress, debug }: { progress: WorkProgress; debug: boolean }) {
  return <Box sx={{ mt: 3, maxWidth: 720 }}>
    <Typography sx={{ fontFamily: font.body, color: color.ink, mb: 1 }}>
      {progress.completedCandidates}/{progress.totalCandidates} associazioni elaborate
    </Typography>
    <LinearProgress aria-label="Associazioni elaborate" variant="determinate"
      value={100 * progress.completedCandidates / progress.totalCandidates}
      sx={{ backgroundColor: color.stone, '& .MuiLinearProgress-bar': { backgroundColor: color.actionBlue },
        '@media (prefers-reduced-motion: reduce)': { '& .MuiLinearProgress-bar': { transition: 'none' } } }} />
    <Typography sx={{ fontFamily: font.body, color: color.body, mt: 1 }}>
      {labels[progress.phase]}
    </Typography>
    {debug && <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.muted,
      mt: 1, overflowWrap: 'anywhere' }}>
      Reader: {progress.readerCalls} chiamate · {progress.readerReuses} risposte riutilizzate
      {progress.documentId && <> · Documento: {progress.documentId}</>}
      {' · '}Candidata: {progress.candidateId}
    </Typography>}
  </Box>;
}
