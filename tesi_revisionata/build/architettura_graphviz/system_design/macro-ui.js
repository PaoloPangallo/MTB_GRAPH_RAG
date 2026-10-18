(function (root) {
  'use strict';
  function create(api) {
    const { el, append, heading, button, phaseLink, contractTable, parseSVG, navigate, state, data, examples, assets } = api;
    const macros = root.ArchitectureMacros;
    const pathViews = root.ArchitecturePaths;
    const selected = () => examples.items.find(item => item.id === state().example) || examples.items[0];
    function paths() {
      const paths = el('div', 'macro-paths'); paths.setAttribute('aria-label', 'I tre percorsi delle fonti');
      for (const [id, title] of [['melanoma','Pubblicazioni'],['studio','Registri degli studi clinici'],['diagnostica','Solo Knowledge Graph']]) {
        const choice = button(title, () => { if (state().example !== id) navigate({ example: id }); }, 'example-choice');
        choice.setAttribute('aria-pressed', String(state().example === id)); paths.append(choice);
      }
      return paths;
    }
    function download(key, format) {
      let bytes = assets.svgs[key]; let mime = 'image/svg+xml';
      if (format === 'dot') { bytes = assets.dots[key]; mime = 'text/vnd.graphviz'; }
      if (format === 'pdf') { bytes = Uint8Array.from(atob(assets.pdfs[key]), char => char.charCodeAt(0)); mime = 'application/pdf'; }
      const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
      const link = el('a'); link.href = url; link.download = key + '.' + format; document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    function diagram(key, title, graph) {
      const figure = el('figure', 'macro-figure');
      const caption = heading('h2', title); const captionId = 'figure-' + key; caption.id = captionId;
      const tools = el('div', 'diagram-tools');
      const viewport = el('div', 'macro-diagram'); viewport.tabIndex = 0; viewport.setAttribute('aria-label', title + ', scorribile');
      const inner = el('div', 'macro-diagram-inner'); const svg = parseSVG(assets.svgs[key]);
      const nativeWidth = Number(svg.getAttribute('viewBox')?.split(/\s+/)[2]);
      const baseWidth = Math.max(650, Number.isFinite(nativeWidth) ? nativeWidth : 700);
      inner.style.minWidth = '0px'; inner.style.width = baseWidth + 'px';
      svg.removeAttribute('width'); svg.removeAttribute('height'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', title + '. ' + graph.nodes.map(n => n.title.replace(/\n/g, '; ')).join('. '));
      inner.append(svg); viewport.append(inner); let zoom = 1;
      const value = el('span', 'zoom-value', '100%');
      function change(next) { zoom = Math.max(.7, Math.min(2, next)); inner.style.width = baseWidth * zoom + 'px'; value.textContent = Math.round(zoom * 100) + '%'; }
      const minus = button('−', () => change(zoom - .25)); minus.setAttribute('aria-label', 'Riduci il diagramma');
      const plus = button('+', () => change(zoom + .25)); plus.setAttribute('aria-label', 'Ingrandisci il diagramma');
      append(tools, minus, value, plus, button('SVG', () => download(key, 'svg'), 'button download-svg'), button('PDF vettoriale', () => download(key, 'pdf'), 'button download-pdf'), button('Sorgente DOT', () => download(key, 'dot'), 'button download-dot'));
      figure.setAttribute('aria-labelledby', captionId);
      return append(figure, append(el('div', 'diagram-heading'), caption, tools), viewport, el('figcaption', 'diagram-hint', 'Il testo mantiene una dimensione leggibile. Scorri il diagramma se supera lo spazio disponibile; SVG e PDF restano vettoriali.'));
    }
    function macroExample(item) {
      const step = macros.exampleStep(item.id, state().example);
      const panel = append(el('section', 'example-panel macro-example'), heading('h2', 'Segui BRAF · ' + selected().kind));
      const list = el('ol', 'journey');
      for (const [title, text, name] of [['Da dove arriviamo',step.input,'input'],['Che cosa cambia',step.action,'action'],['Che cosa portiamo avanti',step.result,'result']]) {
        list.append(append(el('li', 'journey-step journey-' + name), heading('h3', title), el('p', '', text)));
      }
      return append(panel, list, el('p', 'example-origin', 'Caso sintetico; associazioni, osservazioni ed esiti documentati. Le frasi didattiche non sono citazioni dell’output del modello.'));
    }
    function configuration() {
      const box = el('details', 'configuration-note');
      box.append(el('summary', '', 'Percorso predefinito e configurazioni opzionali'));
      box.append(el('p', '', 'Predefinito indica il codice senza opzioni documentali aggiuntive. focused-v1 è un profilo opzionale: non tutti i suoi comportamenti appartengono al percorso predefinito.'));
      const table = el('table', 'configuration-table');
      const head = el('tr'); for (const text of ['Componente','Predefinito','Opzioni e confronti']) { const th = el('th','',text); th.scope = 'col'; head.append(th); }
      table.append(append(el('thead'),head)); const body = el('tbody');
      for (const row of macros.configurations) body.append(append(el('tr'), ...row.map(text => el('td','',text))));
      table.append(body); const scroll = el('div','table-scroll'); scroll.tabIndex = 0; scroll.setAttribute('aria-label','Confronto delle configurazioni, scorribile'); scroll.append(table); box.append(scroll); return box;
    }
    function navigation(target, query) {
      target.replaceChildren(); const overview = phaseLink('panoramica', 'Vista d’insieme', 'nav-overview');
      if (state().phase === 'panoramica') overview.setAttribute('aria-current','page'); target.append(overview);
      for (const [index,item] of macros.items.entries()) {
        const link = phaseLink(item.id, (index + 1) + '. ' + item.title, 'nav-macro');
        if (state().phase === item.id) link.setAttribute('aria-current','page'); target.append(link);
      }
      const details = el('details','nav-details'); details.append(el('summary','','Approfondimenti · 18 passaggi'));
      const matches = api.model.searchPhases(query, data);
      details.open = !!query || data.phases.some(item => item.id === state().phase);
      for (const group of data.groups) {
        const phases = matches.filter(item => item.group === group.id); if (!phases.length) continue;
        const section = append(el('section','nav-group'),heading('h3',group.title));
        for (const phase of phases) {
          const link = phaseLink(phase.id, undefined, 'nav-phase');
          append(link,el('span','nav-number',phase.number),el('span','',phase.title));
          if (phase.id === state().phase) link.setAttribute('aria-current','page'); section.append(link);
        }
        details.append(section);
      }
      target.append(details); document.getElementById('no-results').hidden = matches.length > 0;
    }
    function overview(target) {
      target.append(append(el('section','intro'), heading('h1','Dal caso alla spiegazione, in sei macrofasi'),el('p','','Il sistema organizza il caso, recupera le GCA, analizza le fonti e distingue i diversi esiti dei controlli. Il dossier raccoglie il risultato; la spiegazione deve rimanergli fedele.')));
      const system = append(el('section','system-overview'),heading('h2','Leggere l’architettura'));
      system.append(append(el('div','system-preparation'),phaseLink('corpus','A monte: GCA derivate dal Knowledge Graph'),el('p','','Le associazioni candidate conservano argomenti, tipo di relazione e provenienza. Non sono già conclusioni sul caso.')));
      const list = el('ol','system-flow');
      for (const item of macros.items) list.append(append(el('li','system-step'),phaseLink(item.id,item.title,'system-title'),el('p','',item.short),el('p','system-transfer',item.transfer)));
      system.append(list);
      const branches = append(el('section','source-branches'),heading('h3','Tre percorsi delle fonti'));
      for (const [id,title,text] of [['melanoma','Pubblicazioni','Testo → selezione dei passaggi → Reader → controlli.'],['studio','Registri degli studi clinici','Informazioni di studio; percorso documentale predefinito o fatti strutturati con focused-v1.'],['diagnostica','Solo Knowledge Graph','Nessun documento associato: conservare il collegamento e la sua origine.']]) {
        const link = el('a','','Segui BRAF in questo percorso'); link.href = api.model.serialize({phase:'macro-caso',example:id,tab:'sintesi'});
        branches.append(append(el('section','source-branch'),heading('h4',title),el('p','',text),link));
      }
      system.append(branches);
      system.append(append(el('div','system-coordination'),phaseLink('runtime','Coordinamento trasversale'),el('p','','Controlli di risorse e avanzamento accompagnano l’intero percorso.')));
      target.append(system,paths(),macroExample(macros.items[0]),phaseLink('macro-caso','Inizia dalla comprensione del caso','button'),configuration());
      const details = el('details','overview-details'); details.append(el('summary','','Esplora i 18 passaggi di approfondimento'));
      const map = el('div','map');
      for (const phase of data.phases) map.append(button(phase.number + '. ' + phase.title,() => navigate({phase:phase.id,tab:'sintesi'}),'map-node ' + phase.type));
      details.append(map); target.append(details);
    }
    function rrfPanel(target) {
      target.append(diagram('rrf','Come RRF fonde due classifiche',macros.rrfFlow));
      target.append(el('p','', 'Esempio numerico didattico su passaggi A, B, C e D dello stesso documento. Le classifiche contengono anche altri passaggi: D è oltre i primi 25 in MedCPT e riceve zero da quel ramo. Non sono classifiche misurate su BRAF. Si sommano contributi di posizione, senza fare la media dei punteggi BM25 e MedCPT.'));
      const table = el('table','rrf-table'); const header = el('tr');
      for (const title of ['Passaggio','Rango BM25 strutturale','Rango MedCPT','Calcolo RRF','Somma']) {const th=el('th','',title); th.scope='col';header.append(th);}
      table.append(append(el('thead'),header));const body=el('tbody');
      for (const row of [...macros.rrf.rows].sort((a,b)=>b.score-a.score)) {
        const term=rank=>rank ? '1/(60+'+rank+')' : '0';
        body.append(append(el('tr'),el('td','',row.id),el('td','',row.structure || 'oltre 25'),el('td','',row.medcpt || 'oltre 25'),el('td','',term(row.structure)+' + '+term(row.medcpt)),el('td','',row.score.toFixed(8).replace('.',','))));
      }
      table.append(body);const scroll=el('div','table-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','Esempio numerico RRF, scorribile');scroll.append(table);target.append(scroll);
      target.append(el('p','', 'Ranghi da 1, costante 60, pesi uguali e fino a 25 elementi per classifica. Un passaggio assente contribuisce zero. I filtri precedono la fusione; la selezione finale applica anche i vincoli di sovrapposizione. Se MedCPT non è disponibile, il percorso ripiega su BM25 strutturale.'));
    }
    function clarification(item,brief=false){
      const note=item.clarification;
      if(!note)return null;
      const section=append(el('section','macro-clarification'),heading('h2',note.title));
      for(const text of brief?[note.brief]:note.paragraphs)section.append(el('p','',text));
      if(!brief)section.append(contractTable(note.rows.map(([name,description])=>({name,description}))));
      return section;
    }
    function render(item,target) {
      item=pathViews.macro(item,state().example);
      target.append(append(el('section','intro'),heading('h1',item.title),el('p','',item.lead)));
      const trail=el('nav','macro-trail');trail.setAttribute('aria-label','Percorso BRAF nelle sei macrofasi');
      for(const [index,macro] of macros.items.entries()) {const link=phaseLink(macro.id,String(index+1)+' · '+macro.title);if(macro.id===item.id)link.setAttribute('aria-current','step');trail.append(link);}
      target.append(trail,paths(),diagram(item.assetKey,'Trasformazioni della macrofase',item.flow));
      append(target,clarification(item));
      const concepts=append(el('section','macro-concepts'),heading('h2','Che cosa capire da questo schema'));const list=el('ul');for(const point of item.points)list.append(el('li','',point));concepts.append(list);target.append(concepts);
      if(item.id==='macro-fonti'&&state().example!=='diagnostica')rrfPanel(target);
      target.append(macroExample(item));
      if(item.id==='macro-verifiche') {
        const p=pathViews.profiles[state().example];
        target.append(append(el('section','detail-section'),heading('h2','Esito dell’esempio selezionato'),contractTable([
          {name:'Fonte',description:p.reference},{name:'Esito documentato',description:p.outcome.replace(/\n/g,'; ')},{name:'Limite',description:p.limit.replace(/\n/g,' ')}
        ])));
        const deep=el('details','verification-deep');deep.append(el('summary','','Condizioni dei controlli e percorsi alternativi'));
        deep.append(el('p','','Il dettaglio distingue citazioni invalide, astensioni, controlli strutturali e confronto semantico condizionale. Il riferimento tecnico EVIDENCE_DRUG riguarda le relazioni evidenza–farmaco; non è una verifica universale.'));
        deep.append(phaseLink('validazione','Apri la verifica approfondita per il percorso selezionato','detail-link'));target.append(deep);
      }
      if(item.id==='macro-dossier') {
        const entries = {
          melanoma: [
            ['Relazione cercata','BRAF V600K → descrizione dello studio.'],
            ['Fonte','Pubblicazione PubMed 28891408.'],
            ['Osservazione','Dabrafenib e trametinib in contesto adiuvante, melanoma di stadio III; varianti V600E oppure V600K.'],
            ['Controlli','Citazione autentica; supporto non attribuito alla relazione conservata.'],
            ['Limiti','Il caso è metastatico. Il risultato non viene trasferito automaticamente al caso né alla sola V600K; la differenza non è assunta come causa accertata dell’esito.']
          ],
          studio: [
            ['Relazione cercata','Studio NCT02279004 → gene BRAF.'],
            ['Fonte','Registro dello studio NCT02279004.'],
            ['Informazione osservata','Studio sulla genotipizzazione del plasma; condizioni registrate comprendenti carcinoma polmonare non a piccole cellule e melanoma.'],
            ['Controlli','Origine nel registro conservata; eleggibilità individuale non valutata.'],
            ['Limiti','La descrizione dello studio non costituisce prova di efficacia di dabrafenib o trametinib e non stabilisce la partecipazione del caso.']
          ],
          diagnostica: [
            ['Relazione cercata','FoundationOne CDx → gene BRAF.'],
            ['Fonte','Sola provenienza nel Knowledge Graph.'],
            ['Osservazione documentale','Assente: questo collegamento non ha un documento associato.'],
            ['Controlli','Nessuna citazione o verifica documentale attribuita.'],
            ['Limiti','Il livello è il gene BRAF, non la variante V600K. La presenza del test nel grafo non significa che sia stato eseguito nel caso.']
          ]
        };
        target.append(append(el('section','dossier-example'),heading('h2','Leggere la voce dell’esempio selezionato'),contractTable(entries[state().example].map(([name,description])=>({name,description}))),el('p','','Diagramma e tabella seguono la stessa relazione selezionata.')));
      }
      target.append(configuration());
      const details=el('details','macro-details');details.append(el('summary','','Apri i passaggi di questa macrofase'));
      for(const id of item.phases) {const phase=data.phases.find(x=>x.id===id);details.append(phaseLink(id,phase.title,'detail-link'));}
      target.append(details);
    }
    function print(book,brief=false) {
      for(const original of macros.items) {
        const item=brief?pathViews.brief(original,state().example):pathViews.macro(original,state().example);
        const page=el('section','print-macro');append(page,heading('h1',item.title),el('p','',item.lead),parseSVG(assets.svgs[item.assetKey]),clarification(item,brief),macroExample(item));
        if(!brief&&item.id==='macro-fonti'&&state().example!=='diagnostica') append(page,heading('h2','Esempio numerico RRF'),parseSVG(assets.svgs.rrf),el('p','','Classifiche didattiche, non risultati misurati su BRAF. S(u) = somma di 1/(60+rango), con ranghi da 1.'));
        book.append(page);
      }
    }
    function brief(target){target.append(append(el('section','intro'),heading('h1','Architettura · lettura breve'),el('p','','Sei macrofasi con un esempio trasversale. Le figure seguono la fonte selezionata; le frasi di raccordo sono spiegazioni didattiche, gli esiti sono quelli documentati.')),paths());const body=el('div','brief-body');print(body,true);target.append(body);}
    return { navigation, overview, render, print, brief, download };
  }
  root.ArchitectureMacroUI={create};
})(globalThis);
