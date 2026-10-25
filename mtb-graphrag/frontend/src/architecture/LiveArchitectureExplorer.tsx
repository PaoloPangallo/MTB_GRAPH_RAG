import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import CaseInputPanel, { type RunRequest } from '../research/CaseInputPanel';
import { createRun, getConfig, getStage, listCases } from '../research/api';
import { useRunStream } from '../research/useRunStream';
import { isTerminal } from '../research/runReducer';
import { STAGE_LABELS, type DemoCase, type PipelineEvent, type PipelineStage } from '../research/types';
import StageOutput from '../research/stages';
import { JsonInspector } from '../research/values/StructuredValue';
import { stageTiming } from '../research/stageTiming';
import { runRoute, VERIFIABLE_PIPELINE_ROUTE } from '../routes';
import './ArchitectureExplorer.css';

interface Detail { key: string; stage?: PipelineStage; events?: PipelineEvent[]; error?: string }

/** All displayed executions come from the canonical public API. Viewing never starts a run. */
export default function LiveArchitectureExplorer() {
  const [params, setParams] = useSearchParams();
  const runId = params.get('run');
  const { state, refresh } = useRunStream(runId);
  const run = state.run?.run_id === runId ? state.run : null;
  const [cases, setCases] = useState<DemoCase[]>([]);
  const [cacheAvailable, setCacheAvailable] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ runId: string; stageId: string } | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [detailRevision, setDetailRevision] = useState(0);
  const [tab, setTab] = useState<'output' | 'io' | 'events'>('io');
  const stages = [...(run?.stages ?? [])].sort((a, b) => a.sequence - b.sequence);
  const following = selected?.runId !== runId;
  const stageId = !following ? selected.stageId : run?.current_stage ?? stages.at(-1)?.stage_id;
  const stage = stages.find(item => item.stage_id === stageId);
  const stageSequence = state.events.filter(event => event.stage_id === stageId).at(-1)?.sequence ?? 0;
  const detailKey = `${runId}:${stageId}:${stage?.status}:${stageSequence}:${detailRevision}`;
  const currentDetail = detail?.key === detailKey ? detail : null;
  const fullStage = currentDetail?.stage;
  const timing = stage ? stageTiming(stage) : null;

  useEffect(() => {
    let active = true;
    void Promise.all([listCases(), getConfig()]).then(([catalog, config]) => {
      if (!active) return;
      setCases(catalog.cases);
      setCacheAvailable((config.document_cache as { document_cache_available?: boolean } | undefined)?.document_cache_available !== false);
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Configurazione non disponibile.'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!runId || !stageId) return;
    let active = true;
    // Coalesce progress frames; the selected stage is loaded with its full public payload.
    const timer = window.setTimeout(() => {
      void getStage(runId, stageId).then(response => {
        if (active) setDetail({ key: detailKey, ...response });
      }).catch((reason: unknown) => {
        if (active) setDetail({ key: detailKey, error: reason instanceof Error ? reason.message : 'Dettaglio non disponibile.' });
      });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [runId, stageId, detailKey]);

  const start = async (request: RunRequest) => {
    setStarting(true); setError(null);
    try {
      const created = await createRun(request);
      setSelected(null); setTab('io');
      setParams({ run: created.run_id });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Avvio fallito.');
    } finally { setStarting(false); }
  };
  const choose = (id: string) => { if (runId) setSelected({ runId, stageId: id }); };
  const index = stages.findIndex(item => item.stage_id === stageId);
  const events = currentDetail?.events ?? [];
  const terminal = !!run && isTerminal(state);

  return <main className="gca-explorer">
    <header className="gca-nav"><Link className="gca-brand" to={VERIFIABLE_PIPELINE_ROUTE}><strong>GCA4</strong><span>Architettura in esecuzione</span></Link><div><Link to="/architecture?mode=demo">Demo sintetica</Link><Link to={runId ? runRoute(runId) : VERIFIABLE_PIPELINE_ROUTE}>Apri la console</Link></div></header>
    <div className="gca-content">
      <section className="gca-introduction"><div><h1>Come GCA4 costruisce un dossier</h1><p>Avvia il caso e segui i passaggi effettivamente registrati dalla pipeline.</p></div><p className="demo-disclosure"><span><strong>Run reale</strong>Input, output e stati provengono dal backend. La consultazione non genera nuove chiamate al modello.</span></p></section>
      {(error || state.error) && <p role="alert" className="live-error">{error ?? state.error}</p>}
      {!runId && <section className="live-input"><h2>Parti dal testo del caso</h2><p>Premendo Esegui la pipeline avvii chiamate reali al provider configurato e, quando necessario, alle fonti documentali. Usa casi pubblici, sintetici o anonimizzati.</p><CaseInputPanel cases={cases} busy={starting} onRun={request => { void start(request); }} documentCacheAvailable={cacheAvailable} /></section>}
      {runId && <>
        <section className="live-run-header"><div><h2>{run?.case_id ?? 'Caricamento della run…'}</h2><code>{runId}</code><p><strong>{run?.status ?? 'Caricamento'}</strong> · Trasporto eventi: {state.connection} · {state.events.length} eventi registrati</p><p>Origine esecuzione: {run?.execution_mode ?? 'non disponibile'}. Documenti da cache e risposte registrate mantengono l’origine dichiarata dal backend.</p></div><div className="live-run-actions"><button onClick={() => { setDetailRevision(value => value + 1); void refresh(); }}>Aggiorna</button><button onClick={() => setParams({})} disabled={!terminal}>Nuovo caso</button></div></section>
        {run && <details className="live-case"><summary>Testo inviato al parser</summary><p>{run.input_text}</p></details>}
        <section className="live-workspace">
          <div className="live-trace"><div className="live-trace-heading"><h2>Flusso registrato</h2><button aria-pressed={following} onClick={() => setSelected(null)}>Segui esecuzione</button></div><p>Gli stage mostrano il contratto della pipeline; gli eventi indicano l’ordine effettivo delle operazioni. Alcuni stage sono pubblicati solo al termine della chiamata: il loro output appare quando il backend lo registra. Le verifiche per candidato sono nei dettagli documentali.</p>
            {!stages.length && <p role="status">In attesa degli stage del backend…</p>}
            <ol className="live-stage-list">{stages.map(item => <li key={item.stage_id}><button className={`${item.stage_id === stageId ? 'is-current' : ''} ${item.status === 'RUNNING' ? 'is-running' : ''}`} aria-pressed={item.stage_id === stageId} onClick={() => choose(item.stage_id)}><span className="live-stage-number">{item.sequence}</span><span><strong>{STAGE_LABELS[item.stage_id] ?? item.stage_id}</strong><small>{item.producer.kind} · {item.status}</small><small>{item.producer.component}</small></span></button></li>)}</ol>
          </div>
          <aside className="live-detail" aria-label="Dati reali del passaggio">
            {stage ? <><div className="live-detail-heading"><h2>{STAGE_LABELS[stage.stage_id] ?? stage.stage_id}</h2><p>{stage.status} · {stage.producer.kind} · {timing?.label}: {timing?.milliseconds == null ? 'non misurata' : `${Math.round(timing.milliseconds)} ms`}</p><p>{stage.producer.component} · versione {stage.producer.version}</p>{stage.producer.model && <p>Modello: {stage.producer.model} · prompt: {stage.producer.prompt_version ?? 'non registrato'}</p>}<p>Origine: {stage.artifact_origin}</p><div className="live-navigation"><button disabled={index <= 0} onClick={() => choose(stages[index - 1].stage_id)}>Precedente</button><button disabled={index < 0 || index >= stages.length - 1} onClick={() => choose(stages[index + 1].stage_id)}>Successivo</button></div></div>
              <div className="live-tabs" role="group" aria-label="Vista del passaggio"><button aria-pressed={tab === 'io'} onClick={() => setTab('io')}>Input / output</button><button aria-pressed={tab === 'output'} onClick={() => setTab('output')}>Risultati e chiamate</button><button aria-pressed={tab === 'events'} onClick={() => setTab('events')}>Eventi registrati</button></div>
              {!currentDetail && <p role="status">Caricamento dei payload registrati…</p>}
              {currentDetail?.error && <p role="alert">{currentDetail.error} Nessun output sostitutivo viene generato.</p>}
              {fullStage && <div className="live-payload">
                {tab === 'io' && <><h3>Input registrato</h3><JsonInspector value={fullStage.input_preview} /><h3>Output registrato</h3><JsonInspector value={fullStage.output_preview} /><h3>Motivi, errori e limiti</h3><JsonInspector value={{ reason_codes: fullStage.reason_codes, warnings: fullStage.warnings, errors: fullStage.errors, lineage: fullStage.lineage, metrics: fullStage.metrics }} /><p>Proiezione pubblica registrata dal runtime. Campi assenti o redatti non vengono ricostruiti.</p></>}
                {tab === 'output' && <StageOutput stage={fullStage} clinicalText={run?.input_text} />}
                {tab === 'events' && <><p>Eventi dello stage ordinati per sequenza. I payload arrivano dal ledger; le chiamate interne sono mostrate solo quando registrate.</p>{events.length ? [...events].sort((a, b) => a.sequence - b.sequence).map(event => <details key={event.event_id}><summary>#{event.sequence} · {event.event_type} · {event.created_at}</summary><JsonInspector value={event.payload} /><p>Hash payload: {event.payload_hash ?? 'non disponibile'}</p></details>) : <p>Nessun evento disponibile per questo stage.</p>}</>}
              </div>}
            </> : <p>Il dettaglio apparirà quando il backend registra il primo stage.</p>}
          </aside>
        </section>
        {terminal && <section className="live-outcome"><h2>Esecuzione {run.status}</h2><p>Consulta il dossier canonico e la sua riconciliazione nella console. Il completamento tecnico di uno stage non dimostra supporto scientifico.</p><Link to={runRoute(runId)}>Apri dossier, provenance e limitazioni →</Link>{run.stopped_at && <p>Interruzione: {run.stopped_at}</p>}</section>}
      </>}
    </div>
  </main>;
}
