/**
 * Console di ispezione della pipeline verificabile.
 *
 * L'obiettivo dell'intera schermata è una sola domanda: il relatore, guardando
 * soltanto questa interfaccia, riesce a seguire un caso clinico dallo stage 1
 * al dossier e a risalire da un esito alla sua fonte?
 *
 * Per questo la pipeline è al centro e non c'è spazio per la conversazione.
 */

import { useCallback, useEffect, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Stack, Tab, Tabs, Tooltip, Typography } from '@mui/material';
import RunSpine from './RunSpine';
import StageInspector from './StageInspector';
import DossierView, { type Dossier } from './DossierView';
import ProvenanceTree from './ProvenanceTree';
import SupervisorPanel from './SupervisorPanel';
import {
  createRun, getDossier, getEvents, getMetrics, getProvenance, isRuntimeDisabled, listCases,
} from './api';
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
        Research pipeline
      </Typography>
      <Typography component="span" sx={{ fontFamily: font.body, fontSize: 12, opacity: 0.85 }}>
        Componente sperimentale · non validato clinicamente · non per decisioni cliniche
      </Typography>
    </Box>
  );
}

export default function ResearchConsole() {
  const [cases, setCases] = useState<DemoCase[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [artifacts, setArtifacts] = useState<RunArtifacts>(NO_ARTIFACTS);
  const [lowerTab, setLowerTab] = useState(0);

  const { state } = useRunStream(runId);
  const stages = stagesInOrder(state);
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
  useEffect(() => {
    if (!runId || !terminal) return undefined;
    let active = true;

    void (async () => {
      const [dossier, provenance, metrics, events] = await Promise.all([
        getDossier(runId).catch((error: unknown) => error),
        getProvenance(runId).catch(() => ({ items: [] as ProvenanceItem[] })),
        getMetrics(runId).catch(() => null),
        getEvents(runId).catch(() => null),
      ]);
      if (!active) return;

      const failed = dossier instanceof Error;
      setArtifacts({
        // Una run fermata non ha dossier, e il motivo va detto invece di
        // mostrare una sezione vuota.
        dossier: failed ? null : ((dossier as { dossier?: Dossier }).dossier ?? null),
        dossierUnavailable: failed ? (dossier as Error).message : null,
        provenance: (provenance as { items: ProvenanceItem[] }).items ?? [],
        metrics: metrics as RunMetrics | null,
        hashChainValid: events ? events.hash_chain_valid : null,
      });
    })();

    return () => { active = false; };
  }, [runId, terminal]);

  const start = useCallback(async (caseId: string) => {
    setStarting(true);
    setLoadError(null);
    setSelectedStageId(null);
    setArtifacts(NO_ARTIFACTS);
    try {
      const created = await createRun({ demo_case_key: caseId });
      setRunId(created.run_id);
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : 'Avvio non riuscito.');
    } finally {
      setStarting(false);
    }
  }, []);

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

        {/* Casi sintetici. Eseguono la pipeline reale, non output registrati come tali. */}
        <Box sx={{ mt: 5 }}>
          <Typography sx={{
            fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: color.muted, mb: 1.5,
          }}>
            Casi dimostrativi
          </Typography>
          <Stack direction="row" spacing={1.5} sx={{ flexWrap: "wrap" }}>
            {cases.map((demo) => (
              <Button
                key={demo.case_id}
                onClick={() => void start(demo.case_id)}
                disabled={starting}
                sx={{
                  fontFamily: font.body, fontSize: 14, textTransform: 'none',
                  borderRadius: `${radius.pill}px`, px: 2.5, py: 1,
                  backgroundColor: color.ink, color: '#fff',
                  '&:hover': { backgroundColor: '#000' },
                  '&.Mui-disabled': { backgroundColor: color.hairline, color: color.muted },
                }}
              >
                {demo.case_id.replace(/^CASE-\d+-/, '').replace(/-/g, ' ')}
              </Button>
            ))}
            {cases.length === 0 && !loadError && (
              <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.muted }}>
                Caricamento dei casi…
              </Typography>
            )}
          </Stack>
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
              {state.connection === 'connecting' && (
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <CircularProgress size={12} sx={{ color: color.actionBlue }} />
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.actionBlue }}>
                    in ascolto
                  </Typography>
                </Stack>
              )}
            </Box>

            {/* Spina a sinistra, ispezione a destra. */}
            <Box sx={{
              display: 'grid', gap: 3, mt: 3,
              gridTemplateColumns: { xs: '1fr', lg: 'minmax(320px, 400px) 1fr' },
            }}>
              <Box>
                <RunSpine
                  stages={stages}
                  selectedStageId={selectedStageId}
                  onSelect={setSelectedStageId}
                />
              </Box>
              <Box sx={{
                border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`,
                minHeight: 400, alignSelf: 'start',
              }}>
                <StageInspector
                  stage={selected}
                  events={selectedStageId ? eventsForStage(state, selectedStageId) : []}
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
