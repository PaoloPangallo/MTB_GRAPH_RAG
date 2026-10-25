import { Box, Stack, Typography } from '@mui/material';
import AccountTreeOutlinedIcon from '@mui/icons-material/AccountTreeOutlined';
import { color, font } from './tokens';

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue => value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
const records = (value: unknown): RecordValue[] => Array.isArray(value) ? value.map(record) : [];

export default function EntityResolutionTrace({ value }: { value: unknown }) {
  const trace = record(value);
  if (!trace.registry_version) return null;
  const entities = [
    ...records(trace.diseases), ...records(trace.interventions),
    ...records(trace.biomarkers).flatMap(item => [record(item.gene), record(item.variant)]),
  ].filter(item => item.raw_value);
  return <Box sx={{ mt: 2 }}>
    <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
      <AccountTreeOutlinedIcon fontSize="small" aria-hidden />
      <Typography component="h3" sx={{ fontFamily: font.body, fontSize: 16 }}>Identità dei concetti</Typography>
    </Stack>
    <Typography sx={{ fontSize: 13, color: color.muted, mb: 2 }}>
      La risoluzione identifica concetti e conserva il contesto. Autenticazione e corrispondenza documentale vengono controllate negli stage successivi.
    </Typography>
    {entities.map((item, index) => <Box key={index} sx={{ py: 1.5, borderBottom: `1px solid ${color.hairline}` }}>
      <Typography sx={{ fontSize: 14 }}>{String(item.raw_value)}</Typography>
      <Typography sx={{ fontSize: 13, color: color.slate }}>
        {item.status === 'RESOLVED' ? (Array.isArray(item.concept_ids) ? item.concept_ids.join(' · ') : '')
          : item.status === 'AMBIGUOUS' ? 'Identità ambigua: serve disambiguazione'
            : 'Concetto non risolto: copertura terminologica insufficiente'}
      </Typography>
      {Boolean(item.residual_context) && <Typography sx={{ fontSize: 12, color: color.muted }}>Contesto conservato: {String(item.residual_context)}</Typography>}
      {Array.isArray(item.reasons) && item.reasons.includes('REFERENCE_UNSPECIFIED') &&
        <Typography sx={{ fontSize: 12, color: color.muted }}>Sequenza di riferimento non specificata; identità allelica incompleta.</Typography>}
      {Array.isArray(item.reasons) && item.reasons.includes('PREDICTED_PROTEIN_CONSEQUENCE') &&
        <Typography sx={{ fontSize: 12, color: color.muted }}>Conseguenza proteica predetta.</Typography>}
    </Box>)}
    <Typography sx={{ mt: 1.5, fontFamily: font.mono, fontSize: 11, color: color.muted }}>Registry: {String(trace.registry_version)}</Typography>
  </Box>;
}
