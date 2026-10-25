import { useEffect, useMemo, useReducer } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import LiveArchitectureExplorer from './LiveArchitectureExplorer';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import PlayArrowRounded from '@mui/icons-material/PlayArrowRounded';
import PauseRounded from '@mui/icons-material/PauseRounded';
import ChevronLeftRounded from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import RestartAltRounded from '@mui/icons-material/RestartAltRounded';
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import { VERIFIABLE_PIPELINE_ROUTE } from '../routes';
import { architectureEdges, architectureNodes, demoScenarios, nodeById } from './model';
import { nodeCopy, scenarioCopy } from './presentation';
import FlowDiagram from './FlowDiagram';
import './ArchitectureExplorer.css';

interface SimulationState {
  scenarioId: string;
  index: number;
  playing: boolean;
  speed: number;
  overview: boolean;
  inspectedNodeId: string | null;
}
type Action =
  | { type: 'PLAY' | 'PAUSE' | 'NEXT' | 'PREVIOUS' | 'RESET' | 'TICK' | 'RETURN' }
  | { type: 'SCENARIO'; id: string }
  | { type: 'SPEED'; value: number }
  | { type: 'VIEW'; overview: boolean }
  | { type: 'INSPECT'; id: string }
  | { type: 'GOTO'; index: number };

const initialState: SimulationState = { scenarioId: demoScenarios[0].id, index: 0, playing: false, speed: 1, overview: false, inspectedNodeId: null };

function reducer(state: SimulationState, action: Action): SimulationState {
  const length = demoScenarios.find((scenario) => scenario.id === state.scenarioId)!.events.length;
  switch (action.type) {
    case 'PLAY': return { ...state, playing: true, overview: false, inspectedNodeId: null, index: state.index === length - 1 ? 0 : state.index };
    case 'PAUSE': return { ...state, playing: false };
    case 'TICK': return { ...state, index: Math.min(length - 1, state.index + 1), playing: state.index + 1 < length - 1, inspectedNodeId: null };
    case 'NEXT': return { ...state, index: Math.min(length - 1, state.index + 1), playing: false, inspectedNodeId: null };
    case 'PREVIOUS': return { ...state, index: Math.max(0, state.index - 1), playing: false, inspectedNodeId: null };
    case 'RESET': return { ...state, index: 0, playing: false, inspectedNodeId: null };
    case 'SCENARIO': return { ...state, scenarioId: action.id, index: 0, playing: false, overview: false, inspectedNodeId: null };
    case 'SPEED': return { ...state, speed: action.value };
    case 'VIEW': return { ...state, overview: action.overview, playing: false, inspectedNodeId: action.overview ? demoScenarios.find((scenario) => scenario.id === state.scenarioId)!.events[state.index].nodeId : null };
    case 'INSPECT': return { ...state, inspectedNodeId: action.id, playing: false };
    case 'GOTO': return { ...state, index: Math.max(0, Math.min(length - 1, action.index)), playing: false, inspectedNodeId: null };
    case 'RETURN': return { ...state, inspectedNodeId: null };
  }
}

const branches = [
  { family: 'EVIDENCE_DRUG', name: 'Relazione con farmaco', path: 'Citazione → compatibilità strutturale → verifica semantica', condition: 'La verifica semantica parte solo con gate PASS. MISMATCH e UNRESOLVED restano bloccati.' },
  { family: 'EVIDENCE_STATEMENT', name: 'Relazione scientifica', path: 'Citazione → policy deterministica', condition: 'Usa una verifica documentale distinta; non chiama il verificatore semantico.' },
  { family: 'TRIAL', name: 'Studio clinico', path: 'Fonte NCT → contenuto documentale → record di trial', condition: 'Il record non dimostra efficacia terapeutica né eleggibilità del paziente.' },
  { family: 'KG_ONLY', name: 'Relazione del grafo', path: 'GCA → esito del record → dossier', condition: 'Conserva la provenienza GCA. Non attraversa document retrieval o Reader.' },
];

export default function ArchitectureExplorer() {
  const [params] = useSearchParams();
  return params.get('mode') === 'demo' ? <DemoArchitectureExplorer /> : <LiveArchitectureExplorer />;
}

function DemoArchitectureExplorer() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const scenario = demoScenarios.find((item) => item.id === state.scenarioId)!;
  const event = scenario.events[state.index];
  const inspectedNode = state.inspectedNodeId ? nodeById(state.inspectedNodeId) : null;
  const copy = scenarioCopy[scenario.id];
  const atEnd = state.index === scenario.events.length - 1;
  const items = useMemo(() => state.overview
    ? architectureNodes.map((node) => ({ node }))
    : scenario.events.map((event, eventIndex) => ({ node: nodeById(event.nodeId)!, event, eventIndex })), [scenario, state.overview]);

  useEffect(() => {
    if (!state.playing) return undefined;
    const interval = window.setInterval(() => dispatch({ type: 'TICK' }), 2800 / state.speed);
    return () => window.clearInterval(interval);
  }, [state.playing, state.speed, state.scenarioId]);

  return <main className="gca-explorer">
    <header className="gca-nav">
      <Link to={VERIFIABLE_PIPELINE_ROUTE} className="gca-brand"><AccountTreeOutlined /><strong>GCA4</strong><span>Architettura</span></Link>
      <div><Link to="/architecture">Avvia una run reale <ArrowForwardRounded /></Link><Link to={VERIFIABLE_PIPELINE_ROUTE}>Apri la console <ArrowForwardRounded /></Link></div>
    </header>

    <div className="gca-content">
      <section className="gca-introduction">
        <div><h1>Come GCA4 costruisce un dossier</h1><p>Dal testo del caso alla fonte verificabile. Segui un percorso, esplora i controlli e scopri cosa viene conservato.</p></div>
        <p className="demo-disclosure"><InfoOutlined /><span><strong>Demo interattiva</strong>Dati sintetici e verifiche simulate. Nessuna chiamata al backend o a modelli esterni.</span></p>
      </section>

      <section className="simulation-controls" aria-label="Controlli simulazione">
        <label className="scenario-field"><span>Scenario</span><select aria-label="Scenario" value={state.scenarioId} onChange={(event) => dispatch({ type: 'SCENARIO', id: event.target.value })}>{demoScenarios.map((item) => <option value={item.id} key={item.id}>{scenarioCopy[item.id].title}</option>)}</select></label>
        <div className="simulation-actions">
          <button type="button" className="primary-action" aria-label={state.playing ? 'Pausa' : 'Riproduci'} onClick={() => dispatch({ type: state.playing ? 'PAUSE' : 'PLAY' })}>{state.playing ? <PauseRounded /> : <PlayArrowRounded />}{state.playing ? 'Pausa' : atEnd ? 'Rivedi' : 'Riproduci'}</button>
          <button type="button" className="icon-action" aria-label="Passaggio precedente" title="Passaggio precedente" disabled={state.index === 0} onClick={() => dispatch({ type: 'PREVIOUS' })}><ChevronLeftRounded /></button>
          <button type="button" className="icon-action" aria-label="Passaggio successivo" title="Passaggio successivo" disabled={atEnd} onClick={() => dispatch({ type: 'NEXT' })}><ChevronRightRounded /></button>
          <button type="button" className="reset-action" aria-label="Ricomincia" onClick={() => dispatch({ type: 'RESET' })}><RestartAltRounded /><span>Ricomincia</span></button>
        </div>
        <label className="speed-field"><span>Velocità</span><select aria-label="Velocità" value={state.speed} onChange={(event) => dispatch({ type: 'SPEED', value: Number(event.target.value) })}><option value={0.5}>0,5×</option><option value={1}>1×</option><option value={2}>2×</option></select></label>
      </section>

      <section className="explorer-stage">
        <div className="explorer-map-panel">
          <div className="map-heading"><div><h2>{state.overview ? 'L’architettura completa' : copy.question}</h2><p>{state.overview ? 'Seleziona un componente per leggerne ruolo, input e output.' : scenario.subtitle}</p></div></div>
          <div className="map-view-switch" aria-label="Vista diagramma"><button type="button" aria-pressed={!state.overview} onClick={() => dispatch({ type: 'VIEW', overview: false })}>Percorso dello scenario</button><button type="button" aria-pressed={state.overview} onClick={() => dispatch({ type: 'VIEW', overview: true })}>Mappa completa</button></div>
          <FlowDiagram items={items} edges={architectureEdges} currentIndex={state.index} selectedNodeId={state.inspectedNodeId ?? event.nodeId} overview={state.overview} playing={state.playing} onSelect={(item) => dispatch(state.overview ? { type: 'INSPECT', id: item.node.id } : { type: 'GOTO', index: item.eventIndex! })} />
          {!state.overview && <div className="simulation-progress"><label htmlFor="scenario-progress">Passaggio <strong>{state.index + 1}</strong> di {scenario.events.length}</label><input id="scenario-progress" type="range" min={0} max={scenario.events.length - 1} value={state.index} aria-label="Raggiungi un passaggio" onChange={(event) => dispatch({ type: 'GOTO', index: Number(event.target.value) })} /><span>{atEnd ? 'Percorso concluso' : state.playing ? 'In riproduzione' : 'In pausa'}</span></div>}
        </div>

        <aside className="event-panel" aria-label="Dettaglio del passaggio">
          {inspectedNode ? <>
            <div className="panel-context">Componente · {nodeCopy[inspectedNode.id].phase}</div>
            <h2>{inspectedNode.title}</h2>
            <p className="panel-operation">{inspectedNode.description}</p>
            <div className="component-io"><h3>Input e output</h3><p>{inspectedNode.io}</p></div>
            <section className="component-connections"><h3>Collegamenti e condizioni</h3><ul>{architectureEdges.filter((edge) => edge.from === inspectedNode.id || edge.to === inspectedNode.id).map((edge) => <li key={edge.id}><span>{nodeCopy[edge.from].title} <ArrowForwardRounded /> {nodeCopy[edge.to].title}</span>{edge.label && <strong>{edge.label}</strong>}</li>)}</ul></section>
            <button type="button" className="text-action" onClick={() => dispatch({ type: 'RETURN' })}>Torna al passaggio corrente <ArrowForwardRounded /></button>
          </> : <>
            <div className="panel-context"><span>Passaggio {String(state.index + 1).padStart(2, '0')}</span><span>{nodeCopy[event.nodeId].phase}</span></div>
            <h2>{event.title}</h2>
            <p className="panel-operation">{event.operation}</p>
            <div className="event-data"><section><h3>Cosa entra</h3><p>{event.input}</p></section><div className="data-transfer"><ArrowForwardRounded /></div><section><h3>Cosa esce</h3><p>{event.output}</p></section></div>
            {event.note && <p className="event-note"><InfoOutlined /><span>{event.note}</span></p>}
            {event.nodeId === 'presentation' && <section className={`final-dossier${scenario.dossierStatus.includes('FAIL') ? ' is-partial' : ''}`}>
              <h3>Risultato del dossier</h3><p className="dossier-disposition">{scenario.dossierLabel}</p>
              <dl><div><dt>Fonte</dt><dd>{scenario.source}</dd></div><div><dt>Esito del record</dt><dd>{scenario.recordState}</dd></div><div><dt>Stato della run</dt><dd>{scenario.dossierStatus}</dd></div></dl>
              <p>Questo è un risultato dimostrativo. La presenza di un record non implica supporto clinico.</p>
            </section>}
            <div className="event-panel-footer"><span>{scenario.family}</span><button type="button" onClick={() => dispatch({ type: atEnd ? 'RESET' : 'NEXT' })}>{atEnd ? 'Ricomincia il percorso' : 'Continua'}<ArrowForwardRounded /></button></div>
          </>}
        </aside>
      </section>

      <section className="verification-paths"><h2>Una citazione autentica non equivale a supporto scientifico.</h2><p>Il percorso successivo cambia con il tipo di relazione. I controlli mantengono queste distinzioni.</p><div className="branch-list">{branches.map((branch) => <article key={branch.family}><div><h3>{branch.name}</h3><code>{branch.family}</code></div><p className="branch-route">{branch.path}</p><p>{branch.condition}</p></article>)}</div></section>
      <footer className="gca-footer"><span>GCA4 · Prototipo di ricerca per dossier documentali</span><span>RRF: k=60 · pesi 1:1 · top-25 per componente · top-5 SourceUnit</span><span>Non validato clinicamente</span></footer>
    </div>
    <span className="visually-hidden" role="status" aria-live="polite">Passaggio {state.index + 1}: {event.title}</span>
  </main>;
}
