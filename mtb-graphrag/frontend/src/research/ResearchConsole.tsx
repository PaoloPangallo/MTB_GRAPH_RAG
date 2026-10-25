import PublicationNotice from './PublicationNotice';
/**
 * Console di ispezione della pipeline verificabile.
 *
 * L'obiettivo dell'intera schermata è una sola domanda: il relatore, guardando
 * soltanto questa interfaccia, riesce a seguire un caso clinico dallo stage 1
 * al dossier e a risalire da un esito alla sua fonte?
 *
 * Per questo la pipeline è al centro e non c'è spazio per la conversazione.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Alert, Box, Chip, CircularProgress, Stack, Tab, Tabs, Tooltip, Typography } from '@mui/material';
const RunSpine = lazy(() => import('./RunSpine'));
import { STAGE_FILTERS, matchesFilter, type StageFilterKey } from './stageFilters';
const RunModeHeader = lazy(() => import('./RunModeHeader'));
const StageInspector = lazy(() => import('./StageDetail'));
import DossierView, { type Dossier } from './DossierView';
import NarrativeView, {
  type Narrative, type NarrativePresentation, type NarrativeVerification,
} from './NarrativeView';
const ProvenanceTree = lazy(() => import('./ProvenanceTree'));
const CanonicalProvenance = lazy(() => import('./CanonicalProvenance'));
const SupervisorPanel = lazy(() => import('./SupervisorPanel'));
import ArchitectureMap from './ArchitectureMap';
import CaseOverview from './CaseOverview';
import SupportSummary from './SupportSummary';
import DossierBrief from './DossierBrief';
import observedDemoCases from './observedDemoCases.json';
import { ARCHITECTURE_ROUTE, VERIFIABLE_PIPELINE_ROUTE } from '../routes';
import { Button } from '@mui/material';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import LocalHospitalOutlined from '@mui/icons-material/LocalHospitalOutlined';
import BugReportOutlined from '@mui/icons-material/BugReportOutlined';
import CaseInputPanel, { type RunRequest } from './CaseInputPanel';
import {
  createRun, getConfig, getDossier, getEvents, getMetrics, getProvenance, isRuntimeDisabled,
  listCases,
} from './api';
import { runRoute } from '../routes';
import { derivedCounts, eventsForStage, isTerminal, stageById } from './runReducer';
import { color, font, radius, runStatusStyle, reasonLabel, workspaceOffset } from './tokens';
import {
  TERM_TOOLTIPS, type DemoCase, type ProvenanceItem, type RunMetrics,
} from './types';
import { useRunStream } from './useRunStream';
import { latestWorkProgress } from './workProgress';
import WorkProgressPanel from './WorkProgressPanel';

/** Ciò che si può leggere solo a run conclusa. */
interface RunArtifacts {
  dossier: Dossier | null;
  narrative: Narrative | null;
  presentation: NarrativePresentation | null;
  presentationMode: string;
  narrativeVerification: NarrativeVerification | null;
  dossierUnavailable: string | null;
  provenance: ProvenanceItem[];
  provenanceError: string | null;
  metrics: RunMetrics | null;
  hashChainValid: boolean | null;
}

const NO_ARTIFACTS: RunArtifacts = {
  dossier: null, narrative: null, presentation: null,
  presentationMode: 'STRUCTURED_DOSSIER_FALLBACK', narrativeVerification: null,
  dossierUnavailable: null, provenance: [], provenanceError: null, metrics: null, hashChainValid: null,
};

function Notice() {
  const { runId } = useParams<{ runId: string }>();
  return (
    <Box sx={{
      backgroundColor: color.black, color: '#fff', px: 3, py: 1,
      display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap',
    }}>
      <Typography component="span" sx={{
        fontFamily: font.mono, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>
        MTB · Pipeline delle evidenze
      </Typography>
      <Typography component="span" sx={{ fontFamily: font.body, fontSize: 12, opacity: 0.85 }}>
        Componente sperimentale · non validato clinicamente · non per decisioni cliniche
      </Typography>

      <Button component={RouterLink} to={runId ? `${ARCHITECTURE_ROUTE}?run=${encodeURIComponent(runId)}` : ARCHITECTURE_ROUTE} size="small" sx={{ ml: 'auto', color: '#fff', fontSize: 12, border: '1px solid #ffffff50', px: 1.5, '&:hover': { backgroundColor: '#ffffff18' } }}>Esplora architettura</Button>
    </Box>
  );
}

export default function ResearchConsole() {
  // La run vive nell'URL, non solo nello stato del componente: un refresh
  // ricarica snapshot ed eventi dal ledger invece di riportare la pagina a
  // vuoto, e una trace resta condivisibile per link.
  const { runId: routeRunId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const debug = searchParams.get('view') === 'debug';
  const setView = (view: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('view', view);
    setSearchParams(next);
  };
  const runId = routeRunId ?? null;

  const [cases, setCases] = useState<DemoCase[]>([]);
  // La cache riguarda PAPER e TRIAL; KG_ONLY può partire anche senza documenti.
  const [documentCacheAvailable, setDocumentCacheAvailable] = useState(true);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [artifactResult, setArtifactResult] = useState<{ runId: string | null; data: RunArtifacts }>({ runId: null, data: NO_ARTIFACTS });
  const artifacts = artifactResult.runId === runId ? artifactResult.data : NO_ARTIFACTS;
  const [lowerTab, setLowerTab] = useState(0);
  const [readingChoice, setReadingChoice] = useState<{ runId: string | null; value: 'summary' | 'relations' | 'limits' }>({ runId, value: 'summary' });
  const readingTab = readingChoice.runId === runId ? readingChoice.value : 'summary';
  const [debugChoice, setDebugChoice] = useState<{ runId: string | null; value: 'architecture' | 'stages' | 'audit' }>({ runId, value: 'architecture' });
  const debugTab = debugChoice.runId === runId ? debugChoice.value : 'architecture';
  const [anchorChoice, setAnchorChoice] = useState<{ runId: string | null; target: string } | null>(null);
  const anchor = anchorChoice?.runId === runId ? anchorChoice.target : null;
  const setAnchor = (target: string | null) => setAnchorChoice(target ? { runId, target } : null);
  const [expandedExplanationsRunId, setExpandedExplanationsRunId] = useState<string | null>(null);
  const explanationsOpen = !!runId && expandedExplanationsRunId === runId;
  const [newCaseRunId, setNewCaseRunId] = useState<string | null>(null);
  const newCaseOpen = !!runId && newCaseRunId === runId;
  const navigateDossier = (target: string) => {
    setReadingChoice({ runId, value: target === 'case-narrative' ? 'summary' : target === 'dossier-limits' ? 'limits' : 'relations' });
    setAnchor(target);
  };
  useEffect(() => {
    if (!anchor) return;
    const destination = document.getElementById(anchor);
    if (destination) {
      destination.tabIndex = -1;
      destination.scrollIntoView?.({ block: 'start' });
      destination.focus({ preventScroll: true });
    }
  }, [anchor, readingTab, debugTab]);
  const [expandedTraceRunId, setExpandedTraceRunId] = useState<string | null>(null);
  const traceOpen = runId !== null && expandedTraceRunId === runId;
  const [stageFilter, setStageFilter] = useState<StageFilterKey>('all');

  const { state } = useRunStream(runId);
  const workProgress = useMemo(() => latestWorkProgress(state.events, state.run?.status),
    [state.events, state.run?.status]);
  const stages = useMemo(() => [...(state.run?.stages ?? [])].sort((a, b) => a.sequence - b.sequence), [state.run]);
  const visibleStages = useMemo(
    () => stages.filter((stage) => matchesFilter(stage, stageFilter)),
    [stages, stageFilter],
  );
  const counts = derivedCounts(state);
  const activeStageId = stages.some(stage => stage.stage_id === selectedStageId)
    ? selectedStageId : stages[0]?.stage_id ?? null;
  const selected = activeStageId ? stageById(state, activeStageId) : null;

  useEffect(() => {
    let active = true;
    listCases()
      .then((payload) => { if (active) setCases(payload.cases); })
      .catch((error: unknown) => {
        if (!active) return;
        if (isRuntimeDisabled(error)) {
          setDisabled(true);
          return;
        }
        setLoadError(error instanceof Error ? error.message : 'Impossibile leggere i casi.');
      });
    getConfig()
      .then((payload) => {
        if (!active) return;
        // Un solo runtime, dichiarato dal backend. Prima si leggeva
        // `execution_modes.live_available`, ed era da quel campo che la console
        // derivava l'esistenza di una seconda modalità.
        const runtime = payload.runtime as { available?: boolean } | undefined;
        setDocumentCacheAvailable(runtime?.available !== false);
      })
      .catch(() => { /* la disponibilità resta ottimistica: il backend rifiuta comunque */ });
    return () => { active = false; };
  }, []);

  // Dossier, provenance e metriche esistono solo a run conclusa: leggerli prima
  // darebbe un 409 o un risultato parziale che sembrerebbe definitivo.
  const terminal = state.run?.run_id === runId && isTerminal(state);
  const artifactsLoading = terminal && artifactResult.runId !== runId;

  // Il report canonico può essere presente anche per uno stop prima dello stage 13.
  const dossierStage = stages.find((stage) => stage.stage_id === 'stage_13_dossier');
  const dossierExists = dossierStage?.status === 'SUCCEEDED' || state.run?.dossier_available === true || state.run?.relation_aware_report != null;
  const noDossierReason = state.run
    ? (state.run.stopped_at === 'CALL_BUDGET_EXCEEDED' || state.run.errors?.some((error) => error.includes('CALL_BUDGET_EXCEEDED'))
      ? 'Elaborazione interrotta: è stato raggiunto il limite di chiamate al modello. Il dossier non è stato completato. Consulta la vista Debug per i dettagli.'
      : `Nessun dossier: la run è ${state.run.status}`
      + (state.run.stopped_at ? ` (${reasonLabel(state.run.stopped_at)})` : '')
    )
    : null;

  useEffect(() => {
    if (!runId || !terminal) return undefined;
    let active = true;

    void (async () => {
      const [dossier, provenance, metrics, events] = await Promise.all([
        dossierExists ? getDossier(runId).catch((error: unknown) => error) : Promise.resolve(null),
        (debug ? getProvenance(runId) : Promise.resolve({ items: [] })).catch((error: unknown) => ({
          items: [] as ProvenanceItem[],
          error: error instanceof Error ? error.message : 'Impossibile caricare la provenienza.',
        })),
        (debug ? getMetrics(runId) : Promise.resolve(null)).catch(() => null),
        (debug ? getEvents(runId, 0, 1) : Promise.resolve(null)).catch(() => null),
      ]);
      if (!active) return;

      const failed = dossier instanceof Error;
      setArtifactResult({ runId, data: {
        dossier: failed || dossier === null
          ? null
          : ((dossier as { dossier?: Dossier }).dossier ? {
            ...(dossier as { dossier: Dossier }).dossier,
            // The reading aid is a separate API projection, never part of recorded scientific facts.
            reading_guide: (dossier as Awaited<ReturnType<typeof getDossier>>).reading_guide,
          } : null),
        // Il motivo va detto invece di mostrare una sezione vuota. Quando lo
        // stage 13 non è riuscito il motivo lo danno già gli stage, quindi non
        // serve una richiesta per sentirselo ripetere.
        dossierUnavailable: failed ? (dossier as Error).message
          : dossier === null ? noDossierReason : null,
        narrative: failed || dossier === null
          ? null : ((dossier as { narrative?: Narrative | null }).narrative ?? null),
        presentation: failed || dossier === null
          ? null : ((dossier as { presentation?: NarrativePresentation | null }).presentation ?? null),
        presentationMode: failed || dossier === null
          ? 'STRUCTURED_DOSSIER_FALLBACK'
          : ((dossier as { presentation_mode?: string }).presentation_mode ?? 'STRUCTURED_DOSSIER_FALLBACK'),
        narrativeVerification: failed || dossier === null
          ? null
          : ((dossier as { narrative_verification?: NarrativeVerification | null }).narrative_verification ?? null),
        provenance: (provenance as { items: ProvenanceItem[] }).items ?? [],
        provenanceError: (provenance as { error?: string }).error ?? null,
        metrics: metrics as RunMetrics | null,
        hashChainValid: events ? events.hash_chain_valid : null,
      } });
    })();

    return () => { active = false; };
  }, [runId, terminal, dossierExists, noDossierReason, debug]);

  const start = useCallback(async (request: RunRequest) => {
    setStarting(true);
    setLoadError(null);
    setSelectedStageId(null);
    try {
      const created = await createRun(request);
      navigate(`${runRoute(created.run_id)}?view=${debug ? 'debug' : 'oncologist'}`);
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : 'Avvio non riuscito.');
    } finally {
      setStarting(false);
    }
  }, [navigate, debug]);

  if (disabled) {
    return (
      <Box sx={{ backgroundColor: color.canvas, minHeight: '100vh' }}>
        <Notice />
        <Box sx={{ maxWidth: 720, mx: 'auto', px: 3, py: 10 }}>
          <Typography sx={{
            fontFamily: font.display, fontSize: 44, lineHeight: 1.0,
            letterSpacing: '-0.02em', color: color.ink,
          }}>
            Il research runtime non è attivo.
          </Typography>
          <Typography sx={{ mt: 2, fontFamily: font.body, fontSize: 16, color: color.slate }}>
            Avvia il backend con <code>VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1</code> per ispezionare
            la pipeline. Gli endpoint di prodotto restano disponibili e invariati.
          </Typography>
        </Box>
      </Box>
    );
  }

  const runStyle = state.run ? runStatusStyle[state.run.status] : null;

  // Arresto terminale della catena documentale, distinto da uno stop corretto
  // della policy. Non apre alternative: non ne esistono.
  const ABORT_REASONS = ['DOCUMENT_CACHE_UNAVAILABLE', 'NO_DOCUMENT_RESOLVED',
                         'PARSER_FAILED', 'SOURCEUNIT_SELECTION_FAILED', 'LIVE_STAGE_FAILED', 'PROVIDER_RATE_LIMITED'];
  const pipelineAborted = state.run?.status === 'FAILED'
    && ABORT_REASONS.includes(state.run.stopped_at ?? '');

  const historicalDossier = !!artifacts.dossier && !artifacts.dossier.paper_evidence && !artifacts.dossier.clinical_trials && !artifacts.dossier.kg_only_relations;
  const criticalNotices = [...new Set(artifacts.presentation?.candidates.flatMap(entry => entry.critical_notices) ?? [])];

  const resultPanel = terminal && (
              <Box sx={{ mt: 3 }}>
                <Typography component="h2" sx={{ fontFamily: font.display, fontSize: { xs: 26, md: 34 }, lineHeight: 1.05, color: color.ink, mb: 0.75 }}>
                  {historicalDossier ? 'Dossier storico' : artifacts.dossier ? debug ? 'Dossier e controlli' : readingTab === 'summary' ? 'Dossier canonico' : readingTab === 'relations' ? 'Relazioni e fonti' : 'Limiti del dossier' : 'Esito della run'}
                </Typography>
                {!artifacts.dossier && <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.slate, maxWidth: '68ch', mb: 2.5 }}>
                  Relazioni, fonti e limitazioni del dossier canonico, con la spiegazione narrativa disponibile quando verificata.
                </Typography>}
                {artifactsLoading ? <Typography role="status">Caricamento del dossier canonico…</Typography> : artifacts.dossierUnavailable
                  ? <Alert severity="info" sx={{ borderRadius: `${radius.sm}px` }}>{artifacts.dossierUnavailable}</Alert>
                  : historicalDossier ? <DossierView dossier={artifacts.dossier} debug={debug} /> : <>{!debug && <Tabs value={readingTab} onChange={(_, value: 'summary' | 'relations' | 'limits') => { setReadingChoice({ runId, value }); setAnchor(null); }} aria-label="Consultazione del dossier" variant="scrollable" scrollButtons="auto" sx={{ mb: 2 }}>
                      <Tab value="summary" label="Sintesi" id="reading-summary" aria-controls="reading-panel-summary" />
                      <Tab value="relations" label="Relazioni" id="reading-relations" aria-controls="reading-panel-relations" />
                      <Tab value="limits" label="Limiti" id="reading-limits" aria-controls="reading-panel-limits" />
                    </Tabs>}
                    {!debug && readingTab === 'summary' && artifacts.dossier && <PublicationNotice dossier={artifacts.dossier} />}
                    {!debug && criticalNotices.length > 0 && <Alert severity="warning" sx={{ mb: 1 }}><Box component="ul" sx={{ m: 0, pl: 2 }}>{criticalNotices.map(notice => <li key={notice}>{reasonLabel(notice)}</li>)}</Box></Alert>}
                    {!debug && artifacts.dossier?.paper_evidence?.some(entry => entry.contradiction_present || entry.support_level === 'CONTRADICTORY') && <Alert severity="warning" sx={{ mb: 2 }}>Il dossier contiene evidenze in conflitto.</Alert>}
                    {!debug && !!artifacts.dossier?.limitations?.length && <Button onClick={() => navigateDossier('dossier-limits')} sx={{ mb: 1 }}>Limiti del dossier ({artifacts.dossier.limitations.length})</Button>}
                    <Box role={!debug ? 'tabpanel' : undefined} id={!debug ? `reading-panel-${readingTab}` : undefined} aria-labelledby={!debug ? `reading-${readingTab}` : undefined}>
                    {!debug && readingTab === 'summary' && artifacts.dossier && <><CaseOverview dossier={artifacts.dossier} onNavigate={navigateDossier} /><SupportSummary dossier={artifacts.dossier} /><DossierBrief dossier={artifacts.dossier} onNavigate={navigateDossier} /></>}
                    {(debug || readingTab === 'summary') && <Box id="case-narrative" sx={{ scrollMarginTop: `${workspaceOffset}px` }}><NarrativeView compact showCriticalNotices={debug} narrative={artifacts.narrative}
                                   presentation={artifacts.presentation}
                                   presentationMode={artifacts.presentationMode}
                                   verification={artifacts.narrativeVerification} /></Box>}
                    {(debug || readingTab !== 'summary') && <DossierView dossier={artifacts.dossier} debug={debug} section={debug ? 'all' : readingTab === 'limits' ? 'limits' : 'relations'} />}
                    {!debug && readingTab === 'relations' && <Box component="details" open={explanationsOpen} onToggle={event => setExpandedExplanationsRunId(event.currentTarget.open ? runId : null)} sx={{ mt: 3 }}>
                      <summary>Spiegazioni delle relazioni</summary>
                      {explanationsOpen && <NarrativeView showCriticalNotices={false} narrative={artifacts.narrative} presentation={artifacts.presentation} presentationMode={artifacts.presentationMode} verification={artifacts.narrativeVerification} />}
                    </Box>}
                    </Box></>}
              </Box>
            );

  return (
    <Box sx={{ backgroundColor: color.canvas, minHeight: '100vh' }}>
      <Notice />

      <Box sx={{ maxWidth: debug ? 1440 : 1160, minWidth: 0, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 3, md: runId ? 2 : 4 } }}>
        {runId && <Button startIcon={<ArrowBackOutlined />} onClick={() => navigate(`${VERIFIABLE_PIPELINE_ROUTE}?view=${debug ? 'debug' : 'oncologist'}`)} sx={{ mb: 2, textTransform: 'none' }}>Nuovo caso</Button>}
        <Typography component="h1" sx={{
          fontFamily: font.display, fontSize: { xs: 28, md: runId ? 30 : 38 }, lineHeight: 1.15,
          letterSpacing: '-0.03em', color: color.ink, maxWidth: 900,
        }}>
          {debug ? 'Pipeline e verifiche' : runId ? 'Dossier del caso' : 'Dal testo clinico al dossier delle evidenze.'}
        </Typography>
        {!runId && <Typography sx={{
          mt: 2, fontFamily: font.body, fontSize: 15, color: color.slate, maxWidth: 680,
        }}>
          Il caso viene estratto e verificato prima del retrieval. Le relazioni seguono
          tre percorsi: pubblicazioni, studi clinici e Knowledge Graph.
          Il sistema non formula raccomandazioni cliniche.
        </Typography>}

        <Tabs aria-label="Vista della run" value={debug ? 'debug' : 'oncologist'}
          variant="scrollable" scrollButtons="auto"
          onChange={(_, view: string) => setView(view)}
          sx={{ mt: 2, position: 'sticky', top: 0, zIndex: 2, backgroundColor: color.canvas, borderBottom: `1px solid ${color.hairline}` }}>
          <Tab value="oncologist" label="Oncologo" icon={<LocalHospitalOutlined />} iconPosition="start" id="view-oncologist" aria-controls="workspace-oncologist" />
          <Tab value="debug" label="Debug" icon={<BugReportOutlined />} iconPosition="start" id="view-debug" aria-controls="workspace-debug" />
        </Tabs>
        <Box role="tabpanel" id={debug ? 'workspace-debug' : 'workspace-oncologist'} aria-labelledby={debug ? 'view-debug' : 'view-oncologist'}>
        {!runId && <Typography sx={{ mt: 1.5, color: color.slate, fontSize: 14 }}>
          {debug ? 'Ispeziona stage, eventi e controlli della pipeline.' : 'Consulta il caso, le evidenze e i limiti del dossier.'}
        </Typography>}

        {/* L'ingresso è il testo libero. I casi dimostrativi lo compilano, non
            lo scavalcano: il parser resta sul percorso principale. */}
        <Box component={runId ? 'details' : 'div'} open={runId ? newCaseOpen : undefined} onToggle={(event: React.SyntheticEvent<HTMLDetailsElement>) => setNewCaseRunId(event.currentTarget.open ? runId : null)} sx={{ mt: 2, '& summary': { cursor: 'pointer', color: color.actionBlue, py: 1 } }}>
          {runId && <summary>Avvia un nuovo caso</summary>}
        {(!runId || newCaseOpen) && <CaseInputPanel
          cases={cases}
          busy={starting}
          documentCacheAvailable={documentCacheAvailable}
          onRun={(request) => void start(request)}
        />}
        </Box>

        {loadError && (
          <Alert severity="error" sx={{ mt: 3, borderRadius: '8px' }}>
            {loadError} La console non mostra risultati quando il backend non risponde.
          </Alert>
        )}

        {state.error && (
          <Alert severity="error" sx={{ mt: 3, borderRadius: '8px' }}>{state.error}</Alert>
        )}

        {runId && (
          <Box sx={{ mt: 2 }}>
            {/* Intestazione della run */}
            <Box sx={{
              display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'baseline',
              pb: 2, borderBottom: `1px solid ${color.hairline}`,
            }}>
              <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.muted }}>
                {!debug ? observedDemoCases.cases.find(example => example.case_id === state.run?.case_id)?.title ?? state.run?.case_id ?? runId : state.run?.case_id ?? runId}
              </Typography>
              {runStyle && (
                <Tooltip title={state.run?.status === 'STOPPED' ? TERM_TOOLTIPS.stopped : ''}>
                  <Typography sx={{ fontFamily: font.body, fontSize: 14, color: runStyle.fg }}>
                    <Box component="span" sx={{ display: 'inline-block', bgcolor: runStyle.bg, px: 1.5, py: 0.75, borderRadius: '6px', fontWeight: 600 }}>{runStyle.label}</Box>
                  </Typography>
                </Tooltip>
              )}
              {state.run?.stopped_at && (
                <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.slate }}>
                  {reasonLabel(state.run.stopped_at)}
                </Typography>
              )}
              {debug && <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                {counts.succeeded}/{counts.total} stage · {state.events.length} eventi
              </Typography>}
              {state.run?.started_at && (
                <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                  {new Date(state.run.started_at).toLocaleString('it-IT')}
                </Typography>
              )}
              <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                {debug ? `run ${runId.slice(0, 8)}` : 'Dossier del caso'}
              </Typography>
              {state.connection === 'connecting' && (
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <CircularProgress size={12} sx={{ color: color.actionBlue }} />
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.actionBlue }}>
                    in ascolto
                  </Typography>
                </Stack>
              )}
            </Box>

            {/* Acquisizione documentale, cache, chiamate al modello ed eventuale
                arresto: prima di tutto il resto, perché determinano come va letto
                tutto il resto. */}
            <Box sx={{ mt: 3 }}>
              {workProgress && <WorkProgressPanel progress={workProgress} debug={debug} />}
              {debug && <Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><RunModeHeader run={state.run} /></Suspense>}

              {/* Un arresto della catena documentale si dichiara e basta. Qui
                  compariva un'azione che apriva la run registrata equivalente:
                  era esplicita e non sostituiva nulla in automatico, ma restava
                  un percorso storico offerto al clinico come alternativa
                  operativa. Non lo è, e non deve sembrarlo. */}
              {pipelineAborted && (
                <Alert
                  severity="error"
                  data-testid="pipeline-abort-alert"
                  sx={{ borderRadius: '8px', mb: 3 }}
                >
                  <Typography sx={{ fontFamily: font.body, fontSize: 13 }}>
                    {reasonLabel(state.run?.stopped_at ?? 'LIVE_STAGE_FAILED')}.
                    {' '}Gli stage eseguiti restano visibili; nessun artefatto registrato
                    li ha sostituiti.
                  </Typography>
                </Alert>
              )}
            </Box>

            {debug && <Tabs value={debugTab} onChange={(_, value: 'architecture' | 'stages' | 'audit') => setDebugChoice({ runId, value })} aria-label="Ispezione della pipeline" variant="scrollable" scrollButtons="auto">
              <Tab value="architecture" label="Architettura" id="debug-architecture" aria-controls="debug-panel-architecture" />
              <Tab value="stages" label="Stage" id="debug-stages" aria-controls="debug-panel-stages" />
              <Tab value="audit" label="Audit" id="debug-audit" aria-controls="debug-panel-audit" />
            </Tabs>}
            {debug && debugTab === 'architecture' && <Box role="tabpanel" id="debug-panel-architecture" aria-labelledby="debug-architecture"><ArchitectureMap stages={stages} selectedStageId={activeStageId} onSelect={id => { setSelectedStageId(id); setDebugChoice({ runId, value: 'stages' }); setAnchor('stage-inspector'); }} /></Box>}
            {!debug && state.run?.input_text && <Box component="details" sx={{ mt: 2, maxWidth: '72ch', '& summary': { cursor: 'pointer', fontWeight: 600 } }}>
              <summary>Caso in esame · testo originale</summary>
              <Typography sx={{ lineHeight: 1.7, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{state.run.input_text}</Typography>
            </Box>}
            {!debug && !terminal && <Box role="status" sx={{ py: 4 }}>
              <Typography component="h2" sx={{ fontSize: 22, mb: 1 }}>Preparazione del dossier</Typography>
              <Typography sx={{ color: color.slate }}>Il caso e le fonti sono in elaborazione. Il dossier sarà disponibile al termine.</Typography>
            </Box>}
            {!debug && resultPanel}

            {/* Spina a sinistra, ispezione a destra. */}
            {debug && debugTab === 'stages' && <Box role="tabpanel" id="debug-panel-stages" aria-labelledby="debug-stages" sx={{
              display: 'grid', gap: 3, mt: 3,
              gridTemplateColumns: { xs: '1fr', lg: 'minmax(320px, 400px) 1fr' },
            }}>
              <Box>
                <Stack
                  direction="row"
                  spacing={0.75}
                  role="group"
                  aria-label="Filtro degli stage"
                  sx={{ flexWrap: 'wrap', rowGap: 0.75, mb: 1.5 }}
                >
                  {STAGE_FILTERS.map((option) => (
                    <Chip
                      key={option.key}
                      label={option.label}
                      size="small"
                      onClick={() => setStageFilter(option.key)}
                      aria-pressed={stageFilter === option.key}
                      data-testid={`stage-filter-${option.key}`}
                      sx={{
                        height: 24, fontFamily: font.mono, fontSize: 10, cursor: 'pointer',
                        borderRadius: '6px',
                        backgroundColor: stageFilter === option.key ? color.ink : color.stone,
                        color: stageFilter === option.key ? '#fff' : color.body,
                      }}
                    />
                  ))}
                </Stack>
                {visibleStages.length === 0 ? (
                  <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.muted, py: 2 }}>
                    Nessuno stage corrisponde a questo filtro.
                  </Typography>
                ) : (
                  <Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><RunSpine
                    stages={visibleStages}
                    selectedStageId={activeStageId}
                    onSelect={setSelectedStageId}
                  /></Suspense>
                )}
              </Box>
              <Box id="stage-inspector" sx={{
                border: `1px solid ${color.borderLight}`, scrollMarginTop: `${workspaceOffset}px`, borderRadius: `${radius.md}px`,
                minHeight: 400, alignSelf: 'start',
              }}>
                <Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><StageInspector
                  runId={runId}
                  stage={selected}
                  events={activeStageId ? eventsForStage(state, activeStageId) : []}
                  clinicalText={state.run?.input_text}
                /></Suspense>
              </Box>
            </Box>}

            {debug && debugTab === 'audit' && terminal && (
              <Box role="tabpanel" id="debug-panel-audit" aria-labelledby="debug-audit" sx={{ mt: 3 }}>
                <Tabs
                  aria-label="Audit della run"
                  value={lowerTab}
                  onChange={(_, next: number) => setLowerTab(next)}
                  sx={{ borderBottom: `1px solid ${color.hairline}`, minHeight: 44 }}
                >
                  <Tab id="audit-tab-0" aria-controls="audit-panel-0" label="Provenienza" />
                  <Tab id="audit-tab-1" aria-controls="audit-panel-1" label="Metriche e integrità" />
                </Tabs>

                <Box role="tabpanel" id={`audit-panel-${lowerTab}`} aria-labelledby={`audit-tab-${lowerTab}`} sx={{ pt: 3 }}>
                  {lowerTab === 0 && <><Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><CanonicalProvenance dossier={artifacts.dossier} /></Suspense>
                    <Box component="details" open={traceOpen}
                      onToggle={(event) => setExpandedTraceRunId(event.currentTarget.open ? runId : null)} sx={{ mt: 3 }}>
                      <summary>Trace degli stage e classificazioni interne</summary>
                      <Typography variant="body2" sx={{ my: 2 }}>Questa trace dell’API descrive i controlli degli stage; i bucket interni non sostituiscono le osservazioni e i controlli del dossier canonico.</Typography>
                      {traceOpen && <Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><ProvenanceTree items={artifacts.provenance} error={artifacts.provenanceError} /></Suspense>}
                    </Box></>}
                  {lowerTab === 1 && (
                    <Suspense fallback={<Typography role="status">Caricamento dettagli…</Typography>}><SupervisorPanel
                      metrics={artifacts.metrics}
                      events={state.events}
                      hashChainValid={artifacts.hashChainValid}
                      versions={state.run?.versions ?? {}}
                    /></Suspense>
                  )}
                </Box>
              </Box>
            )}
            {debug && debugTab === 'audit' && resultPanel}
            {debug && debugTab === 'audit' && !terminal && <Typography role="status" sx={{ mt: 3 }}>L'audit completo sarà disponibile al termine della run.</Typography>}
          </Box>
        )}
        </Box>
      </Box>
    </Box>
  );
}
