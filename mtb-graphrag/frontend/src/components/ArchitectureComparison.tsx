import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import PsychologyIcon from '@mui/icons-material/Psychology';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser';
import type {
  AlterationType,
  ArchitectureComparisonResponse,
  ArchitectureRun,
  ClaimCheck,
  ExecutionMode,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const palette = {
  deterministic: { main: '#176B5B', soft: '#EAF7F2', icon: <AccountTreeIcon /> },
  agentic: { main: '#7551A6', soft: '#F3EEFA', icon: <PsychologyIcon /> },
};

function statusColor(status: ClaimCheck['status']) {
  if (status === 'supported') return 'success';
  if (status === 'blocked') return 'error';
  if (status === 'insufficient') return 'warning';
  return 'default';
}

function ArchitecturePanel({ run }: { run: ArchitectureRun }) {
  const colors = palette[run.architecture_id];
  return (
    <Card variant="outlined" sx={{ height: '100%', borderTop: `5px solid ${colors.main}` }}>
      <CardContent sx={{ p: { xs: 2, md: 3 } }}>
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
          <Box sx={{ color: colors.main, display: 'flex', mt: 0.25 }}>{colors.icon}</Box>
          <Box>
            <Typography variant="h5" sx={{ color: colors.main, fontWeight: 800 }}>{run.title}</Typography>
            <Typography variant="body2" color="text.secondary">{run.subtitle}</Typography>
          </Box>
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 1, my: 2.5 }}>
          {[
            ['Tempo', `${run.metrics.elapsed_ms} ms`],
            ['Passi', run.metrics.tool_calls],
            ['Evidenze', run.metrics.evidence_count],
            ['Verificate', run.metrics.verified_claims],
            ['Bloccate', run.metrics.blocked_claims],
          ].map(([label, value]) => (
            <Box key={String(label)} sx={{ p: 1, borderRadius: 1.5, bgcolor: colors.soft, textAlign: 'center' }}>
              <Typography variant="caption" sx={{ display: 'block' }}>{label}</Typography>
              <Typography variant="subtitle2" sx={{ color: colors.main, fontWeight: 800 }}>{value}</Typography>
            </Box>
          ))}
        </Box>

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Ruolo dell'LLM</Typography>
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 2.5 }}>
          {run.llm_roles.map(role => <Chip key={role} label={role} size="small" sx={{ bgcolor: colors.soft, color: colors.main }} />)}
        </Box>

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Dietro le quinte</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.1, mb: 2.5 }}>
          {run.trace.map(step => (
            <Box key={`${step.order}-${step.stage}`} sx={{ display: 'grid', gridTemplateColumns: '28px 1fr', gap: 1.25 }}>
              <Box sx={{ width: 26, height: 26, borderRadius: '50%', bgcolor: colors.main, color: '#fff', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 800 }}>{step.order}</Box>
              <Box sx={{ pb: 1.1, borderBottom: '1px solid #E2E8F0' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>{step.stage}</Typography>
                  <Chip label={step.actor} size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />
                  {step.status !== 'completed' && <Chip label={step.status} size="small" color={step.status === 'blocked' ? 'error' : 'warning'} sx={{ height: 20, fontSize: 10 }} />}
                </Box>
                <Typography variant="body2" color="text.secondary">{step.detail}</Typography>
              </Box>
            </Box>
          ))}
        </Box>

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Evidenze e provenienza</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2.5 }}>
          {run.evidence.length === 0 ? (
            <Alert severity="warning">Nessuna evidenza disponibile per questo caso nella modalita selezionata.</Alert>
          ) : run.evidence.map((item, index) => (
            <Box key={`${item.subject}-${item.object}-${index}`} sx={{ p: 1.5, border: '1px solid #DCE5E2', borderRadius: 2, bgcolor: '#FCFEFD' }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.subject} → {item.relation} → {item.object}</Typography>
              <Typography variant="caption" sx={{ display: 'block' }}>Contesto: {item.context}</Typography>
              <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap', mt: 0.75 }}>
                {item.source_id && <Chip label={item.source_id} size="small" color="info" variant="outlined" />}
                <Typography variant="caption">{item.provenance}</Typography>
              </Box>
            </Box>
          ))}
        </Box>

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Report per l'oncologo</Typography>
        <Box sx={{ p: 2, bgcolor: '#F8FAFC', borderLeft: `4px solid ${colors.main}`, borderRadius: 1, mb: 2.5 }}>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{run.report}</Typography>
        </Box>

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Controllo delle claim</Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2.5 }}>
          {run.claim_checks.map((check, index) => (
            <Box key={`${check.claim}-${index}`} sx={{ p: 1.25, border: '1px solid #E2E8F0', borderRadius: 1.5 }}>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <Chip label={check.status} color={statusColor(check.status)} size="small" />
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{check.claim}</Typography>
                  <Typography variant="caption">{check.reason}{check.source_id ? ` · ${check.source_id}` : ''}</Typography>
                </Box>
              </Box>
            </Box>
          ))}
        </Box>

        <Alert severity="info" icon={<VerifiedUserIcon />}>
          <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>Limiti dichiarati</Typography>
          {run.limitations.map(item => <Typography key={item} variant="caption" component="div">• {item}</Typography>)}
        </Alert>
      </CardContent>
    </Card>
  );
}

export default function ArchitectureComparison() {
  const [gene, setGene] = useState('EGFR');
  const [variant, setVariant] = useState('L858R');
  const [tumorType, setTumorType] = useState('Lung Adenocarcinoma');
  const [alterationType, setAlterationType] = useState<AlterationType>('point_mutation');
  const [therapyLine, setTherapyLine] = useState('first-line');
  const [mode, setMode] = useState<ExecutionMode>('demo');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ArchitectureComparisonResponse | null>(null);

  const runComparison = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/compare-architectures`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gene,
          variant,
          tumor_type: tumorType,
          alteration_type: alterationType,
          therapy_line: therapyLine,
          enrich_with_oncokb: false,
          execution_mode: mode,
        }),
      });
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Backend ${response.status}: ${body.slice(0, 180)}`);
      }
      setData(await response.json());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Errore sconosciuto');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h1">Confronto delle due architetture</Typography>
        <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 900 }}>
          Lo stesso caso viene elaborato con un percorso tipizzato e con una raccolta agentica. La vista mostra evidenze, provenienza, ruolo dell'LLM e controlli applicati.
        </Typography>
      </Box>

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} sx={{ alignItems: 'center' }}>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}><TextField label="Gene" value={gene} onChange={event => setGene(event.target.value)} size="small" fullWidth /></Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}><TextField label="Variante" value={variant} onChange={event => setVariant(event.target.value)} size="small" fullWidth /></Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2.5 }}><TextField label="Tumore" value={tumorType} onChange={event => setTumorType(event.target.value)} size="small" fullWidth /></Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}>
              <FormControl size="small" fullWidth><InputLabel>Alterazione</InputLabel><Select value={alterationType} label="Alterazione" onChange={event => setAlterationType(event.target.value as AlterationType)}>
                <MenuItem value="point_mutation">Point mutation</MenuItem><MenuItem value="fusion">Fusion</MenuItem><MenuItem value="cna">CNA</MenuItem><MenuItem value="itd">ITD</MenuItem><MenuItem value="atypical">Atypical</MenuItem><MenuItem value="biomarker">Biomarker</MenuItem>
              </Select></FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 1.5 }}>
              <FormControl size="small" fullWidth><InputLabel>Linea</InputLabel><Select value={therapyLine} label="Linea" onChange={event => setTherapyLine(event.target.value)}>
                <MenuItem value="first-line">First line</MenuItem><MenuItem value="second-line">Second line</MenuItem><MenuItem value="later-line">Later line</MenuItem>
              </Select></FormControl>
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 2 }}>
              <FormControl size="small" fullWidth><InputLabel>Modalita</InputLabel><Select value={mode} label="Modalita" onChange={event => setMode(event.target.value as ExecutionMode)}>
                <MenuItem value="demo">Demo riproducibile</MenuItem><MenuItem value="live">Backend live</MenuItem>
              </Select></FormControl>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, alignItems: { sm: 'center' } }}>
                <Button variant="contained" startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />} onClick={runComparison} disabled={loading}>Esegui confronto</Button>
                <Typography variant="caption">La modalita demo non richiede Neo4j o LLM; la modalita live usa i servizi configurati nel backend.</Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {data && (
        <>
          <Alert severity={data.execution_mode === 'demo' ? 'warning' : 'info'} sx={{ mb: 3 }}>
            <strong>{data.case_label}</strong> — {data.disclaimer}
          </Alert>
          <Card variant="outlined" sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>Confronto della provenienza</Typography>
              <Typography variant="body2" color="text.secondary">{data.summary.explanation}</Typography>
              <Divider sx={{ my: 1.5 }} />
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip label={`Condivise: ${data.summary.shared_sources.join(', ') || 'nessuna'}`} color="success" variant="outlined" />
                <Chip label={`Solo traversal: ${data.summary.deterministic_only_sources.join(', ') || 'nessuna'}`} variant="outlined" />
                <Chip label={`Solo agentico: ${data.summary.agentic_only_sources.join(', ') || 'nessuna'}`} color="secondary" variant="outlined" />
              </Box>
            </CardContent>
          </Card>
          <Grid container spacing={3} sx={{ alignItems: 'stretch' }}>
            <Grid size={{ xs: 12, lg: 6 }}><ArchitecturePanel run={data.deterministic} /></Grid>
            <Grid size={{ xs: 12, lg: 6 }}><ArchitecturePanel run={data.agentic} /></Grid>
          </Grid>
        </>
      )}
    </Container>
  );
}
