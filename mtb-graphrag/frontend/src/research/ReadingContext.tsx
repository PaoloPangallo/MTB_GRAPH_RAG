import { Box, Typography } from '@mui/material';
import type { ReadingFinding } from './contracts.generated';
import { color } from './tokens';

/** Display the backend's reading aid; never derive clinical equivalence here. */
export default function ReadingContext({ reading }: { reading?: ReadingFinding }) {
  if (!reading) return <Typography variant="body2" sx={{ mt: 1.5, color: color.slate }}>
    Confronto con il caso non disponibile per questa versione. Verificare patologia, intervento ed endpoint nella fonte; una categoria generale del risultato non misura il beneficio clinico.
  </Typography>;
  const rows = [
    ['Patologia richiesta', reading.requested_disease], ['Patologia estratta dalla fonte', reading.observed_disease],
    ['Intervento richiesto', reading.requested_intervention], ['Intervento estratto dalla fonte', reading.observed_intervention],
  ];
  return <Box component="section" aria-label="Confronto con il caso" sx={{ mt: 2, maxWidth: '75ch' }}>
    <Typography component="h5" sx={{ fontSize: 16, fontWeight: 600 }}>Confronto con il caso</Typography>
    <Box component="dl" sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(140px, 190px) minmax(0, 1fr)' }, gap: 1, my: 1 }}>
      {rows.map(([label, value]) => <Box key={label} sx={{ display: 'contents' }}>
        <Typography component="dt" sx={{ fontSize: 14, color: color.slate }}>{label}</Typography>
        <Typography component="dd" sx={{ m: 0, fontSize: 15, overflowWrap: 'anywhere' }}>{value || 'Non registrato'}</Typography>
      </Box>)}
    </Box>
    {!!reading.notices.length && <Box component="ul" aria-label="Aspetti da verificare" sx={{ pl: 2.5, mt: 1, mb: 0 }}>
      {reading.notices.map(notice => <Typography component="li" key={notice.code} sx={{ fontSize: 14, lineHeight: 1.6, mb: 1 }}>{notice.message}</Typography>)}
    </Box>}
  </Box>;
}
