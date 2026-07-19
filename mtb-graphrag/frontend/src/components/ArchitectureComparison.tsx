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

const architectureBlueprints = {
  deterministic: {
    title: 'Traversal deterministico',
    subtitle: 'Percorso noto prima dell’esecuzione',
    llm: 'L’LLM interviene dopo il retrieval come lettore/sintetizzatore vincolato.',
    steps: [
      ['Caso MTB', 'Gene, variante, tumore e linea terapeutica.'],
      ['Normalizzazione', 'Entità e intento vengono ricondotti a forme canoniche.'],
      ['Template tipizzato', 'L’intento seleziona una traversata predefinita.'],
      ['Knowledge Graph', 'La query recupera entità, relazioni e provenienza.'],
      ['Contesto strutturato', 'I record diventano l’unico contesto ammesso.'],
      ['Sintesi vincolata', 'L’LLM verbalizza il contesto; non sceglie gli strumenti.'],
      ['Revisione oncologica', 'Il clinico verifica pertinenza e fonte.'],
    ],
  },
  agentic: {
    title: 'Architettura agentica verificabile',
    subtitle: 'Raccolta adattiva, responsabilità separate',
    llm: 'L’LLM può pianificare la raccolta; ledger, rendering e verifica restano controllati.',
    steps: [
      ['Controller di autonomia', 'Decide se il caso richiede una raccolta multi-step.'],
      ['Piano e strumenti', 'L’agente interroga iterativamente strumenti tipizzati del KG.'],
      ['Event log append-only', 'Ogni osservazione viene registrata senza riscrivere il passato.'],
      ['Vista canonica', 'Deduplica i record e conserva provenienza e conflitti.'],
      ['Proiezione pertinente', 'Ammette soltanto le evidenze necessarie al caso.'],
      ['Rendering deterministico', 'Costruisce un report candidato dai record ammessi.'],
      ['Verifica delle claim', 'Blocca, ripara o invia all’oncologo le claim non supportate.'],
      ['Narrazione opzionale', 'Un’eventuale riscrittura LLM viene verificata di nuovo.'],
      ['Revisione oncologica', 'Il clinico riceve un artefatto tracciabile e revisionabile.'],
    ],
  },
};

function statusColor(status: ClaimCheck['status']) {
  if (status === 'supported') return 'success';
  if (status === 'blocked') return 'error';
  if (status === 'insufficient') return 'warning';
  return 'default';
}

function BlueprintCard({ architecture }: { architecture: 'deterministic' | 'agentic' }) {
  const colors = palette[architecture];
  const blueprint = architectureBlueprints[architecture];
  return (
    <Card variant="outlined" sx={{ height: '100%', borderTop: `5px solid ${colors.main}` }}>
      <CardContent sx={{ p: { xs: 2, md: 3 } }}>
        <Box sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-start', mb: 2 }}>
          <Box sx={{ color: colors.main, display: 'flex', mt: 0.25 }}>{colors.icon}</Box>
          <Box>
            <Typography variant="h5" sx={{ color: colors.main, fontWeight: 800 }}>{blueprint.title}</Typography>
            <Typography variant="body2" color="text.secondary">{blueprint.subtitle}</Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
          {blueprint.steps.map(([title, detail], index) => (
            <Box key={title} sx={{ display: 'grid', gridTemplateColumns: '28px 1fr', gap: 1 }}>
              <Box sx={{ width: 24, height: 24, borderRadius: '50%', bgcolor: colors.main, color: '#fff', display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 800 }}>{index + 1}</Box>
              <Box sx={{ pb: 0.8, borderBottom: '1px solid #E2E8F0' }}>
                <Typography variant="body2" sx={{ fontWeight: 800 }}>{title}</Typography>
                <Typography variant="caption" color="text.secondary">{detail}</Typography>
              </Box>
            </Box>
          ))}
        </Box>
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="caption"><strong>Ruolo dell’LLM:</strong> {blueprint.llm}</Typography>
        </Alert>
      </CardContent>
    </Card>
  );
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

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(5, minmax(0, 1fr))' }, gap: 1, my: 2.5 }}>
          {[
            ['Tempo', `${run.metrics.elapsed_ms} ms`],
            ['Nodi/strumenti', run.metrics.tool_calls],
            ['Evidenze', run.metrics.evidence_count],
            ['Claim supportate', run.metrics.verified_claims],
            ['Claim bloccate', run.metrics.blocked_claims],
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
          {run.claim_checks.length === 0 && <Alert severity="warning">Nessuna verifica claim-by-claim disponibile.</Alert>}
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
          Lo stesso caso viene osservato attraverso le due architetture proposte nella tesi. Il confronto non cerca necessariamente fonti diverse: rende visibili responsabilità, percorso di raccolta, ruolo dell’LLM e controlli sul report destinato all’oncologo.
        </Typography>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        <strong>Come leggere il confronto.</strong> Se le fonti coincidono non significa che le architetture siano uguali: entrambe interrogano lo stesso Knowledge Graph. La differenza è nel percorso e, soprattutto, nella separazione tra raccolta dell’evidenza, rendering e verifica delle claim.
      </Alert>

      <Typography variant="h4" sx={{ mb: 1.5, fontWeight: 800 }}>Struttura proposta</Typography>
      <Grid container spacing={3} sx={{ alignItems: 'stretch', mb: 3 }}>
        <Grid size={{ xs: 12, lg: 6 }}><BlueprintCard architecture="deterministic" /></Grid>
        <Grid size={{ xs: 12, lg: 6 }}><BlueprintCard architecture="agentic" /></Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h5" sx={{ mb: 0.5, fontWeight: 800 }}>Esegui lo stesso caso</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            La demo mostra il contratto architetturale con una fault injection dichiarata. Il live usa i componenti disponibili e segnala i pezzi dell’architettura agentica ancora parziali.
          </Typography>
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
              <FormControl size="small" fullWidth><InputLabel>Modalità</InputLabel><Select value={mode} label="Modalità" onChange={event => setMode(event.target.value as ExecutionMode)}>
                <MenuItem value="demo">Contratto proposto (demo)</MenuItem><MenuItem value="live">Componenti reali (live)</MenuItem>
              </Select></FormControl>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, alignItems: { sm: 'center' } }}>
                <Button variant="contained" startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />} onClick={runComparison} disabled={loading}>Esegui confronto</Button>
                <Typography variant="caption">La modalità demo non richiede Neo4j o LLM; la modalità live usa i servizi configurati nel backend e dichiara i limiti di integrazione.</Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {data && (
        <>
          <Alert severity={data.execution_mode === 'demo' ? 'warning' : 'info'} sx={{ mb: 3 }}>
            <strong>{data.case_label}</strong> — {data.disclaimer}<br />
            <Typography variant="caption">
              {data.execution_mode === 'demo'
                ? 'Scenario sintetico dichiarato: serve a mostrare il comportamento delle due architetture e il blocco di una claim non supportata.'
                : 'Esecuzione sui componenti reali: i limiti riportati in ciascuna colonna indicano ciò che non è ancora integrato end-to-end.'}
            </Typography>
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
              {data.summary.deterministic_only_sources.length === 0 && data.summary.agentic_only_sources.length === 0 && (
                <Alert severity="success" sx={{ mt: 1.5 }}>
                  In questo caso le fonti coincidono. È un risultato plausibile: il vantaggio dell’architettura verificabile va letto nella trace e nel controllo delle claim, non nell’obbligo di produrre una risposta diversa.
                </Alert>
              )}
            </CardContent>
          </Card>
          <Typography variant="h4" sx={{ mb: 1.5, fontWeight: 800 }}>Esecuzione e controlli</Typography>
          <Grid container spacing={3} sx={{ alignItems: 'stretch' }}>
            <Grid size={{ xs: 12, lg: 6 }}><ArchitecturePanel run={data.deterministic} /></Grid>
            <Grid size={{ xs: 12, lg: 6 }}><ArchitecturePanel run={data.agentic} /></Grid>
          </Grid>
        </>
      )}
    </Container>
  );
}
