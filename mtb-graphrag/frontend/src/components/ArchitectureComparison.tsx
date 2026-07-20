import { useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import type {
  AlterationType,
  ArchitectureComparisonResponse,
  ArchitectureRun,
  ClaimCheck,
  ClinicalDossier,
  DossierEvidence,
  ExecutionMode,
} from '../types';
import { buildComparisonRequest, type ComparisonFormState } from './comparisonRequest';
import { DOSSIER_SECTION_ORDER, DOSSIER_SECTION_SEVERITY, DOSSIER_SECTION_TITLES, groupDossierEvidence } from './dossierSections';

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

const claimStatusLabels: Record<ClaimCheck['status'], string> = {
  supported: 'Supportata',
  insufficient: 'Insufficiente',
  blocked: 'Bloccata',
  not_checked: 'Non verificata',
};

const supportLabels: Record<DossierEvidence['source_support_status'], string> = {
  supported: 'Fonte: supporto documentale confermato',
  uncertain: 'Fonte: supporto documentale incerto',
  unsupported: 'Fonte: non supportata',
};

// L'etichetta per "not_compatible" deve sempre riferirsi al contesto
// dichiarato, non al paziente: una fonte può essere perfettamente valida e
// semplicemente riguardare un setting diverso da quello richiesto.
const applicabilityLabels: Record<DossierEvidence['applicability_status'], string> = {
  compatible: 'Applicabilità: compatibile con il contesto dichiarato',
  indeterminate: 'Applicabilità: indeterminata',
  not_compatible: 'Applicabilità: non compatibile con il contesto dichiarato',
};

const timingLabels: Record<string, string> = {
  retrieval: 'retrieval',
  synthesis: 'sintesi',
  dossier: 'dossier',
  collection: 'raccolta agentica',
  projection: 'proiezione',
  verification: 'verifica',
  rendering: 'rendering',
};

function formatMs(ms: number): string {
  return ms < 1 ? '<1 ms' : `${ms} ms`;
}

function DossierEvidenceList({
  title,
  items,
  severity,
}: {
  title: string;
  items: DossierEvidence[];
  severity: 'success' | 'warning' | 'error';
}) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 0.75 }}>{title} ({items.length})</Typography>
      {items.length === 0 ? (
        <Typography variant="caption" color="text.secondary">Nessun elemento in questa sezione.</Typography>
      ) : items.map(item => {
        const sourcePrerequisites = [item.source_population, item.source_line, item.source_setting, item.source_prerequisites]
          .filter(Boolean)
          .join(' · ');
        return (
          <Alert key={item.evidence_id} severity={severity} variant="outlined" sx={{ mb: 0.75, alignItems: 'flex-start' }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.therapy}</Typography>
            <Typography variant="caption" component="div">Tumore/contesto del record recuperato: {item.setting}</Typography>
            {sourcePrerequisites && (
              <Typography variant="caption" component="div">Contesto descritto dalla fonte: {sourcePrerequisites}</Typography>
            )}
            <Typography variant="caption" component="div">Supporto documentale: {item.source_support_reason}</Typography>
            <Typography variant="caption" component="div">Applicabilità al caso: {item.applicability_reason}</Typography>
            <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
              {item.source_id && <Chip label={item.source_id} size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />}
              {item.evidence_level && <Chip label={`Livello ${item.evidence_level}`} size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />}
              <Chip label={supportLabels[item.source_support_status]} size="small" sx={{ height: 20, fontSize: 10 }} />
              <Chip
                label={applicabilityLabels[item.applicability_status]}
                size="small"
                color={item.applicability_status === 'compatible' ? 'success' : item.applicability_status === 'not_compatible' ? 'error' : 'warning'}
                sx={{ height: 20, fontSize: 10 }}
              />
            </Box>
          </Alert>
        );
      })}
    </Box>
  );
}

function ClinicalDossierPanel({ dossier }: { dossier: ClinicalDossier }) {
  const grouped = groupDossierEvidence(dossier.evidence);
  return (
    <Box sx={{ mb: 2.5 }}>
      <Typography variant="overline" sx={{ fontWeight: 800 }}>Dossier per il Molecular Tumor Board</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 0.75, my: 1 }}>
        {dossier.case_summary.map(field => (
          <Box key={field.key} sx={{ p: 1, borderRadius: 1.5, bgcolor: field.confirmed ? '#F8FAFC' : '#FFF7E6', border: '1px solid #E2E8F0' }}>
            <Typography variant="caption" color="text.secondary" component="div">{field.label}</Typography>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{field.value || 'Da completare'}</Typography>
          </Box>
        ))}
      </Box>

      {dossier.missing_data.length > 0 && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          <strong>Dati mancanti:</strong> {dossier.missing_data.join(', ')}. L’applicabilità individuale non può essere chiusa senza questi elementi.
        </Alert>
      )}

      {DOSSIER_SECTION_ORDER.map(section => (
        <DossierEvidenceList
          key={section}
          title={DOSSIER_SECTION_TITLES[section]}
          items={grouped[section]}
          severity={DOSSIER_SECTION_SEVERITY[section]}
        />
      ))}

      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>Meccanismi di resistenza documentati ({dossier.resistance_findings.length})</Typography>
          {dossier.resistance_findings.length === 0 ? <Typography variant="caption">Nessun record disponibile.</Typography> : dossier.resistance_findings.map((item, index) => (
            <Box key={`${item.title}-${index}`} sx={{ mt: 0.75, p: 1, border: '1px solid #E2E8F0', borderRadius: 1.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.title}</Typography>
              <Typography variant="caption" component="div">{item.detail}</Typography>
              {item.source_id && <Chip label={item.source_id} size="small" variant="outlined" sx={{ mt: 0.5, height: 20, fontSize: 10 }} />}
            </Box>
          ))}
        </Grid>
        <Grid size={{ xs: 12, sm: 6 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>Trial da valutare per potenziale pertinenza ({dossier.trial_findings.length})</Typography>
          {dossier.trial_findings.length === 0 ? <Typography variant="caption">Nessun record disponibile.</Typography> : dossier.trial_findings.map((item, index) => (
            <Box key={`${item.title}-${index}`} sx={{ mt: 0.75, p: 1, border: '1px solid #E2E8F0', borderRadius: 1.5 }}>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.title}</Typography>
              <Typography variant="caption">{item.detail}</Typography>
              <Chip label="Eleggibilità non verificata" size="small" color="warning" variant="outlined" sx={{ display: 'flex', width: 'fit-content', mt: 0.5, height: 20, fontSize: 10 }} />
            </Box>
          ))}
        </Grid>
      </Grid>

      <Alert severity="info">
        <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>Questioni da discutere nel MTB</Typography>
        {dossier.mtb_questions.map((question, index) => <Typography key={`${question}-${index}`} variant="caption" component="div">{index + 1}. {question}</Typography>)}
      </Alert>
    </Box>
  );
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

export function ArchitecturePanel({ run }: { run: ArchitectureRun }) {
  const colors = palette[run.architecture_id];
  const isTraversal = run.architecture_id === 'deterministic';
  const metrics = run.metrics;
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

        {(run.run_id || run.planning_mode || (run.ledger_valid !== null && run.ledger_valid !== undefined)) && (
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 1.5 }}>
            {run.planning_mode && <Chip label={`Planner: ${run.planning_mode}`} size="small" variant="outlined" />}
            {run.planner_attempts != null && <Chip label={`Tentativi planner: ${run.planner_attempts}`} size="small" variant="outlined" />}
            {run.planner_elapsed_ms != null && <Chip label={`Tempo planner: ${formatMs(run.planner_elapsed_ms)}`} size="small" variant="outlined" />}
            {run.run_id && (
              <Button size="small" variant="text" href={`${API_BASE}/api/v1/agent-runs/${run.run_id}`} target="_blank" rel="noreferrer">
                Apri ledger {run.run_id.slice(0, 8)}
              </Button>
            )}
            {run.ledger_valid !== null && run.ledger_valid !== undefined && (
              <Chip label={run.ledger_valid ? 'Ledger integro' : 'Ledger non integro'} size="small" color={run.ledger_valid ? 'success' : 'error'} />
            )}
          </Box>
        )}

        {run.planning_mode === 'safe_fallback' && (
          <Alert severity="warning" icon={<WarningAmberIcon />} sx={{ mt: 1.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              Il planner LLM non ha completato un piano valido; è stato eseguito il piano sicuro predefinito.
            </Typography>
            <Typography variant="caption" component="div">
              Causa: {run.fallback_reason ?? 'non classificata'}. Questa esecuzione non dimostra pianificazione agentica dinamica.
            </Typography>
          </Alert>
        )}

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(3, minmax(0, 1fr))', md: 'repeat(4, minmax(0, 1fr))', lg: 'repeat(7, minmax(0, 1fr))' }, gap: 1, my: 2.5 }}>
          {[
            ['Tempo', formatMs(metrics.elapsed_ms)],
            ['Nodi/strumenti', metrics.tool_calls],
            ['Evidenze', metrics.evidence_count],
            ['Fonti supportate', metrics.source_supported_count ?? 0],
            ['Supporto documentale incerto', metrics.source_uncertain_count ?? 0],
            ['Fonti non supportate', metrics.source_unsupported_count ?? 0],
            ['Applicabilità compatibile', metrics.applicability_compatible_count ?? 0],
            ['Applicabilità indeterminata', metrics.applicability_indeterminate_count ?? 0],
            ['Applicabilità non compatibile', metrics.applicability_not_compatible_count ?? 0],
            ['Eventi ledger', metrics.ledger_events ?? 0],
          ].map(([label, value]) => (
            <Box key={String(label)} sx={{ p: 1, borderRadius: 1.5, bgcolor: colors.soft, textAlign: 'center' }}>
              <Typography variant="caption" sx={{ display: 'block' }}>{label}</Typography>
              <Typography variant="subtitle2" sx={{ color: colors.main, fontWeight: 800 }}>{value}</Typography>
            </Box>
          ))}
        </Box>

        {Object.keys(metrics.stage_timings_ms ?? {}).length > 0 && (
          <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: -1.5, mb: 2.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 800, alignSelf: 'center' }}>Tempi per fase:</Typography>
            {Object.entries(metrics.stage_timings_ms ?? {}).map(([stage, milliseconds]) => (
              <Chip key={stage} label={`${timingLabels[stage] ?? stage}: ${formatMs(milliseconds)}`} size="small" variant="outlined" />
            ))}
          </Box>
        )}

        <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>Ruolo dell'LLM</Typography>
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 2.5 }}>
          {run.llm_roles.map(role => <Chip key={role} label={role} size="small" sx={{ bgcolor: colors.soft, color: colors.main }} />)}
        </Box>

        <ClinicalDossierPanel dossier={run.dossier} />

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
              {item.evidence_level && <Typography variant="caption" sx={{ display: 'block' }}>Livello evidenza: {item.evidence_level}</Typography>}
              {item.evidence_statement && <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}><strong>Statement CIViC:</strong> {item.evidence_statement}</Typography>}
              <Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', flexWrap: 'wrap', mt: 0.75 }}>
                {item.source_id && <Chip label={item.source_id} size="small" color="info" variant="outlined" />}
                <Typography variant="caption">{item.provenance}</Typography>
              </Box>
            </Box>
          ))}
        </Box>

        {isTraversal ? (
          <Accordion defaultExpanded={false} disableGutters sx={{ mb: 2.5 }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>
                Output LLM non verificato — solo analisi sperimentale
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Alert severity="error" sx={{ mb: 1.5 }}>
                Questo testo può contenere formulazioni non supportate come "terapia raccomandata" o
                "trial eleggibile". Non usare come report clinico.
              </Alert>
              <Box sx={{ p: 2, bgcolor: '#F8FAFC', borderLeft: `4px solid ${colors.main}`, borderRadius: 1 }}>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{run.report}</Typography>
              </Box>
            </AccordionDetails>
          </Accordion>
        ) : (
          <>
            <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>
              Report verificato (testo) — filtrato sull'asse del supporto documentale
            </Typography>
            <Alert severity="info" sx={{ my: 1 }}>
              Questo testo riflette solo il supporto documentale delle fonti; l'applicabilità al caso è
              mostrata per ciascun elemento nel dossier sopra, che resta l'artefatto primario.
            </Alert>
            <Box sx={{ p: 2, bgcolor: '#F8FAFC', borderLeft: `4px solid ${colors.main}`, borderRadius: 1, mb: 2.5 }}>
              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{run.report}</Typography>
            </Box>
          </>
        )}

        <Accordion defaultExpanded={false} disableGutters sx={{ mb: 2.5 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box>
              <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>
                Vista tecnica: controllo del supporto documentale per fonte
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div">
                Solo asse del supporto — il dossier sopra resta la vista clinica primaria, con entrambi gli assi.
              </Typography>
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {run.claim_checks.length === 0 && <Alert severity="warning">Nessuna verifica claim-by-claim disponibile.</Alert>}
              {run.claim_checks.map((check, index) => (
                <Box key={`${check.claim}-${index}`} sx={{ p: 1.25, border: '1px solid #E2E8F0', borderRadius: 1.5 }}>
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                    <Chip label={claimStatusLabels[check.status]} color={statusColor(check.status)} size="small" />
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{check.claim}</Typography>
                      <Typography variant="caption">{check.reason}{check.source_id ? ` · ${check.source_id}` : ''}</Typography>
                      <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 0.5 }}>
                        {check.verification_level && <Chip label={`Livello: ${check.verification_level}`} size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />}
                        {check.requires_human_review && <Chip label="Revisione umana richiesta" size="small" color="warning" sx={{ height: 20, fontSize: 10 }} />}
                      </Box>
                    </Box>
                  </Box>
                </Box>
              ))}
            </Box>
          </AccordionDetails>
        </Accordion>

        {run.tool_call_timings && run.tool_call_timings.length > 0 && (
          <Accordion defaultExpanded={false} disableGutters sx={{ mb: 2.5 }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box>
                <Typography variant="overline" sx={{ color: colors.main, fontWeight: 800 }}>
                  Tempi delle chiamate agli strumenti
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  Vista tecnica separata dalle metriche cliniche sopra.
                </Typography>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                {run.tool_call_timings.map((timing, index) => (
                  <Box
                    key={`${timing.sequence}-${timing.tool}-${index}`}
                    sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', p: 1, border: '1px solid #E2E8F0', borderRadius: 1.5 }}
                  >
                    <Chip label={`#${timing.sequence}`} size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{timing.tool}</Typography>
                    <Typography variant="caption">{formatMs(timing.elapsed_ms)}</Typography>
                    <Chip
                      label={timing.status}
                      size="small"
                      color={timing.status === 'completed' ? 'success' : 'error'}
                      sx={{ height: 20, fontSize: 10 }}
                    />
                  </Box>
                ))}
              </Box>
            </AccordionDetails>
          </Accordion>
        )}

        <Alert severity="info" icon={<VerifiedUserIcon />}>
          <Typography variant="caption" component="div" sx={{ fontWeight: 700 }}>Garanzie e confini operativi</Typography>
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
  const [diseaseStage, setDiseaseStage] = useState('');
  const [diseaseSetting, setDiseaseSetting] = useState('');
  const [priorTherapies, setPriorTherapies] = useState('');
  const [priorResponse, setPriorResponse] = useState('');
  const [ecogStatus, setEcogStatus] = useState('');
  const [cnsMetastases, setCnsMetastases] = useState('');
  const [coAlterations, setCoAlterations] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [mtbGoal, setMtbGoal] = useState('general-review');
  const [mode, setMode] = useState<ExecutionMode>('demo');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ArchitectureComparisonResponse | null>(null);

  const runComparison = async () => {
    setLoading(true);
    setError(null);
    try {
      const formState: ComparisonFormState = {
        gene,
        variant,
        tumorType,
        alterationType,
        therapyLine,
        diseaseStage,
        diseaseSetting,
        priorTherapies,
        priorResponse,
        ecogStatus,
        cnsMetastases,
        coAlterations,
        jurisdiction,
        mtbGoal,
        mode,
      };
      const response = await fetch(`${API_BASE}/api/v1/compare-architectures`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildComparisonRequest(formState)),
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
            La demo mostra il contratto architetturale con una fault injection dichiarata. Il live esegue il planner a strumenti consentiti, persiste il ledger durante la raccolta e verifica ogni claim rispetto a CIViC e PubMed.
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
              <Accordion variant="outlined" disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>Contesto clinico del paziente</Typography>
                    <Typography variant="caption" color="text.secondary">I campi non compilati saranno riportati nel dossier come dati non dichiarati, non inventati dal sistema.</Typography>
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}><TextField label="Stadio" placeholder="es. IV" value={diseaseStage} onChange={event => setDiseaseStage(event.target.value)} size="small" fullWidth /></Grid>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                      <FormControl size="small" fullWidth><InputLabel>Setting di malattia</InputLabel><Select value={diseaseSetting} label="Setting di malattia" onChange={event => setDiseaseSetting(event.target.value)}>
                        <MenuItem value=""><em>Non specificato</em></MenuItem><MenuItem value="resected">Resecato</MenuItem><MenuItem value="locally-advanced">Localmente avanzato</MenuItem><MenuItem value="metastatic">Metastatico</MenuItem>
                      </Select></FormControl>
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                      <FormControl size="small" fullWidth><InputLabel>ECOG</InputLabel><Select value={ecogStatus} label="ECOG" onChange={event => setEcogStatus(event.target.value)}>
                        <MenuItem value=""><em>Non disponibile</em></MenuItem>{[0, 1, 2, 3, 4].map(value => <MenuItem key={value} value={String(value)}>{value}</MenuItem>)}
                      </Select></FormControl>
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                      <FormControl size="small" fullWidth><InputLabel>Metastasi SNC</InputLabel><Select value={cnsMetastases} label="Metastasi SNC" onChange={event => setCnsMetastases(event.target.value)}>
                        <MenuItem value=""><em>Non specificato</em></MenuItem><MenuItem value="absent">Assenti</MenuItem><MenuItem value="present">Presenti</MenuItem>
                      </Select></FormControl>
                    </Grid>
                    <Grid size={{ xs: 12, md: 6 }}><TextField label="Trattamenti precedenti" placeholder="Separati da virgola; scrivere Nessuno se confermato" value={priorTherapies} onChange={event => setPriorTherapies(event.target.value)} size="small" fullWidth /></Grid>
                    <Grid size={{ xs: 12, md: 6 }}><TextField label="Risposta o progressione precedente" value={priorResponse} onChange={event => setPriorResponse(event.target.value)} size="small" fullWidth /></Grid>
                    <Grid size={{ xs: 12, md: 6 }}><TextField label="Co-alterazioni" placeholder="Separare con virgola; scrivere Nessuna nota se confermato" value={coAlterations} onChange={event => setCoAlterations(event.target.value)} size="small" fullWidth /></Grid>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}><TextField label="Paese / contesto regolatorio" placeholder="es. Italia" value={jurisdiction} onChange={event => setJurisdiction(event.target.value)} size="small" fullWidth /></Grid>
                    <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                      <FormControl size="small" fullWidth><InputLabel>Obiettivo MTB</InputLabel><Select value={mtbGoal} label="Obiettivo MTB" onChange={event => setMtbGoal(event.target.value)}>
                        <MenuItem value="general-review">Revisione generale</MenuItem><MenuItem value="treatment-evidence">Evidenze terapeutiche</MenuItem><MenuItem value="resistance">Resistenze</MenuItem><MenuItem value="clinical-trials">Trial clinici</MenuItem>
                      </Select></FormControl>
                    </Grid>
                  </Grid>
                </AccordionDetails>
              </Accordion>
            </Grid>
            <Grid size={{ xs: 12 }}>
              <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 1.5, alignItems: { sm: 'center' } }}>
                <Button variant="contained" startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />} onClick={runComparison} disabled={loading}>Esegui confronto</Button>
                <Typography variant="caption">La modalità demo non richiede Neo4j o LLM; la modalità live richiede Neo4j, endpoint LLM e accesso a PubMed.</Typography>
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
                : 'Esecuzione sui componenti reali: planner, ledger append-only e verifica claim–fonte sono attivi; gli esiti incerti vengono inviati alla revisione umana.'}
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
