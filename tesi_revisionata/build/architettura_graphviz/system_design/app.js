(function () {
  'use strict';
  const data = globalThis.ArchitectureData;
  const model = globalThis.ArchitectureState;
  const assets = globalThis.ArchitectureAssets;
  const examples = globalThis.ArchitectureExamples;
  const pathViews = globalThis.ArchitecturePaths;
  const briefEdition = document.body.dataset.edition === 'breve';
  let printMode = briefEdition ? 'brief' : 'complete';
  const content = document.getElementById('content');
  const navigation = document.getElementById('navigation');
  const exampleSelect = document.getElementById('example');
  const search = document.getElementById('search');
  const sidebar = document.getElementById('sidebar');
  const menu = document.getElementById('menu');
  const announcement = document.getElementById('announcement');
  if (!data || !model || !assets || !examples || !globalThis.ArchitectureJourney || !globalThis.ArchitectureMacroUI) {
    content.textContent = 'Il documento non è completo. Apri il file autonomo della presentazione.';
    return;
  }
  let state = model.parseLocation(location.hash, data);
  let zoom = 1;


  function el(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function append(parent, ...children) { for (const child of children) if (child) parent.append(child); return parent; }
  const heading = (tag, text) => el(tag, '', text);
  function button(text, action, className = 'button') {
    const item = el('button', className, text); item.type = 'button'; item.addEventListener('click', action); return item;
  }
  function navigate(patch) {
    const next = { ...state, ...patch }; const hash = model.serialize(next);
    if (location.hash === hash) { state = next; render(); } else location.hash = hash;
  }
  function phaseLink(id, text, className) {
    const link = el('a', className, text); link.href = model.serialize({ ...state, phase: id, tab: 'sintesi' }); return link;
  }
  function typeName(type) { return ({ codice: 'Codice deterministico', modello: 'Modello linguistico', controllo: 'Controllo deterministico', misto: 'Codice e modello linguistico' })[type] || 'Elaborazione'; }
  function kindName(kind) { return ({ dato: 'Informazioni', codice: 'Elaborazione', modello: 'Lettura assistita', controllo: 'Verifica', risultato: 'Risultato', limite: 'Limite' })[kind] || 'Elaborazione'; }
  function list(items, className = '') { return append(el('ul', className), ...items.map(text => el('li', '', text))); }
  function section(title, child) { return append(el('section', 'detail-section'), heading('h2', title), child); }
  function contractTable(fields) {
    const table = el('table', 'contract'); const head = el('tr');
    for (const title of ['Informazione', 'Che cosa contiene']) { const th = el('th', '', title); th.scope = 'col'; head.append(th); }
    table.append(append(el('thead'), head)); const body = el('tbody');
    for (const field of fields) body.append(append(el('tr'), el('td', '', field.name), el('td', '', field.description)));
    table.append(body); return table;
  }
  function parseSVG(source) {
    const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw new Error('Figura non disponibile');
    const svg = document.importNode(parsed.documentElement, true);
    for (const title of svg.querySelectorAll('title')) title.remove();
    return svg;
  }
  const selectedExample = () => examples.items.find(item => item.id === state.example) || examples.items[0];
  function diagramKey(phase) {
    if (phase.assetKey) return phase.assetKey;
    return state.example === 'diagnostica' && ['risoluzione', 'unita', 'selezione', 'reader', 'validazione'].includes(phase.id) ? 'solo-grafo' : phase.id;
  }
  function examplePanel(phase) {
    const example = selectedExample(); const box = el('section', 'example-panel');
    append(box, heading('h2', phase ? 'L’esempio, in questa fase' : example.label));
    if (phase) {
      const step = globalThis.ArchitectureJourney.step(phase.id, example.id, examples.caseText);
      append(box, el('p', 'journey-context', step.context + ' · ' + example.label));
      const steps = el('ol', 'journey');
      for (const [title, text, name] of [['Da dove arriviamo', step.input, 'input'], ['Che cosa cambia qui', step.action, 'action'], ['Che cosa otteniamo e portiamo avanti', step.result, 'result']]) {
        steps.append(append(el('li', 'journey-step journey-' + name), heading('h3', title), el('p', '', text)));
      }
      box.append(steps);
      const next = model.neighbors(phase.id, data).next;
      if (next) box.append(phaseLink(next, phase.id === 'corpus' ? 'Inizia dal caso' : next === 'runtime' ? 'Scopri il coordinamento trasversale' : 'Segui l’esempio nella fase successiva', 'journey-next'));
      box.append(el('p', 'example-origin', 'Esempio documentato; le parafrasi didattiche non sono citazioni del testo generato.'));
    } else box.append(el('p', '', example.lead));
    box.append(el('p', 'example-origin', 'Caso sintetico; associazioni documentate nel Knowledge Graph e nelle fonti.'));
    return box;
  }
  function exampleDetail() {
    const example = selectedExample(); const wrapper = el('section', 'example-detail');
    append(wrapper, heading('h2', example.title), el('p', '', example.lead));
    const path = el('ol', 'example-path'); for (const item of example.path) path.append(el('li', '', item));
    append(wrapper, path, contractTable(example.facts.map(([name, description]) => ({ name, description }))));
    if (example.quote) append(wrapper, heading('h3', 'Un breve estratto originale'), el('blockquote', '', example.quote));
    append(wrapper, heading('h3', 'Che cosa questo esempio non dimostra'), el('p', '', example.limitation));
    const provenance = el('section', 'example-provenance');
    append(provenance, heading('h3', 'Da dove provengono le informazioni'), el('p', '', example.kind + ': associazione presente nel Knowledge Graph e contenuto conservato nell’esempio documentato.'));
    if (example.sourceUrl) { const link = el('a', '', example.sourceLabel); link.href = example.sourceUrl; link.target = '_blank'; link.rel = 'noopener noreferrer'; provenance.append(link); }
    else provenance.append(el('p', '', example.sourceLabel));
    append(provenance, el('p', 'example-origin', 'Caso sintetico; associazioni e risultati documentati. Nessuna nuova analisi eseguita.')); wrapper.append(provenance); return wrapper;
  }

  function renderNavigation() { if(briefEdition){navigation.replaceChildren();return;} macroUI.navigation(navigation, search.value); }
  function renderOverview() {
    const details = el('details', 'dashboard-map');
    details.append(el('summary', '', 'Consulta la mappa completa dell’architettura'));
    const map = el('div', 'dashboard-map-content');
    macroUI.overview(map); details.append(map); content.append(details);
  }

  function renderDiagram(phase, panel) {
    const section = el('section', 'diagram-section'); const head = el('div', 'diagram-heading'); head.append(heading('h2', 'Operazioni e dati scambiati'));
    const tools = el('div', 'diagram-tools'); const value = el('span', 'zoom-value', '100%'); const inner = el('div', 'diagram-inner');
    let diagramBaseWidth = 650;
    function updateZoom() { inner.style.width = diagramBaseWidth * zoom + 'px'; value.textContent = Math.round(zoom * 100) + '%'; }
    const decrease = button('−', () => { zoom = Math.max(.7, +(zoom - .15).toFixed(2)); updateZoom(); }); decrease.setAttribute('aria-label', 'Riduci la figura');
    const increase = button('+', () => { zoom = Math.min(2, +(zoom + .15).toFixed(2)); updateZoom(); }); increase.setAttribute('aria-label', 'Ingrandisci la figura');
    const reset = button('100%', () => { zoom = 1; updateZoom(); }); reset.setAttribute('aria-label', 'Ripristina la dimensione al 100 per cento');
    const key = diagramKey(phase);
    append(tools, decrease, value, increase, reset,
      button('SVG', () => macroUI.download(key, 'svg')),
      button('PDF vettoriale', () => macroUI.download(key, 'pdf')),
      button('Sorgente DOT', () => macroUI.download(key, 'dot'))); head.append(tools);
    const viewport = el('div', 'diagram-viewport'); viewport.tabIndex = 0; viewport.setAttribute('aria-label', 'Figura del passaggio, scorribile orizzontalmente');
    const bypass = diagramKey(phase) === 'solo-grafo';
    const flow = bypass ? data.graphOnlyFlow : phase.flow;
    const svg = parseSVG(assets.svgs[diagramKey(phase)]); svg.removeAttribute('width'); svg.removeAttribute('height'); svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', phase.title);
    const nativeWidth = Number(svg.getAttribute('viewBox')?.split(/\s+/)[2]);
    diagramBaseWidth = Math.max(650, Number.isFinite(nativeWidth) ? nativeWidth : 700);
    inner.style.minWidth = '0px'; updateZoom();
    const inspector = el('div', 'component-inspector'); inspector.hidden = true;
    const title = heading('h3', ''); const description = el('p', '', ''); append(inspector, title, description);
    function inspect(node, group) { inspector.hidden = false; for (const item of svg.querySelectorAll('.node')) item.classList.toggle('active', item === group); title.textContent = node.title; description.textContent = node.detail; announcement.textContent = node.title + ': ' + node.detail; }
    for (const node of flow.nodes) {
      const group = svg.querySelector('[id="node-' + node.id + '"]'); if (!group) continue;
      group.setAttribute('tabindex', '0'); group.setAttribute('role', 'button'); group.setAttribute('aria-label', node.title + ' — ' + kindName(node.kind));
      group.addEventListener('click', () => inspect(node, group)); group.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inspect(node, group); } });
    }
    inner.append(svg); viewport.append(inner); append(section, head, viewport, inspector); panel.append(section);
  }
  function renderPhase(phase) {
    phase = pathViews.detail(phase, state.example);
    const intro = append(el('section', 'intro'), heading('h1', phase.title), el('p', '', phase.summary));
    intro.append(append(el('div', 'phase-meta'), el('span', 'type-label ' + phase.type, typeName(phase.type)), el('span', '', (phase.id === 'runtime' ? 'Coordinamento trasversale' : phase.id === 'corpus' ? 'Preparazione a monte' : 'Passaggio ' + phase.number) + ' · Architettura attuale')));
    const parent = data.macros.find(item => item.phases.includes(phase.id));
    if (parent) content.append(phaseLink(parent.id, 'Nella macrofase: ' + parent.title, 'phase-parent'));
    content.append(intro);
    const tabs = el('div', 'tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Approfondimenti del passaggio');
    const labels = { sintesi: 'Come funziona', contratti: 'Che cosa entra ed esce', controlli: 'Come si controlla', codice: 'Esempio e fonte' };
    for (const id of model.tabs) {
      const item = button(labels[id], () => navigate({ tab: id }), 'tab'); item.id = 'tab-' + id; item.setAttribute('role', 'tab'); item.setAttribute('aria-controls', 'phase-panel'); item.setAttribute('aria-selected', String(state.tab === id)); item.tabIndex = state.tab === id ? 0 : -1;
      item.addEventListener('keydown', event => { const i = model.tabs.indexOf(id); const next = event.key === 'ArrowRight' ? (i + 1) % model.tabs.length : event.key === 'ArrowLeft' ? (i + 3) % model.tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : -1; if (next >= 0) { event.preventDefault(); navigate({ tab: model.tabs[next] }); } }); tabs.append(item);
    }
    content.append(tabs); const panel = el('section'); panel.id = 'phase-panel'; panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', 'tab-' + state.tab);
    if (state.tab === 'sintesi') {
      renderDiagram(phase, panel);
      panel.append(section('Come opera il componente', list(phase.how, 'mechanism-list')));
      if (phase.workedExample) panel.append(section('Applicazione ai dati documentati di BRAF', contractTable(phase.workedExample)));
    } else if (state.tab === 'contratti') {
      append(panel, section('Le informazioni di partenza', contractTable(phase.input)), section('Le informazioni prodotte', contractTable(phase.output)), append(el('section', 'principle'), heading('h3', 'Che cosa deve rimanere distinto'), el('p', '', phase.design)));
    } else if (state.tab === 'controlli') {
      append(panel, section('Che cosa viene controllato', list(phase.controls)), section('Quando ci si ferma o si segnala un limite', list(phase.failures, 'status-list')), append(el('section', 'principle'), heading('h3', 'Perché questo controllo conta'), el('p', '', phase.design)));
    } else panel.append(exampleDetail());
    content.append(panel, examplePanel(phase));
  }
  function renderPagination() {
    const pagination = document.getElementById('pagination'); pagination.replaceChildren(); const adjacent = model.neighbors(state.phase, data);
    if(briefEdition)return;
    for (const direction of ['previous', 'next']) {
      const id = adjacent[direction]; if (!id) continue; const phase = [...data.phases, ...data.macros].find(item => item.id === id);
      const link = phaseLink(id, undefined, 'page-link ' + (direction === 'next' ? 'next' : 'previous'));
      append(link, el('small', '', direction === 'next' ? 'Passaggio successivo' : 'Passaggio precedente'), el('span', '', phase ? phase.title : 'Come funziona l’insieme')); pagination.append(link);
    }
  }
  function render() {
    document.getElementById('dashboard').hidden = briefEdition || state.phase !== 'panoramica';
    for (const link of document.querySelectorAll('#dashboard a[href^="#macro-"]')) {
      link.href = model.serialize({ ...state, phase: link.getAttribute('href').split('?')[0].slice(1), tab: 'sintesi' });
    }
    document.querySelector('.dashboard-home').href = 'Architettura_per_il_relatore.html' + model.serialize({ ...state, phase: 'panoramica', tab: 'sintesi' });
    zoom = 1; exampleSelect.value = state.example; content.replaceChildren(); const phase = data.phases.find(item => item.id === state.phase);
    const macro = data.macros.find(item => item.id === state.phase);
    if (briefEdition) {
      macroUI.brief(content);
      content.prepend(button('Scarica il PDF dell’esempio selezionato', () => macroUI.download('breve--' + state.example, 'pdf'), 'dashboard-download brief-download'));
    } else if (macro) macroUI.render(macro, content); else if (phase) renderPhase(phase); else renderOverview();
    document.title = (macro ? macro.title : phase ? phase.title : 'Come funziona l’architettura') + ' — MTB'; renderNavigation(); renderPagination(); sidebar.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false');
  }
  function preparePrint() {
    const book = document.getElementById('print-book'); book.replaceChildren();
    book.classList.toggle('print-brief', printMode === 'brief');
    if (printMode === 'brief') { macroUI.print(book, true); return; }
    append(book, append(el('section', 'print-cover'), heading('h1', 'Come funziona l’architettura'), el('p', '', 'Dal caso alle fonti e dalle fonti al dossier.'), heading('h2', 'Esempio: ' + selectedExample().label), el('p', '', 'Caso sintetico; associazioni e risultati documentati. Nessuna nuova analisi eseguita.')));
    macroUI.print(book);
    for (const original of data.phases) {
      const phase = pathViews.detail(original, state.example);
      const section = el('section', 'print-phase');
      append(section, heading('h1', phase.number + ' · ' + phase.title), el('p', '', phase.summary), parseSVG(assets.svgs[diagramKey(phase)]), heading('h2', 'Come opera il componente'), list(phase.how));
      if (phase.workedExample) append(section, heading('h2', 'Applicazione ai dati di BRAF'), contractTable(phase.workedExample));
      append(section, examplePanel(phase), heading('h2', 'Che cosa riceve'), contractTable(phase.input), heading('h2', 'Che cosa restituisce'), contractTable(phase.output), heading('h2', 'Controlli e condizioni di arresto'), list(phase.controls), list(phase.failures)); book.append(section);
    }
    book.append(append(el('section', 'print-phase'), heading('h1', 'Provenienza dell’esempio'), exampleDetail()));
  }
  exampleSelect.addEventListener('change', () => navigate({ example: exampleSelect.value }));
  search.addEventListener('input', renderNavigation);
  document.querySelector('.skip-link').addEventListener('click', event => { event.preventDefault(); document.getElementById('main').focus({ preventScroll: true }); });
  menu.addEventListener('click', () => { const open = !sidebar.classList.contains('is-open'); sidebar.classList.toggle('is-open', open); menu.setAttribute('aria-expanded', String(open)); if (open) search.focus(); });
  document.getElementById('download-brief').addEventListener('click', () => macroUI.download('breve--'+state.example,'pdf'));
  window.addEventListener('beforeprint', () => preparePrint());
  window.addEventListener('hashchange', () => {
    const previous = state;
    const pathHadFocus = document.activeElement?.matches('.macro-paths button');
    state = model.parseLocation(location.hash, data); render();
    if (previous.phase !== state.phase) {
      document.getElementById('main').focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    } else if (previous.tab !== state.tab) document.getElementById('tab-' + state.tab)?.focus({ preventScroll: true });
    else if (previous.example !== state.example && pathHadFocus) document.querySelector('.macro-paths [aria-pressed="true"]')?.focus({ preventScroll: true });
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && sidebar.classList.contains('is-open')) { sidebar.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false'); menu.focus(); } });
  const macroUI = globalThis.ArchitectureMacroUI.create({ el, append, heading, button, phaseLink, contractTable, parseSVG, navigate, state: () => state, data, examples, assets, model });
  render();
})();
