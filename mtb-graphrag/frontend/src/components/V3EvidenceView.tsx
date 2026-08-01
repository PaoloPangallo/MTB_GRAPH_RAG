import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import type { V3EvidenceRecord, V3RetrieveResponse } from '../types';

const bucketTitles: Record<string, string> = {
  primary: 'Evidenze principali',
  warning: 'Evidenze con limitazioni',
  audit: 'Evidenze da verificare',
  rejected: 'Evidenze escluse',
};

function EvidenceCard({ item }: { item: V3EvidenceRecord }) {
  const total = typeof item.score?.total === 'number' ? item.score.total : null;
  return (
    <Card variant="outlined" sx={{ mb: 1.5 }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'flex-start' }}>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>{item.claim_text || item.claim_id}</Typography>
            <Typography variant="caption" color="text.secondary">{item.claim_id} ? {item.evidence_type || 'record'}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <Chip label={item.bucket} size="small" color={item.bucket === 'primary' ? 'success' : item.bucket === 'warning' ? 'warning' : 'default'} />
            {total !== null && <Chip label={`Punteggio strutturale ${total}`} size="small" variant="outlined" />}
          </Box>
        </Box>
        <Grid container spacing={1} sx={{ mt: 1 }}>
          <Grid size={{ xs: 12, md: 6 }}><Typography variant="caption" component="div"><b>Biomarcatore:</b> {item.biomarker || 'N/D'}</Typography></Grid>
          <Grid size={{ xs: 12, md: 6 }}><Typography variant="caption" component="div"><b>Malattia:</b> {item.disease || 'N/D'}</Typography></Grid>
          <Grid size={{ xs: 12, md: 6 }}><Typography variant="caption" component="div"><b>Intervento:</b> {item.intervention || 'N/D'}</Typography></Grid>
          <Grid size={{ xs: 12, md: 6 }}><Typography variant="caption" component="div"><b>Direzione:</b> {item.direction || 'non specificata'}</Typography></Grid>
        </Grid>
        <Box sx={{ mt: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
          <Chip label={`Provenance: ${String(item.provenance?.status || 'N/D')}`} size="small" variant="outlined" />
          {!Boolean(item.provenance?.is_verifiable) && <Chip label="Fonte non verificabile" size="small" color="warning" variant="outlined" />}
          {item.qualifiers.map(code => <Chip key={code} label={code} size="small" variant="outlined" />)}
        </Box>
        {item.reason_codes.length > 0 && (
          <Typography variant="caption" component="div" sx={{ mt: 1 }}>
            <b>Motivazione:</b> {item.reason_codes.map(reason => `${reason.code}: ${reason.human_message}`).join(' ? ')}
          </Typography>
        )}
        <Accordion disableGutters elevation={0} sx={{ mt: 1, bgcolor: 'transparent' }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 32, px: 0 }}><Typography variant="caption" sx={{ fontWeight: 700 }}>Gate trace e provenienza</Typography></AccordionSummary>
          <AccordionDetails sx={{ px: 0 }}>
            {item.gate_trace.map((step, index) => <Typography key={`${String(step.gate)}-${index}`} variant="caption" component="div">{String(step.gate)}: {String(step.status)} ? {String(step.message)}</Typography>)}
            <Divider sx={{ my: 1 }} />
            <Typography variant="caption" component="div">Parent: {String(item.parent_graph_evidence_record?.parent_id || 'N/D')}</Typography>
            <Typography variant="caption" component="div">Locator: {String(item.provenance?.locator || 'Nessun locator')}</Typography>
          </AccordionDetails>
        </Accordion>
      </CardContent>
    </Card>
  );
}

export default function V3EvidenceView({ data }: { data: V3RetrieveResponse }) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  return (
    <Card variant="outlined" sx={{ borderTop: '3px solid #176B5B' }}>
      <CardContent>
        <Typography variant="h5" sx={{ fontWeight: 800, color: '#14532D' }}>V3 Evidence Retrieval</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Vista strutturale V3: le claim cliniche sono separate dai record tecnici di provenienza.</Typography>
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 2 }}>
          <Chip label={`${data.summary.claim_records} claim`} size="small" />
          <Chip label={`${data.summary.technical_records} record tecnici`} size="small" variant="outlined" />
          <Chip label={`${data.summary.primary} primary`} size="small" color="success" />
          <Chip label={`${data.summary.warning} warning`} size="small" color="warning" variant="outlined" />
          <Chip label={`${data.metadata.latency_ms ?? 'N/D'} ms`} size="small" variant="outlined" />
        </Box>
        {data.abstention && <Alert severity="info" sx={{ mb: 2 }}>Nessuna evidenza direttamente applicabile: il sistema si astiene dalla promozione primaria.</Alert>}
        {(['primary', 'warning', 'audit', 'rejected'] as const).map(bucket => (
          <Box key={bucket} sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 750, mb: 1 }}>{bucketTitles[bucket]} ({data.evidence[bucket].length})</Typography>
            {data.evidence[bucket].length === 0 ? <Typography variant="caption" color="text.secondary">Nessun claim in questa sezione.</Typography> : data.evidence[bucket].slice(0, 20).map(item => <EvidenceCard key={item.claim_id} item={item} />)}
          </Box>
        ))}
        <Accordion expanded={technicalOpen} onChange={(_, expanded) => setTechnicalOpen(expanded)}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography sx={{ fontWeight: 750 }}>Dati tecnici e provenienza</Typography></AccordionSummary>
          <AccordionDetails>
            {Object.entries(data.technical_records).map(([key, items]) => <Typography key={key} variant="body2" component="div" sx={{ mb: 0.5 }}>{key}: {items.length}</Typography>)}
            <Typography variant="caption" color="text.secondary">I record tecnici non vengono presentati come evidenze cliniche.</Typography>
          </AccordionDetails>
        </Accordion>
      </CardContent>
    </Card>
  );
}
