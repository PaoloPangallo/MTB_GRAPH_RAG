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
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Tab,
  Tabs,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import type { V3EvidenceRecord, V3PipelineStage, V3RetrieveResponse } from '../types';

const bucketTitles: Record<string, string> = {
  primary: 'Evidenze principali',
  warning: 'Evidenze con limitazioni',
  audit: 'Evidenze da verificare',
  rejected: 'Evidenze escluse',
};

const stageFallback: V3PipelineStage[] = [
  { id: 'clinical_input', label: 'Input clinico', status: 'completed', input_count: 1, output_count: 1, latency_ms: null, details: {} },
  { id: 'case_normalization', label: 'CaseContext normalizzato', status: 'completed', input_count: 1, output_count: 1, latency_ms: null, details: {} },
  { id: 'repository_candidates', label: 'Repository e candidati', status: 'completed', input_count: null, output_count: null, latency_ms: null, details: {} },
  { id: 'structural_gates', label: 'Gate strutturali', status: 'completed', input_count: null, output_count: null, latency_ms: null, details: {} },
  { id: 'classification_ranking', label: 'Classificazione', status: 'completed', input_count: null, output_count: null, latency_ms: null, details: {} },
  { id: 'provenance_projection', label: 'Provenance', status: 'completed', input_count: null, output_count: null, latency_ms: null, details: {} },
  { id: 'structured_dossier', label: 'Dossier strutturato', status: 'completed', input_count: null, output_count: null, latency_ms: null, details: {} },
  { id: 'optional_narration', label: 'Narrazione opzionale', status: 'not_executed', input_count: null, output_count: null, latency_ms: null, details: {} },
];

function value(value: unknown, fallback = 'non specificato'): string {
  if (value === null || value === undefined || value === '') return fallback;
  return Array.isArray(value) ? value.join(', ') : String(value);
}

function directionLabel(direction: unknown): string {
  if (direction === 'not_constrained') return 'Non vincolata dal caso';
  if (direction === 'sensitivity') return 'Sensibilità';
  if (direction === 'resistance') return 'Resistenza';
  return value(direction);
}

function comparisonLabel(result: unknown): string {
  if (result === 'not_constrained') return 'Non vincolata dal caso';
  if (result === 'exact') return 'esatto';
  if (result === true) return 'compatibile';
  if (result === false) return 'non compatibile';
  return value(result, 'non esposto');
}

function caseValue(raw: unknown, gate: string): string {
  if (Array.isArray(raw) && raw.length === 0 && gate === 'intervention') {
    return 'nessun intervento richiesto';
  }
  if (raw === '' && gate === 'direction') return 'nessuna direzione richiesta';
  return gate === 'direction' ? directionLabel(raw) : value(raw);
}

function claimTitleV3(item: V3EvidenceRecord): string {
  const claim = item.claim;
  if (claim?.claim_text || item.claim_text) return claim?.claim_text || item.claim_text || item.claim_id;
  if (
    (claim?.structured_tuple_complete || item.structured_tuple_complete)
    && (claim?.subject || item.subject)
    && (claim?.relation || item.relation)
    && (claim?.object || item.object)
  ) {
    return [
      claim?.subject || item.subject,
      claim?.relation || item.relation,
      claim?.object || item.object,
    ].join(' · ');
  }
  const biomarker = claim?.biomarker || item.biomarker;
  const direction = claim?.direction || item.direction;
  const intervention = claim?.intervention || item.intervention;
  if (biomarker || direction || intervention) {
    return [biomarker, directionLabel(direction), intervention].filter(Boolean).join(' · ');
  }
  return claimTitle(item);
}

function claimTitle(item: V3EvidenceRecord): string {
  if (item.claim_text) return item.claim_text;
  if (item.structured_tuple_complete && item.subject && item.relation && item.object) {
    return [item.subject, item.relation, item.object].join(' · ');
  }
  if (item.biomarker || item.direction || item.intervention) {
    return [item.biomarker, item.direction, item.intervention].filter(Boolean).join(' · ');
  }
  return item.claim_id;
}

function Score({ item }: { item: V3EvidenceRecord }) {
  if (item.decision) {
    const score = item.decision.structural_score;
    const shown = score === null || score === undefined
      ? 'non disponibile'
      : item.decision.structural_score_eligible === false
        ? 'Non applicabile'
        : String(score);
    return (
      <Tooltip title='Il punteggio strutturale non è una probabilità clinica.'>
        <Chip label={'Punteggio strutturale: ' + shown} size='small' variant='outlined' />
      </Tooltip>
    );
  }
  const score = item.score?.total;
  const shown = typeof score === 'number' ? String(score) : 'non disponibile';
  return (
    <Tooltip title='Punteggio strutturale nativo; non è una probabilità clinica.'>
      <Chip label={'Punteggio strutturale: ' + shown} size='small' variant='outlined' />
    </Tooltip>
  );
}

function GateTrace({ item }: { item: V3EvidenceRecord }) {
  return (
    <Box sx={{ mt: 1 }}>
      {item.gate_trace.length === 0 && <Typography variant='caption' color='text.secondary'>Gate trace non esposto.</Typography>}
      {item.gate_trace.map((trace, index) => {
        const gate = String(trace.gate || '');
        const status = String(trace.status || 'not_applicable');
        const color = status === 'pass' ? 'success' : status === 'fail' ? 'error' : status === 'warning' ? 'warning' : 'default';
        return (
          <Box key={index} sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '150px 110px 1fr' }, gap: 1, alignItems: 'center', py: 0.5 }}>
            <Typography variant='caption' sx={{ fontWeight: 700 }}>{value(trace.gate)}: {status}</Typography>
            <Chip label={status} color={color} size='small' />
            <Box>
              <Typography variant='caption'>{value(trace.message, value(trace.reason_code))}</Typography>
              <Typography variant='caption' sx={{ display: 'block' }} color='text.secondary'>Caso: {caseValue(trace.query_value_original ?? trace.case_value, gate)} / Claim: {gate === 'direction' ? directionLabel(trace.claim_value) : value(trace.claim_value)}</Typography>
              {trace.query_value_normalized !== null && trace.query_value_normalized !== undefined && String(trace.query_value_normalized) !== String(trace.query_value_original ?? trace.case_value) && (
                <Typography variant='caption' sx={{ display: 'block' }} color='text.secondary'>Normalizzato: {caseValue(trace.query_value_normalized, gate)}</Typography>
              )}
              {trace.comparison_result !== undefined && <Typography variant='caption' sx={{ display: 'block' }} color='text.secondary'>Esito: {comparisonLabel(trace.comparison_result)}</Typography>}
              {Boolean(trace.not_applicable_reason) && <Typography variant='caption' sx={{ display: 'block' }} color='text.secondary'>Stato: {String(trace.not_applicable_reason)}</Typography>}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

function applicabilityLabel(item: V3EvidenceRecord): string {
  if (item.decision) {
    return item.decision.applicability || 'Applicabilità non valutata separatamente';
  }
  return item.applicability && item.applicability !== item.bucket
    ? item.applicability
    : 'Applicabilità non valutata separatamente';
}

function ComparisonRows({ item }: { item: V3EvidenceRecord }) {
  const comparison = item.case_comparison || {};
  const labels: Record<string, string> = {
    biomarker: 'Biomarcatore',
    disease: 'Malattia',
    intervention: 'Intervento',
    formulation: 'Formulazione',
    direction: 'Direzione',
    claim_status: 'Stato claim',
    domain: 'Dominio',
  };
  return (
    <Box sx={{ mt: 1 }}>
      {Object.entries(comparison).map(([gate, raw]) => {
        if (!raw) return null;
        const row = raw;
        const reason = row.not_applicable_reason;
        return (
          <Box key={gate} sx={{ py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}>
            <Typography variant='caption' sx={{ fontWeight: 800 }}>{labels[gate] || gate}</Typography>
            <Typography variant='caption' component='div'>Caso: {caseValue(row.query_value_original, gate)} · Claim: {gate === 'direction' ? directionLabel(row.claim_value) : value(row.claim_value)}</Typography>
            {row.query_value_normalized !== null && row.query_value_normalized !== undefined && String(row.query_value_normalized) !== String(row.query_value_original) && (
              <Typography variant='caption' component='div' color='text.secondary'>Normalizzato: {caseValue(row.query_value_normalized, gate)}</Typography>
            )}
            <Typography variant='caption' component='div' color='text.secondary'>Esito: {comparisonLabel(row.comparison_result)}</Typography>
            {reason && <Typography variant='caption' component='div' color='text.secondary'>Stato: {reason}</Typography>}
          </Box>
        );
      })}
    </Box>
  );
}

function ReasonDetails({ item }: { item: V3EvidenceRecord }) {
  return (
    <Box sx={{ mt: 1 }}>
      {item.reason_codes.map(reason => (
        <Typography key={reason.code + '-' + String(reason.gate || 'structural')} variant='caption' component='div'>
          {reason.gate || 'Gate strutturale'} · {reason.code} · {reason.human_message}
        </Typography>
      ))}
    </Box>
  );
}

function EvidenceCard({ item }: { item: V3EvidenceRecord }) {
  const reason = item.reason_codes[0];
  return (
    <Card variant='outlined' sx={{ mb: 1.5 }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant='subtitle1' sx={{ fontWeight: 800, overflowWrap: 'anywhere' }}>{claimTitleV3(item)}</Typography>
            {!(item.claim?.claim_text || item.claim_text) && !(item.claim?.structured_tuple_complete || item.structured_tuple_complete) && (
              <Typography variant='caption' color='text.secondary'>Tripla strutturata non disponibile nel record sorgente</Typography>
            )}
            <Typography variant='caption' color='text.secondary'>{item.claim_id} · {value(item.evidence_type, 'record')}</Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            <Chip label={'Bucket: ' + value(item.decision?.bucket || item.bucket)} size='small' color={item.bucket === 'primary' ? 'success' : item.bucket === 'warning' ? 'warning' : 'default'} />
            <Score item={item} />
          </Box>
        </Box>
        <Typography variant='caption'><b>Biomarcatore:</b> {value(item.claim?.biomarker || item.biomarker)}</Typography>
        <Typography variant='caption' component='div'><b>Malattia:</b> {value(item.claim?.disease || item.disease)}</Typography>
        <Typography variant='caption' component='div'><b>Intervento:</b> {value(item.claim?.intervention || item.intervention)}</Typography>
        <Typography variant='caption' component='div'><b>Direzione:</b> {directionLabel(item.claim?.direction || item.direction)}</Typography>
        <Typography variant='caption' component='div'><b>Applicabilità:</b> {applicabilityLabel(item)}</Typography>
        <ComparisonRows item={item} />
        <Divider sx={{ my: 1.5 }} />
        <Typography variant='body2'><b>Motivo:</b> {reason?.human_message || 'Motivazione non esposta.'}</Typography>
        {reason && <Typography variant='caption' color='text.secondary'>Reason code: {reason.gate || 'Gate strutturale'} · {reason.code}</Typography>}
        <Accordion disableGutters elevation={0} sx={{ mt: 1, bgcolor: 'transparent' }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 32, px: 0 }}>
            <Typography variant='caption' sx={{ fontWeight: 800 }}>Gate trace e provenienza</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ px: 0 }}>
            <GateTrace item={item} />
            <ReasonDetails item={item} />
            <Divider sx={{ my: 1 }} />
            <Typography variant='caption' component='div'>Parent GraphEvidenceRecord: {value(item.parent_graph_evidence_record?.parent_id)}</Typography>
            <Typography variant='caption' component='div'>Source unit: {value(item.source_unit)}</Typography>
            <Typography variant='caption' component='div'>Stato provenance: {value(item.provenance?.status)}</Typography>
            <Typography variant='caption' component='div'>Locator: {value(item.provenance?.locator, 'nessun locator verificato')}</Typography>
          </AccordionDetails>
        </Accordion>
      </CardContent>
    </Card>
  );
}

function EvidenceSections({ data }: { data: V3RetrieveResponse }) {
  return (
    <Box>
      {(['primary', 'warning', 'audit', 'rejected'] as const).map(bucket => (
        <Box key={bucket} sx={{ mb: 2 }}>
          <Typography variant='h6' sx={{ fontWeight: 800, mb: 1 }}>{bucketTitles[bucket]} ({data.evidence[bucket].length})</Typography>
          {data.evidence[bucket].length === 0
            ? <Typography variant='caption' color='text.secondary'>Nessun claim in questa sezione.</Typography>
            : data.evidence[bucket].slice(0, 50).map(item => <EvidenceCard key={item.claim_id} item={item} />)}
        </Box>
      ))}
    </Box>
  );
}

function PipelineTab({ data }: { data: V3RetrieveResponse }) {
  const pipeline = data.pipeline;
  const stages = pipeline?.stages || stageFallback;
  const gates = pipeline?.gate_summary || [];
  return (
    <Box>
      <Stepper orientation='vertical'>
        {stages.map(stage => (
          <Step key={stage.id} active expanded>
            <StepLabel error={stage.status === 'failed'}>{stage.label}</StepLabel>
            <StepContent>
              <Typography variant='caption' color='text.secondary'>Stato: {stage.status} · input {value(stage.input_count)} · output {value(stage.output_count)} · latenza {value(stage.latency_ms, 'non misurata')}</Typography>
              {Object.entries(stage.details || {}).slice(0, 12).map(([key, item]) => (
                <Typography key={key} variant='body2'><b>{key}:</b> {value(item)}</Typography>
              ))}
            </StepContent>
          </Step>
        ))}
      </Stepper>
      <Typography variant='h6' sx={{ fontWeight: 800, mt: 2 }}>Gate strutturali</Typography>
      {gates.length === 0
        ? <Typography variant='caption' color='text.secondary'>Riepilogo gate non esposto; consultare il trace nativo delle claim.</Typography>
        : gates.map(gate => (
          <Box key={gate.gate} sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '220px repeat(4, 90px) 1fr' }, gap: 1, py: 1, borderBottom: '1px solid', borderColor: 'divider', alignItems: 'center' }}>
            <Typography variant='body2' sx={{ fontWeight: 700 }}>{gate.label}</Typography>
            <Typography variant='caption'>pass {value(gate.pass_count, '—')}</Typography>
            <Typography variant='caption'>fail {value(gate.fail_count, '—')}</Typography>
            <Typography variant='caption'>N/A {value(gate.not_applicable_count, '—')}</Typography>
            <Typography variant='caption'>warn {value(gate.warning_count, '—')}</Typography>
            <Typography variant='caption'>{gate.reason_codes.slice(0, 3).join(', ') || gate.note || 'nessun dettaglio'}</Typography>
          </Box>
        ))}
    </Box>
  );
}

function ProvenanceTab({ data }: { data: V3RetrieveResponse }) {
  const summary = data.pipeline?.provenance_summary || {};
  const statuses = Object.entries(summary);
  return (
    <Box>
      <Typography variant='body2' sx={{ mb: 2 }}>Catena verificabile: Qualified Claim → Parent GraphEvidenceRecord → Source Unit → PMID / DOI / NCT / URL / locator.</Typography>
      {statuses.length === 0 && <Typography variant='caption' color='text.secondary'>Riepilogo provenance non esposto.</Typography>}
      {statuses.map(([status, raw]) => {
        const item = raw as Record<string, unknown>;
        return <Card key={status} variant='outlined' sx={{ mb: 1.5 }}><CardContent>
          <Typography variant='subtitle1' sx={{ fontWeight: 800 }}>{value(item.label, status)} · {value(item.count, '0')}</Typography>
          <Typography variant='body2'>{value(item.explanation, 'Stato di provenance nativo.')}</Typography>
          <Typography variant='caption' color='text.secondary'>Presenti: {value(item.fields_present)} · Mancanti: {value(item.fields_missing)}</Typography>
        </CardContent></Card>;
      })}
      <Divider sx={{ my: 2 }} />
      {data.evidence.primary.slice(0, 10).map(item => <Typography key={item.claim_id} variant='caption' component='div'>Claim {item.claim_id} ↓ Parent {value(item.parent_graph_evidence_record?.parent_id)} ↓ Source {value(item.source_unit)} ↓ {value(item.provenance?.locator, 'identificatore non disponibile')}</Typography>)}
    </Box>
  );
}

function TechnicalTab({ data }: { data: V3RetrieveResponse }) {
  return <Box>
    <Alert severity='info' sx={{ mb: 2 }}>Dati tecnici e di audit — non sono evidenze cliniche.</Alert>
    {Object.entries(data.technical_records).map(([key, items]) => (
      <Accordion key={key}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}><Typography sx={{ fontWeight: 800 }}>{key} · {items.length}</Typography></AccordionSummary>
        <AccordionDetails>
          <Typography variant='caption' color='text.secondary'>Record tecnici separati dalla classificazione clinica.</Typography>
          {items.slice(0, 20).map(item => <Typography key={item.claim_id} variant='body2' component='div'>{item.claim_id} · {value(item.reason_codes?.[0]?.code, 'reason non esposto')}</Typography>)}
        </AccordionDetails>
      </Accordion>
    ))}
  </Box>;
}

function contextValue(raw: unknown): string {
  if (raw === null || raw === undefined || raw === '') return 'non specificato';
  if (Array.isArray(raw)) return raw.length === 0 ? 'nessuno' : raw.join(', ');
  if (typeof raw === 'object') {
    return Object.entries(raw as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${contextValue(item)}`)
      .join(' / ');
  }
  return String(raw);
}

function CaseContextSummary({ context }: { context: Record<string, unknown> }) {
  const original = (context.original || {}) as Record<string, unknown>;
  const normalized = Object.fromEntries(
    Object.entries(context).filter(([key]) => key !== 'original' && key !== 'gate_query'),
  );
  return (
    <Box sx={{ mb: 2, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
      <Typography variant='subtitle1' sx={{ fontWeight: 800 }}>CaseContext</Typography>
      <Typography variant='body2'><b>Originale:</b> {contextValue(original)}</Typography>
      <Typography variant='body2'><b>Normalizzato:</b> {contextValue(normalized)}</Typography>
    </Box>
  );
}

export default function V3EvidenceView({ data }: { data: V3RetrieveResponse }) {
  const [tab, setTab] = useState(0);
  const context = data.case_context || {};
  const primary = data.summary.primary;
  const status = data.metadata.status || 'completed';
  const dossier = data.pipeline?.dossier_summary || {};
  return (
    <Card variant='outlined' sx={{ borderTop: '3px solid #176B5B' }}>
      <CardContent>
        <Typography variant='h5' sx={{ fontWeight: 800, color: '#14532D' }}>MTB Evidence Retrieval V3</Typography>
        <Typography variant='body2' color='text.secondary' sx={{ mb: 2 }}>Run deterministica evidence-centric: il motore non usa planner, LLM o fonti live per classificare.</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(5, 1fr)' }, gap: 1, mb: 2 }}>
          {[
            ['Record analizzati', data.summary.total_records],
            ['Claim cliniche', data.summary.claim_records],
            ['Record tecnici', data.summary.technical_records],
            ['Primary', data.summary.primary],
            ['Warning', data.summary.warning],
            ['Audit', data.summary.audit_claims],
            ['Rejected', data.summary.rejected_claims],
            ['Latenza', value(data.metadata.latency_ms, 'N/D') + (data.metadata.latency_ms ? ' ms' : '')],
            ['Stato', status],
          ].map(([label, count]) => <Box key={String(label)} sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}><Typography variant='caption' color='text.secondary'>{String(label)}</Typography><Typography sx={{ fontWeight: 800 }}>{String(count)}</Typography></Box>)}
        </Box>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 2 }}>
          <Chip label={'query_id: ' + value(context.query_id)} size='small' />
          <Chip label={'repository: ' + value(data.metadata.repository_version)} size='small' variant='outlined' />
          <Chip label={'gate: ' + value(data.metadata.gate_version)} size='small' variant='outlined' />
          <Chip label={'backend: ' + value(data.metadata.retrieval_backend)} size='small' variant='outlined' />
        </Box>
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 2 }}>
          <Chip label={data.summary.claim_records + ' claim'} size='small' />
          <Chip label={data.summary.technical_records + ' record tecnici'} size='small' variant='outlined' />
        </Box>
        {primary === 0 && <Alert severity='info' sx={{ mb: 2 }}>Nessuna evidenza direttamente applicabile. Nessuna evidenza direttamente compatibile con il caso. Il sistema si astiene dal produrre conclusioni principali.</Alert>}
        <Tabs value={tab} onChange={(_, next) => setTab(next)} variant='scrollable' allowScrollButtonsMobile sx={{ mb: 2 }}>
          <Tab label='Dossier clinico' />
          <Tab label='Pipeline' />
          <Tab label='Evidenze' />
          <Tab label='Provenienza' />
          <Tab label='Dati tecnici' />
        </Tabs>
        {tab === 0 && <Box><Typography variant='h6' sx={{ fontWeight: 800 }}>Caso interpretato</Typography><CaseContextSummary context={context} /><Typography variant='body2' color='text.secondary' sx={{ mb: 2 }}>Dossier strutturato deterministico. Nessuna narrazione generativa è stata utilizzata.</Typography><EvidenceSections data={data} /><Typography variant='caption' color='text.secondary'>Claim nel dossier strutturato: {value(dossier.included_claims, String(primary))}.</Typography></Box>}
        {tab === 1 && <PipelineTab data={data} />}
        {tab === 2 && <EvidenceSections data={data} />}
        {tab === 3 && <ProvenanceTab data={data} />}
        {tab === 4 && <TechnicalTab data={data} />}
      </CardContent>
    </Card>
  );
}
