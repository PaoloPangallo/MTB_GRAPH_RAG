(function(root){
  'use strict';
  const node=(id,title,kind='codice',detail=title)=>({id,title,kind,detail});
  const flow=(nodes,edges)=>({nodes,edges,direction:'TB',ranks:[]});
  const profiles={
    melanoma:{label:'Pubblicazione',reference:'Pubblicazione 28891408',relation:'BRAF V600K → descrizione dello studio',observation:'Adiuvante, melanoma di stadio III\nV600E oppure V600K',outcome:'Citazione autentica\nSupporto non attribuito alla relazione',limit:'Nessun trasferimento automatico\nal caso metastatico o alla sola V600K'},
    studio:{label:'Registro di studio clinico',reference:'Registro NCT02279004',relation:'Studio NCT02279004 → BRAF',observation:'Studio sulla genotipizzazione del plasma\nCondizioni comprendenti il melanoma',outcome:'Informazioni dello studio\nEleggibilità individuale non valutata',limit:'Associazione di studio\nNon è una prova di efficacia'},
    diagnostica:{label:'Solo Knowledge Graph',reference:'FoundationOne CDx → BRAF',relation:'FoundationOne CDx → gene BRAF',observation:'Nessuna osservazione documentale\nNessun documento associato',outcome:'Sola provenienza nel Knowledge Graph\nNessuna verifica documentale attribuita',limit:'Livello del gene, non della variante\nIl test non è dichiarato nel caso'}
  };
  const clean=text=>text.replace(/EVIDENCE_DRUG/g,'relazioni evidenza–farmaco');
  function dossierFlow(p){return flow([
    node('relazione',p.relation,'dato'),node('fonte',p.reference,'dato'),node('raccolta','Comporre la voce del dossier\nConservare la natura della fonte'),
    node('voce','Relazione: '+p.relation+'\nFonte: '+p.reference+'\n'+p.observation+'\n'+p.outcome+'\nLimite: '+p.limit,'risultato')
  ],[['relazione','raccolta','relazione cercata'],['fonte','raccolta','origine'],['raccolta','voce','osservazione + controlli + limiti']]);}
  function sourceFlow(example){const p=profiles[example];
    if(example==='diagnostica')return flow([node('relazione',p.relation,'dato'),node('nessuna','Nessun riferimento documentale associato','controllo'),node('conservare','Conservare il collegamento e la sua origine\nNon simulare selezione, lettura o citazioni'),node('esito',p.outcome,'risultato')],[['relazione','nessuna','riferimenti del record'],['nessuna','conservare','nessun documento'],['conservare','esito','provenienza nel grafo']]);
    const nodes=[node('fonte',p.reference,'dato'),node('risolvere','Raggiungere il contenuto della fonte\nConservare documento e posizione'),node('selezione','Percorso predefinito\nBM25 strutturale + MedCPT → RRF'),node('reader','Reader\nOsservazione con citazione o astensione','modello'),node('esito',example==='studio'?'Informazioni del registro\nNessuna efficacia o eleggibilità dedotta':'Osservazione della pubblicazione\nDa sottoporre ai controlli','risultato')];
    const edges=[['fonte','risolvere','riferimento'],['risolvere','selezione','unità della fonte'],['selezione','reader','passaggi selezionati'],['reader','esito','contenuto della fonte']];
    if(example==='studio'){nodes.push(node('fatti','Configurazione opzionale del registro\nFatti strutturati, senza Reader generativo'));edges.push(['risolvere','fatti','opzione, non default','dashed'],['fatti','esito','informazioni di studio','dashed']);}
    return flow(nodes,edges);
  }
  function verificationFlow(example){const p=profiles[example];
    if(example==='studio')return flow([node('fonte',p.reference,'dato'),node('autenticazione','1 · Autenticazione della citazione\nDefault: controllare testo e fonte\nEsempio opzionale: fatti strutturati, nessuna citazione Reader','controllo'),node('relazione','2 · Controlli sulla relazione\nPreservare identità e origine dello studio\nNon dedurre efficacia o eleggibilità','controllo'),node('decisione','3 · Decisione\nGate documentato: ambiguo\nEleggibilità individuale non valutata','risultato')],[['fonte','autenticazione','distinguere i due percorsi'],['autenticazione','relazione','contenuto e provenienza'],['relazione','decisione','esiti e limiti conservati']]);
    if(example==='diagnostica')return flow([node('origine',p.reference,'dato'),node('autenticazione','1 · Autenticazione della citazione\nNon applicabile: nessun documento','controllo'),node('relazione','2 · Controlli sulla relazione\nConservare identità e provenienza nel grafo','controllo'),node('decisione','3 · Decisione\nConservare il collegamento nel grafo\nVerifica documentale non applicabile','risultato')],[['origine','autenticazione','percorso senza documento'],['autenticazione','relazione','nessuna citazione da validare'],['relazione','decisione','origine e limite conservati']]);
    return flow([node('fonte',p.reference,'dato'),node('autenticazione','1 · Autenticazione della citazione\nTesto letterale e fonte corretta','controllo'),node('relazione','2 · Controlli sulla relazione\nIdentità, campi e significato\nSecondo il tipo di relazione','controllo'),node('decisione','3 · Decisione\n'+(example==='studio'?'Conservare il contesto dello studio\nEleggibilità individuale non valutata':'Attribuire solo il supporto consentito\nNell’esempio: supporto non attribuito'),'risultato')],[['fonte','autenticazione','contenuto disponibile'],['autenticazione','relazione','contenuto utilizzabile'],['relazione','decisione','esiti distinti dei controlli']]);
  }
  function macro(item,example){
    const p=profiles[example]||profiles.melanoma; const selected=profiles[example]?example:'melanoma';
    let graph=item.flow;
    if(item.id==='macro-recupero'){
      graph=JSON.parse(JSON.stringify(item.flow));
      graph.nodes=graph.nodes.filter(n=>!['variante','gene'].includes(n.id));
      graph.edges=graph.edges.filter(e=>!['variante','gene'].includes(e[1]));graph.ranks=[];
      graph.nodes.push(node('selezionata',p.relation+'\n'+p.reference+'\n'+(selected==='melanoma'?'Specificità della variante':'Specificità del gene, non V600K'),'risultato'));
      graph.edges.push(['specificita','selezionata','relazione seguita nell’esempio']);
    }
    if(item.id==='macro-fonti')graph=sourceFlow(selected);
    if(item.id==='macro-verifiche')graph=verificationFlow(selected);
    if(item.id==='macro-dossier')graph=dossierFlow(p);
    if(item.id==='macro-presentazione'){
      graph=JSON.parse(JSON.stringify(item.flow));
      graph.nodes.find(n=>n.id==='dossier').title='Voce del dossier · '+p.reference+'\n'+p.outcome;
      graph.nodes.find(n=>n.id==='mostrare').title='Presentazione accettata dai controlli\n'+p.reference+'\n'+p.limit;
    }
    const points=item.id==='macro-verifiche'?[
      selected==='diagnostica'?'Non esiste una citazione da autenticare: si conserva la provenienza del collegamento.':selected==='studio'?'Nel percorso predefinito si autentica la citazione del Reader. Nell’esempio opzionale sono conservati fatti strutturati del registro, senza una citazione del Reader da autenticare.':'Autenticazione: la citazione deve essere letterale e appartenere alla fonte corretta.',
      selected==='studio'?'I controlli sul registro mantengono distinta la descrizione dello studio da efficacia ed eleggibilità individuale.':'I controlli sulla relazione dipendono dal tipo di collegamento; non ogni associazione richiede lo stesso confronto.',
      'La decisione finale conserva esiti e limiti. Le condizioni dei controlli e i percorsi alternativi sono negli approfondimenti.'
    ]:item.points.map(clean);
    return {...item,flow:graph,assetKey:item.id+'--'+selected,points};
  }
  const sensitive=['retrieval','risoluzione','unita','selezione','reader','validazione','gates','status','dossier','narratore','fedelta'];
  function detail(phase,example){
    if(example==='melanoma'||!sensitive.includes(phase.id))return {...phase,assetKey:phase.id};
    const p=profiles[example];if(!p)return {...phase,assetKey:phase.id};
    let graph,how,explanation;
    if(phase.id==='retrieval'){
      const template=root.ArchitectureMacros?.items.find(x=>x.id==='macro-recupero');
      if(!template)throw new Error('Dati delle macrofasi mancanti');
      graph=macro(template,example).flow;
      explanation='Il recupero segue la relazione selezionata a livello di gene: '+p.relation+'. Non la rende specifica per V600K.';
    }else if(phase.id==='dossier'){graph=dossierFlow(p);explanation='La voce del dossier conserva la relazione selezionata, la sua fonte e i limiti propri di questa origine.';
    }else if(['narratore','fedelta'].includes(phase.id)){
      graph=JSON.parse(JSON.stringify(phase.flow));graph.nodes.find(n=>n.id==='dossier').title=p.reference+'\n'+p.outcome;
      explanation='Il componente opera sulla voce selezionata: '+p.reference+'. La presentazione conserva '+p.limit.replace(/\n/g,' ').toLowerCase()+'.';
    }else if(example==='diagnostica'){
      const operations={risoluzione:'Nessun documento da risolvere',unita:'Nessun testo da suddividere',selezione:'Nessun passaggio da selezionare',reader:'Nessuna lettura da eseguire',validazione:'Nessuna citazione da autenticare',gates:'Nessun gate documentale da applicare',status:'Esporre la sola provenienza nel grafo'};
      graph=flow([node('associazione',p.relation,'dato'),node('assenza',operations[phase.id],'controllo'),node('origine','Conservare relazione, origine e limite\nNon inventare una citazione','risultato','Il sistema non simula la lettura di un documento assente e non inventa citazioni; conserva la provenienza nel grafo.')],[['associazione','assenza','nessun documento associato'],['assenza','origine','percorso solo grafo']]);
      explanation=operations[phase.id]+': il record FoundationOne CDx–BRAF non contiene un riferimento documentale. Questo passaggio non produce una verifica della letteratura.';
    }else{
      const graphs={
        risoluzione:flow([node('fonte',p.reference,'dato'),node('risolvere','Cercare la copia del registro\nPreservare identità e origine'),node('record','Record di studio disponibile\nTitolo, sintesi e condizioni','risultato')],[['fonte','risolvere','riferimento dello studio'],['risolvere','record','contenuto del registro']]),
        unita:flow([node('record',p.reference,'dato'),node('parti','Identificare le parti del registro\nTitolo · sintesi · descrizione · condizioni'),node('unita','Parti riconducibili al record consultato','risultato')],[['record','parti','contenuto strutturato'],['parti','unita','testo e origine']]),
        selezione:sourceFlow(example),
        reader:flow([node('fonte',p.reference,'dato'),node('reader','Percorso predefinito\nReader: leggere che cosa dice il registro','modello'),node('fatti','Percorso opzionale, usato nell’esempio\nOrganizzare i dati già presenti nel registro'),node('esito','Informazioni dello studio\nEleggibilità individuale non valutata','risultato')],[['fonte','reader','passaggi scelti'],['fonte','fatti','opzione per i registri','dashed'],['reader','esito','descrizione con citazione o astensione'],['fatti','esito','dati dello studio','dashed']]),
        validazione:flow([node('fonte',p.reference,'dato'),node('citazione','Percorso predefinito\nVerificare la frase citata e la sua fonte\nNell’esempio opzionale: conservare l’origine dei dati','controllo'),node('relazione','Controllare il collegamento allo studio\nTenere distinti descrizione e risultati','controllo'),node('esito','Esito registrato: da chiarire\nEleggibilità individuale non valutata','risultato')],[['fonte','citazione','contenuto del registro'],['citazione','relazione','origine conservata'],['relazione','esito','esiti e limiti']]),
        gates:flow([node('record',p.reference,'dato'),node('gate','Gate operativo dell’esempio\nAmbiguo: nessuna osservazione ammessa','controllo'),node('distinzione','Tenere separato il contenuto del registro\nL’eleggibilità individuale non è valutata','risultato')],[['record','gate','esiti del percorso documentale'],['gate','distinzione','nessun giudizio di eleggibilità']]),
        status:flow([node('record',p.reference,'dato'),node('operativo','Esito operativo documentato: ambiguo\nNon è lo stato di reclutamento dello studio'),node('dossier','Voce del registro nel dossier\nEleggibilità individuale non valutata','risultato')],[['record','operativo','esito del gate'],['operativo','dossier','contesto e limiti separati']])
      };
      graph=graphs[phase.id];explanation='Il passaggio riguarda il registro NCT02279004, non una pubblicazione. Il record descrive uno studio sulla genotipizzazione del plasma, collegato al gene BRAF.';
    }
    how=['La relazione selezionata è '+p.relation+'. Il collegamento resta a livello di gene.',example==='studio'?'Il percorso predefinito seleziona il contenuto e usa il Reader. L’opzione dedicata ai registri usa fatti strutturati; l’esempio documentato appartiene a quest’ultimo percorso.':'Non sono disponibili documenti associati: selezione, lettura e verifiche documentali non vengono simulate.',p.outcome.replace(/\n/g,'; ')+'. '+p.limit.replace(/\n/g,' ').toLowerCase()+'.'];
    if(['narratore','fedelta'].includes(phase.id))how=phase.how;
    return {...phase,flow:graph,assetKey:phase.id+'--'+example,summary:explanation,explanation,how,workedExample:undefined,
      input:[{name:'Relazione selezionata',description:p.relation},{name:'Origine',description:p.reference}],
      output:[{name:'Contenuto conservato',description:p.outcome.replace(/\n/g,'; ')},{name:'Limite',description:p.limit.replace(/\n/g,' ')}],
      controls:how,failures:[p.limit.replace(/\n/g,' ')+'.'],design:explanation};
  }
  function entries(data,macros){
    const result=[];
    for(const example of Object.keys(profiles))for(const item of macros.items){
      for(const view of [macro(item,example),brief(item,example)])result.push({key:view.assetKey,title:item.title+' · '+profiles[example].label,flow:view.flow});
    }
    for(const example of ['studio','diagnostica'])for(const phase of data.phases.filter(x=>sensitive.includes(x.id))){const view=detail(phase,example);result.push({key:view.assetKey,title:phase.title+' · '+profiles[example].label,flow:view.flow});}
    return result;
  }
  function brief(item,example){
    const view=macro(item,example),p=profiles[example];let graph=view.flow;
    const chain=(labels)=>flow(labels.map((label,i)=>node('step'+i,label,i===0?'dato':i===labels.length-1?'risultato':'codice')),labels.slice(1).map((_,i)=>['step'+i,'step'+(i+1),'']));
    if(item.id==='macro-caso')graph=chain(['Caso sintetico\nMelanoma metastatico · BRAF V600K\nInteresse: dabrafenib e trametinib','Case Parser\nEstrarre campi e citazioni del caso','Ancoraggio e ammissione\nVerificare testo e dati richiesti','Caso strutturato ammesso alla ricerca']);
    if(item.id==='macro-recupero')graph=chain(['Identità del caso\nGene–variante e contesto conservati','Compatibilità delle relazioni\nFiltrare secondo la famiglia','Specificità\nOrdinare le relazioni ammesse',p.relation+'\n'+p.reference]);
    if(item.id==='macro-fonti'&&example!=='diagnostica')graph=chain([p.reference,example==='studio'?'Predefinito: selezione e Reader\nOpzione: fatti strutturati del registro':'Selezione BM25 strutturale + MedCPT\nRRF → passaggi al Reader',example==='studio'?'Informazioni dello studio\nNell’esempio: fatti strutturati':'Osservazione con citazione\noppure astensione',p.outcome]);
    if(item.id==='macro-dossier')graph=chain([p.relation+'\n'+p.reference,'Raccogliere la voce\nRelazione · fonte · osservazione\nControlli e limiti',p.outcome+'\n'+p.limit]);
    if(item.id==='macro-presentazione')graph=flow([
      node('dossier',p.reference+'\nDossier: fatti, esiti e limiti','dato'),
      node('piano','Modello: spiegare ogni osservazione\nConfrontare più studi della stessa relazione\nRipiego deterministico disponibile'),
      node('verifica','Verificare copertura e contenuto\nSchede e dati esatti · ogni osservazione spiegata\nFonti · quantità · stati · limiti','controllo'),
      node('accettata','Presentazione accettata\nConforme ai controlli implementati','risultato'),
      node('ripiego','Preparare il ripiego\nVerificarlo con confronto esatto','controllo'),
      node('alternativa','Mostrare il ripiego verificato','risultato'),
      node('respinta','Testo respinto\nSolo dossier strutturato','limite')
    ],[['dossier','piano','contenuti ammessi'],['piano','verifica','testo proposto'],['verifica','accettata','controlli superati'],['verifica','ripiego','testo respinto'],['piano','ripiego','indisponibile','dashed'],['ripiego','alternativa','conforme'],['ripiego','respinta','non conforme']]);
    return {...view,flow:graph,assetKey:'breve-'+view.assetKey};
  }
  const api={profiles,macro,brief,detail,entries,verificationFlow};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.ArchitecturePaths=api;
})(globalThis);
