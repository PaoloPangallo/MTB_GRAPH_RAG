/**
 * Console di ispezione della pipeline verificabile.
 *
 * L'obiettivo dell'intera schermata è una sola domanda: il relatore, guardando
 * soltanto questa interfaccia, riesce a seguire un caso clinico dallo stage 1
 * al dossier e a risalire da un esito alla sua fonte?
 *
 * Per questo la pipeline è al centro e non c'è spazio per la conversazione.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { Alert, Box, Button, Chip, CircularProgress, Stack, Tab, Tabs, Tooltip, Typography } from '@mui/material';
import RunSpine, { STAGE_FILTERS, matchesFilter, type StageFilterKey } from './RunSpine';
import RunModeHeader from './RunModeHeader';
import StageInspector from './StageInspector';
import DossierView, { type Dossier } from './DossierView';
import ProvenanceTree from './ProvenanceTree';
import SupervisorPanel from './SupervisorPanel';
import CaseInputPanel, { type RunRequest } from './CaseInputPanel';
import {
  createRun, getConfig, getDossier, getEvents, getMetrics, getProvenance, isRuntimeDisabled,
  listCases,
} from './api';
import { LEGACY_V3_ROUTE, runRoute } from '../routes';
import { derivedCounts, eventsForStage, isTerminal, stageById, stagesInOrder } from './runReducer';
import { color, font, radius, runStatusStyle, reasonLabel } from './tokens';
import {
  TERM_TOOLTIPS, type DemoCase, type ProvenanceItem, type RunMetrics,
} from './types';
import { useRunStream } from './useRunStream';

/** Ciò che si può leggere solo a run conclusa. */
interface RunArtifacts {
  dossier: Dossier | null;
  dossierUnavailable: string | null;
  provenance: ProvenanceItem[];
  metrics: RunMetrics | null;
  hashChainValid: boolean | null;
}

const NO_ARTIFACTS: RunArtifacts = {
  dossier: null, dossierUnavailable: null, provenance: [], metrics: null, hashChainValid: null,
};

function Notice() {
  return (
    <Box sx={{
      backgroundColor: color.black, color: '#fff', px: 3, py: 1,
      display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap',
    }}>
      <Typography component="span" sx={{
        fontFamily: font.mono, fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>
        Verifiable research pipeline
      </Typography>
      <Typography component="span" sx={{ fontFamily: font.body, fontSize: 12, opacity: 0.85 }}>
        Componente sperimentale · non validato clinicamente · non per decisioni cliniche
      </Typography>
      <Button
        component={RouterLink}
        to={LEGACY_V3_ROUTE}
        size="small"
        sx={{
          ml: 'auto', color: 'rgba(255,255,255,0.6)', textTransform: 'none',
          fontSize: 11, fontFamily: font.mono,
        }}
      >
        Legacy V3 →
      </Button>
    </Box>
  );
}

export default function ResearchConsole() {
  // La run vive nell'URL, non solo nello stato del componente: un refresh
  // ricarica snapshot ed eventi dal ledger invece di riportare la pagina a
  // vuoto, e una trace resta condivisibile per link.
  const { runId: routeRunId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const runId = routeRunId ?? null;

  const [cases, setCases] = useState<DemoCase[]>([]);
  // Se la cache documentale manca, LIVE non è eseguibile: va detto **prima**
  // di premere, non scoperto da una run fallita.
  const [liveAvailable, setLiveAvailable] = useState(true);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [artifacts, setArtifacts] = useState<RunArtifacts>(NO_ARTIFACTS);
  const [lowerTab, setLowerTab] = useState(0);
  const [stageFilter, setStageFilter] = useState<StageFilterKey>('all');

  const { state } = useRunStream(runId);
  const stages = stagesInOrder(state);
  const visibleStages = useMemo(
    () => stages.filter((stage) => matchesFilter(stage, stageFilter)),
    [stages, stageFilter],
  );
  const counts = derivedCounts(state);
  const selected = selectedStageId ? stageById(state, selectedStageId) : null;

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
        const modes = payload.execution_modes as { live_available?: boolean } | undefined;
        setLiveAvailable(modes?.live_available !== false);
      })
      .catch(() => { /* la disponibilità resta ottimistica: il backend rifiuta comunque */ });
    return () => { active = false; };
  }, []);

  // Alla prima comparsa degli stage si apre il primo, così l'inspector non
  // resta vuoto senza motivo.
  useEffect(() => {
    if (!selectedStageId && stages.length > 0) setSelectedStageId(stages[0].stage_id);
  }, [stages, selectedStageId]);

  // Dossier, provenance e metriche esistono solo a run conclusa: leggerli prima
  // darebbe un 409 o un risultato parziale che sembrerebbe definitivo.
  const terminal = isTerminal(state);

  // Una run fermata prima dello stage 13 **non ha** un dossier, e lo si sa dagli
  // stage senza chiederlo. Richiederlo comunque otteneva un 409 corretto ma
  // faceva comparire un errore rosso nella console del browser per un esito
  // previsto — indistinguibile, per chi guarda, da un guasto vero.
  const dossierStage = stages.find((stage) => stage.stage_id === 'stage_13_dossier');
  const dossierExists = dossierStage?.status === 'SUCCEEDED';
  const noDossierReason = state.run
    ? `Nessun dossier: la run è ${state.run.status}`
      + (state.run.stopped_at ? ` (${reasonLabel(state.run.stopped_at)})` : '')
    : null;

  useEffect(() => {
    if (!runId || !terminal) return undefined;
    let active = true;

    void (async () => {
      const [dossier, provenance, metrics, events] = await Promise.all([
        dossierExists ? getDossier(runId).catch((error: unknown) => error) : Promise.resolve(null),
        getProvenance(runId).catch(() => ({ items: [] as ProvenanceItem[] })),
        getMetrics(runId).catch(() => null),
        getEvents(runId).catch(() => null),
      ]);
      if (!active) return;

      const failed = dossier instanceof Error;
      setArtifacts({
        dossier: failed || dossier === null
          ? null
          : ((dossier as { dossier?: Dossier }).dossier ?? null),
        // Il motivo va detto invece di mostrare una sezione vuota. Quando lo
        // stage 13 non è riuscito il motivo lo danno già gli stage, quindi non
        // serve una richiesta per sentirselo ripetere.
        dossierUnavailable: failed ? (dossier as Error).message
          : dossier === null ? noDossierReason : null,
        provenance: (provenance as { items: ProvenanceItem[] }).items ?? [],
        metrics: metrics as RunMetrics | null,
        hashChainValid: events ? events.hash_chain_valid : null,
      });
    })();

    return () => { active = false; };
  }, [runId, terminal, dossierExists, noDossierReason]);

  const start = useCallback(async (request: RunRequest) => {
    setStarting(true);
    setLoadError(null);
    setSelectedStageId(null);
    setArtifacts(NO_ARTIFACTS);
    try {
      const created = await createRun(request);
      navigate(runRoute(created.run_id));
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : 'Avvio non riuscito.');
    } finally {
      setStarting(false);
    }
  }, [navigate]);

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

  // Un guasto della modalità live, distinto da un arresto corretto: solo il
  // primo giustifica di proporre la run registrata come lettura alternativa.
  const LIVE_FAILURES = ['DOCUMENT_CACHE_UNAVAILABLE', 'NO_DOCUMENT_RESOLVED', 'LIVE_STAGE_FAILED'];
  const liveFailed = state.run?.status === 'FAILED'
    && LIVE_FAILURES.includes(state.run.stopped_at ?? '');
  const equivalentReplay = cases.find(
    (demo) => demo.case_id === state.run?.case_id && demo.frozen_artifacts_available,
  ) ?? null;

  return (
    <Box sx={{ backgroundColor: color.canvas, minHeight: '100vh' }}>
      <Notice />

      <Box sx={{ maxWidth: 1440, mx: 'auto', px: { xs: 2, md: 4 }, py: { xs: 4, md: 6 } }}>
        <Typography component="h1" sx={{
          fontFamily: font.display, fontSize: { xs: 36, md: 56 }, lineHeight: 0.98,
          letterSpacing: '-0.03em', color: color.ink, maxWidth: 900,
        }}>
          Dal testo clinico al dossier, uno stage alla volta.
        </Typography>
        <Typography sx={{
          mt: 2, fontFamily: font.body, fontSize: 17, color: color.slate, maxWidth: 680,
        }}>
          Ogni risultato dichiara chi lo ha prodotto, quanto è durato e su quale fonte poggia.
          Il sistema non formula raccomandazioni cliniche.
        </Typography>

        {/* L'ingresso è il testo libero. I casi dimostrativi lo compilano, non
            lo scavalcano: il parser resta sul percorso principale. */}
        <CaseInputPanel
          cases={cases}
          busy={starting}
          liveAvailable={liveAvailable}
          onRun={(request) => void start(request)}
        />

        {loadError && (
          <Alert severity="error" sx={{ mt: 3, borderRadius: '8px' }}>
            {loadError} La console non mostra risultati quando il backend non risponde.
          </Alert>
        )}

        {state.error && (
          <Alert severity="error" sx={{ mt: 3, borderRadius: '8px' }}>{state.error}</Alert>
        )}

        {runId && (
          <Box sx={{ mt: 5 }}>
            {/* Intestazione della run */}
            <Box sx={{
              display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'baseline',
              pb: 2, borderBottom: `1px solid ${color.hairline}`,
            }}>
              <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.muted }}>
                {state.run?.case_id ?? runId}
              </Typography>
              {runStyle && (
                <Tooltip title={state.run?.status === 'STOPPED' ? TERM_TOOLTIPS.stopped : ''}>
                  <Typography sx={{ fontFamily: font.body, fontSize: 14, color: runStyle.fg }}>
                    {runStyle.label}
                  </Typography>
                </Tooltip>
              )}
              {state.run?.stopped_at && (
                <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.slate }}>
                  {reasonLabel(state.run.stopped_at)}
                </Typography>
              )}
              <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                {counts.succeeded}/{counts.total} stage · {state.events.length} eventi
              </Typography>
              {state.run?.started_at && (
                <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                  {new Date(state.run.started_at).toLocaleString('it-IT')}
                </Typography>
              )}
              <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                run {runId.slice(0, 8)}
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

            {/* Modalità, cache, chiamate e artefatti rigiocati: prima di tutto
                il resto, perché determinano come va letto tutto il resto. */}
            <Box sx={{ mt: 3 }}>
              <RunModeHeader run={state.run} />

              {/* Una run live fallita **non** viene sostituita dalla run
                  registrata: quella resta consultabile con un gesto separato ed
                  esplicito, che apre una run distinta. Sostituirla in automatico
                  farebbe apparire riuscito ciò che non è stato eseguito. */}
              {liveFailed && (
                <Alert
                  severity="error"
                  data-testid="live-stage-failed"
                  sx={{ borderRadius: '8px', mb: 3 }}
                  action={equivalentReplay ? (
                    <Button
                      size="small"
                      data-testid="open-recorded-run"
                      disabled={starting}
                      onClick={() => void start({
                        demo_case_key: equivalentReplay.case_id,
                        execution_mode: 'REPLAY',
                      })}
                      sx={{ textTransform: 'none', fontFamily: font.body, fontSize: 13 }}
                    >
                      Apri la run registrata equivalente
                    </Button>
                  ) : undefined}
                >
                  <Typography sx={{ fontFamily: font.body, fontSize: 13 }}>
                    {reasonLabel(state.run?.stopped_at ?? 'LIVE_STAGE_FAILED')}.
                    {' '}Gli stage eseguiti restano visibili; nessun artefatto registrato
                    li ha sostituiti.
                  </Typography>
                </Alert>
              )}
            </Box>

            {/* Spina a sinistra, ispezione a destra. */}
            <Box sx={{
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
                  <RunSpine
                    stages={visibleStages}
                    selectedStageId={selectedStageId}
                    onSelect={setSelectedStageId}
                  />
                )}
              </Box>
              <Box sx={{
                border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`,
                minHeight: 400, alignSelf: 'start',
              }}>
                <StageInspector
                  stage={selected}
                  events={selectedStageId ? eventsForStage(state, selectedStageId) : []}
                  clinicalText={state.run?.input_text}
                />
              </Box>
            </Box>

            {terminal && (
              <Box sx={{ mt: 6 }}>
                <Tabs
                  value={lowerTab}
                  onChange={(_, next: number) => setLowerTab(next)}
                  sx={{ borderBottom: `1px solid ${color.hairline}`, minHeight: 44 }}
                >
                  <Tab label="Dossier" />
                  <Tab label="Provenienza" />
                  <Tab label="Modalità relatore" />
                </Tabs>

                <Box sx={{ pt: 3 }}>
                  {lowerTab === 0 && (
                    artifacts.dossierUnavailable
                      ? (
                        <Alert severity="info" sx={{ borderRadius: '8px' }}>
                          {artifacts.dossierUnavailable}
                        </Alert>
                      )
                      : <DossierView dossier={artifacts.dossier} />
                  )}
                  {lowerTab === 1 && <ProvenanceTree items={artifacts.provenance} />}
                  {lowerTab === 2 && (
                    <SupervisorPanel
                      metrics={artifacts.metrics}
                      events={state.events}
                      hashChainValid={artifacts.hashChainValid}
                      versions={state.run?.versions ?? {}}
                    />
                  )}
                </Box>
              </Box>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
}
