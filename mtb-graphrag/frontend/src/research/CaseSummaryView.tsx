import { Box, Typography } from '@mui/material';
import { useState } from 'react';
import { Alert } from '@mui/material';
import { object } from './dossierReading';
import BoundedValue from './values/BoundedValue';
import StructuredValue from './values/StructuredValue';
import { color } from './tokens';
const labels: Record<string, string> = { case_id: 'Identificativo del caso', disease: 'Patologia', gene: 'Gene', variant: 'Alterazione', intervention: 'Intervento', intent: 'Intento della ricerca' };
export default function CaseSummaryView({ value }: { value?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  if (!value || !Object.keys(value).length) return <Typography variant="body2">Caso estratto non disponibile.</Typography>;
  return <Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
    <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(120px, 180px) minmax(0, 1fr)' }, gap: 1 }}>
      {Object.entries(labels).filter(([key]) => key in value).map(([key, label]) => <Box key={key} sx={{ display: 'contents' }}>
        <Typography component="dt" sx={{ color: color.slate, fontSize: 13 }}>{label}</Typography>
        <Box component="dd" sx={{ m: 0, minWidth: 0 }}>{value[key] !== null && typeof value[key] === 'object' ? <Typography variant="body2">Valore strutturato nei dettagli tecnici</Typography> : <StructuredValue value={value[key]} />}</Box>
      </Box>)}
    </Box>
    {Array.isArray(value.molecular_resolution) && value.molecular_resolution.map((raw, index) => {
      const item = object(raw);
      const partners = Array.isArray(item.fusion_partners) ? item.fusion_partners.filter(partner => typeof partner === 'string').join(' → ') : '';
      return <Alert key={index} severity={item.fusion_status === 'RESOLVED' ? 'info' : 'warning'} sx={{ mt: 1.5 }}>
        {item.fusion_status === 'RESOLVED' ? 'Profilo di fusione risolto nel registro' : 'Profilo di fusione non risolto nel registro disponibile'}: {partners || 'partner non disponibili'}.
        {item.fusion_status !== 'RESOLVED' && ' I partner dichiarati sono conservati; nessuna identità di profilo è stata attribuita.'}
      </Alert>;
    })}
    <Box component="details" onToggle={event => setOpen(event.currentTarget.open)} sx={{ mt: 2, minWidth: 0, '& summary': { cursor: 'pointer', color: color.actionBlue, fontSize: 13 } }}>
      <summary>Campi canonici e dettagli tecnici del caso</summary>
      {open && <Box sx={{ mt: 1, minWidth: 0, overflowX: 'auto' }}><BoundedValue value={value} /></Box>}
    </Box>
  </Box>;
}
