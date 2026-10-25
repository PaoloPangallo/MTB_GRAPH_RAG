import { Box, Typography } from '@mui/material';
import { color } from './tokens';
import { object, readable, text } from './dossierReading';

export default function ObservedFields({ observed }: { observed: Record<string, unknown> }) {
  const context = object(observed.evidence_context);
  const subjects = Array.isArray(observed.subjects) ? observed.subjects.map(subject => {
    const item = object(subject);
    return text(item.surface_value) ?? text(item.canonical_value);
  }).filter(Boolean).join(', ') : null;
  const caveats = Array.isArray(observed.caveats) ? observed.caveats.filter(item => typeof item === 'string').join('; ') : null;
  const fields = [
    ['Intervento osservato', text(observed.intervention)], ['Biomarcatori osservati', subjects],
    ['Patologia nella fonte', text(observed.disease)], ['Popolazione o modello', readable(context.subject_level)],
    ['Classificazione generale del risultato', readable(observed.effect_direction)],
    ['Composizione molecolare', readable(observed.molecular_composition ?? observed.relation_scope)],
    ['Composizione dell’intervento', readable(observed.intervention_composition)],
    ['Incertezza dichiarata', text(observed.uncertainty)], ['Cautele nella fonte', caveats],
  ];
  return <Box component="dl" sx={{ m: 0, mt: 1, display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(140px, 190px) minmax(0, 1fr)' }, gap: 1 }}>
    {fields.map(([label, value]) => <Box key={label} sx={{ display: 'contents' }}>
      <Typography component="dt" sx={{ color: color.slate, fontSize: 14 }}>{label}</Typography>
      <Typography component="dd" sx={{ m: 0, fontSize: 15, overflowWrap: 'anywhere' }}>{value || 'Non specificato'}</Typography>
    </Box>)}
  </Box>;
}
