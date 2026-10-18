(function (root) {
  'use strict';
  const node = (id, title, kind = 'codice', detail = title, shape = 'box') => ({ id, title, kind, detail, shape });
  const flow = (nodes, edges, ranks = []) => ({ nodes, edges, ranks, direction: 'TB' });
  const rrf = {
    constant: 60, depth: 25,
    rows: [
      { id: 'A', structure: 1, medcpt: 3 },
      { id: 'B', structure: 2, medcpt: 1 },
      { id: 'C', structure: 3, medcpt: 2 },
      { id: 'D', structure: 4, medcpt: null }
    ].map(row => ({ ...row, score: (row.structure ? 1 / (60 + row.structure) : 0) + (row.medcpt ? 1 / (60 + row.medcpt) : 0) }))
  };
  const items = [
    {
      id: 'macro-caso', title: 'Comprensione del caso', short: 'Dal testo ai campi',
      lead: 'Questa fase trasforma il testo clinico in informazioni utilizzabili dalla ricerca: malattia, gene, variante e intervento di interesse. Il Case Parser propone i campi; i controlli verificano che abbiano un riscontro nel testo e che siano presenti i dati richiesti. Serve a costruire la ricerca a partire da ciò che è effettivamente dichiarato, evitando di colmare le informazioni mancanti con supposizioni. Alla fase successiva passa il caso strutturato ammesso alla ricerca.',
      transfer: 'Caso strutturato, ancorato e ammesso alla ricerca',
      phases: ['input', 'parser', 'ancoraggio', 'ammissibilita'],
      points: ['Gene e variante restano distinti: BRAF è il gene, V600K è la variante.', 'Dabrafenib e trametinib sono l’intervento oggetto della ricerca; non diventano automaticamente terapie già ricevute.', 'Un campo assente rimane assente. L’ammissione alla ricerca non è un giudizio clinico.'],
      flow: flow([
        node('testo', 'Caso sintetico · estratto\nDiagnosi: melanoma metastatico\nProfilo molecolare: BRAF V600K\nIntervento da cercare: dabrafenib e trametinib', 'dato'),
        node('parser', 'Case Parser\nEstrazione con modello linguistico', 'modello'),
        node('campi', 'Campi estratti\nMalattia = melanoma metastatico\nGene = BRAF · Variante = V600K\nIntervento = dabrafenib e trametinib\nTerapie pregresse = non dichiarate', 'dato'),
        node('testo-check', 'Ancoraggio al testo\nOgni valore ha un riscontro letterale', 'controllo'),
        node('gate', 'Informazioni sufficienti\nper la ricerca?', 'controllo', 'Il gate controlla i dati minimi richiesti dalla domanda.', 'diamond'),
        node('caso', 'Caso verificato\nPronto per il recupero GCA', 'risultato'),
        node('chiarire', 'Chiarire o fermare\nDati assenti o incoerenti', 'limite')
      ], [['testo','parser','testo libero'],['parser','campi','campi proposti'],['campi','testo-check','valori e citazioni'],['testo-check','gate','dati controllati'],['gate','caso','sì'],['gate','chiarire','no']])
    },
    {
      id: 'macro-recupero', title: 'Recupero GCA', short: 'Dalle identità alle relazioni',
      lead: 'Questa fase cerca, tra le associazioni candidate derivate dal Knowledge Graph e chiamate GCA, quelle pertinenti al caso strutturato. L’Entity Resolution riconduce i nomi alle identità disponibili; il recupero filtra le relazioni compatibili e ordina quelle ammesse per specificità. Serve a restringere la ricerca mantenendo visibile quanto ogni relazione corrisponde al caso: un collegamento al gene BRAF resta distinto da uno specifico per V600K. Alla fase successiva passano le relazioni candidate e i riferimenti alle loro fonti.',
      transfer: 'Relazioni candidate con livello di specificità e tipo di fonte',
      phases: ['corpus', 'piano', 'retrieval'],
      points: ['Compatibilità: la relazione può entrare nella ricerca, secondo la famiglia e i dati disponibili?', 'Specificità: tra le relazioni compatibili, quali corrispondono più precisamente alle identità cercate?', 'L’ordinamento è lessicografico: distingue identità dell’intervento, variante, gene e malattia. Non equivale a un punteggio di efficacia.', 'Una relazione su BRAF non diventa una relazione specifica per V600K. Recuperare una relazione non significa confermarla.'],
      flow: flow([
        node('caso', 'Caso verificato\nBRAF V600K · melanoma metastatico', 'dato'),
        node('identita', 'Normalizzazione ed Entity Resolution\nUniformare le forme riconosciute\nNome o alias → identità, se risolta\nGene e variante restano collegati\nIl contesto metastatico resta visibile'),
        node('gca', 'GCA preparate dal Knowledge Graph\nRelazioni, argomenti e provenienza', 'dato'),
        node('compatibili', 'Compatibilità\nFiltri dipendenti dalla famiglia\nMalattia, gene–variante, intervento', 'controllo'),
        node('escluse', 'Non compatibili\nEsclusione con motivo', 'limite'),
        node('specificita', 'Specificità delle relazioni ammesse\nOrdinamento lessicografico\nNessuna promozione da gene a variante'),
        node('variante', 'Esempio documentato\nBRAF V600K → descrizione dello studio\nPubblicazione 28891408', 'risultato'),
        node('gene', 'Esempi documentati a livello di gene\nStudio NCT02279004 → BRAF\nFoundationOne CDx → BRAF', 'risultato')
      ], [['caso','identita','campi'],['identita','compatibili','identità riconosciute'],['gca','compatibili','relazioni candidate'],['compatibili','escluse','non ammesse'],['compatibili','specificita','ammesse'],['specificita','variante','specificità dichiarata'],['specificita','gene','specificità dichiarata']], [['variante','gene']])
    },
    {
      id: 'macro-fonti', title: 'Analisi delle fonti', short: 'Tre percorsi, origini distinte',
      lead: 'Questa fase esamina da dove proviene ciascuna relazione recuperata. Per le fonti documentali il percorso predefinito raggiunge il contenuto, seleziona i passaggi pertinenti e li sottopone al Reader, che produce un’osservazione con citazione oppure si astiene. Serve a passare da un collegamento nel grafo a un contenuto esaminabile. Pubblicazioni, registri e collegamenti senza documento seguono percorsi distinti: alla fase successiva passano osservazioni, informazioni di studio o sola provenienza, con i rispettivi limiti.',
      transfer: 'Osservazioni con citazione, informazioni di registro o sola provenienza nel grafo',
      phases: ['risoluzione', 'unita', 'selezione', 'reader'],
      points: ['Per le fonti documentali il percorso predefinito seleziona passaggi con BM25 strutturale + MedCPT e li fonde con RRF.', 'Il Reader descrive ciò che dice la fonte; può anche astenersi. Il contesto vicino aiuta la lettura senza diventare automaticamente testo citabile.', 'Il registro descrive uno studio, senza dimostrare efficacia o eleggibilità individuale.', 'In focused-v1 i registri risolti sono trattati come fatti strutturati senza chiamata al Reader generativo: è una differenza di configurazione.'],
      flow: flow([
        node('riferimenti','Relazioni recuperate\nQuale fonte è associata?', 'dato'),
        node('paper','Pubblicazioni\nRisoluzione del testo\nSuddivisione in passaggi', 'dato'),
        node('trial','Registri degli studi clinici\nCopia del registro\nParti identificabili', 'dato'),
        node('kg','Solo Knowledge Graph\nNessun documento associato', 'dato'),
        node('selezione','Percorso predefinito documentale\nBM25 strutturale + MedCPT → RRF\nSelezione dei passaggi'),
        node('reader','Reader\nOsservazione con citazione\noppure astensione', 'modello'),
        node('facts','Opzione focused-v1 · solo registri\nFatti strutturati collegati alla relazione\nSenza lettura generativa', 'codice'),
        node('origine','Conservare origine e limite\nNessuna citazione inventata', 'risultato'),
        node('uscita','Ai controlli e al dossier\nContenuto e tipo di fonte restano distinti', 'risultato')
      ], [['riferimenti','paper','pubblicazione'],['riferimenti','trial','registro'],['riferimenti','kg','nessun documento'],['paper','selezione','passaggi'],['trial','selezione','default'],['trial','facts','solo se configurato','dashed'],['selezione','reader','materiale scelto'],['reader','uscita','osservazione o astensione'],['facts','uscita','contesto di studio','dashed'],['kg','origine','sola provenienza'],['origine','uscita','limite conservato']], [['paper','trial','kg']])
    },
    {
      id: 'macro-verifiche', title: 'Verifiche', short: 'Citazione, struttura e significato',
      lead: 'Questa fase stabilisce che cosa si può attribuire alla relazione dopo l’analisi della fonte. Quando è presente una citazione, ne controlla l’autenticità; applica poi i controlli previsti per il tipo di relazione e conserva la decisione risultante. Serve a distinguere una frase realmente presente nella fonte dal supporto alla relazione cercata: la prima non garantisce il secondo. Il confronto semantico aggiuntivo si applica solo nelle condizioni previste. Alla fase successiva passano esiti distinti e limiti espliciti.',
      transfer: 'Esiti distinti dei controlli, senza trasformare in conferma ciò che rimane incerto',
      phases: ['validazione', 'gates', 'status'],
      points: ['Autenticazione: il testo citato deve essere letterale e appartenere al passaggio selezionato della fonte corretta.', 'Per EVIDENCE_DRUG: documento autorizzato, identità di gene, variante e intervento, legami tra gli argomenti e ambito della proposizione.', 'Il confronto semantico aggiuntivo è richiesto solo per EVIDENCE_DRUG, con osservazione ammessa e controllo strutturale superato. Le altre famiglie seguono il proprio validatore.', 'Supporto, contraddizione, assenza di supporto, informazione insufficiente ed errore tecnico restano esiti diversi. Nessuno di questi sostituisce una valutazione clinica individuale.'],
      flow: flow([
        node('proposta','Reader\nCitazione e relazione osservata', 'dato'),
        node('autentica','Autenticazione e validazione\nCitazione letterale\nFonte e passaggio corretti', 'controllo'),
        node('assenza','Citazione invalida\no astensione\nNessun supporto attribuito', 'limite'),
        node('famiglia','EVIDENCE_DRUG?', 'controllo', 'La policy dipende dalla famiglia della relazione.', 'diamond'),
        node('ordinario','Altre famiglie\nValidatore specifico\nNessun confronto aggiuntivo', 'controllo'),
        node('struttura','EVIDENCE_DRUG\nStruttura e identità\nProvenienza e legami', 'controllo'),
        node('blocco','Incompatibile o non risolta\nConfronto non eseguito', 'limite'),
        node('semantica','Solo con struttura PASS\nConfronto semantico\nRelazione ↔ proposizione', 'modello'),
        node('esiti','Regole di ammissione ed esiti\nSupporto pieno o parziale\nContraddizione · nessun supporto\nInformazione insufficiente\nNon verificabile · errore tecnico', 'risultato')
      ], [['proposta','autentica','osservazione'],['autentica','assenza','invalida o assente'],['autentica','famiglia','osservazione ammessa'],['famiglia','ordinario','altra famiglia'],['famiglia','struttura','EVIDENCE_DRUG'],['struttura','blocco','incompatibile o incerta'],['struttura','semantica','PASS'],['ordinario','esiti','controlli della famiglia'],['semantica','esiti','valutazione + regole']], [['ordinario','struttura']])
    },
    {
      id: 'macro-dossier', title: 'Dossier', short: 'Una voce ricostruibile',
      lead: 'Questa fase organizza le informazioni raccolte in un dossier. Ogni voce mantiene insieme la relazione cercata, la fonte, l’eventuale osservazione, i controlli eseguiti e i limiti emersi. Serve a rendere il risultato ricostruibile: chi legge deve poter capire da dove proviene un’informazione e quali conclusioni consente. Pubblicazioni, registri e sola provenienza nel grafo restano riconoscibili. Alla presentazione passa questo contenuto organizzato, senza trasformare l’assenza di verifica in una conferma.',
      transfer: 'Dossier di riferimento per la spiegazione',
      phases: ['dossier'],
      points: ['La relazione cercata e l’osservazione della fonte sono due informazioni distinte.', 'Il dossier mantiene anche risultati senza supporto e relazioni del solo grafo, con il loro significato esplicito.', 'La voce BRAF qui mostrata è una sintesi leggibile dell’esempio documentato; non aggiunge una conclusione clinica.'],
      flow: flow([
        node('paper','Pubblicazioni\nOsservazioni e controlli', 'dato'),
        node('trial','Registri\nInformazioni dello studio', 'dato'),
        node('kg','Knowledge Graph\nRelazioni senza documento', 'dato'),
        node('raccogliere','Comporre il dossier\nConservare le origini separate'),
        node('voce','Esempio di voce · BRAF V600K\nRelazione: variante → descrizione dello studio\nFonte: pubblicazione 28891408\nOsservazione: adiuvante, stadio III, V600E oppure V600K\nControlli: citazione autentica; supporto non attribuito\nLimiti: caso metastatico; nessun trasferimento automatico', 'risultato')
      ], [['paper','raccogliere','osservazioni'],['trial','raccogliere','contesto di studio'],['kg','raccogliere','origine nel grafo'],['raccogliere','voce','relazione + fonte + osservazione + controlli + limiti']], [['paper','trial','kg']])
    },
    {
      id: 'macro-presentazione', title: 'Presentazione', short: 'Dal dossier alla spiegazione fedele',
      lead: 'Questa fase trasforma il dossier in una spiegazione leggibile. Ogni osservazione conservata riceve una spiegazione dedicata; quando una relazione comprende più studi, il modello aggiunge un confronto. Le schede delle fonti e i dati osservati rimangono disponibili accanto al testo. Il codice verifica la copertura delle osservazioni e i vincoli su identità, fonti, citazioni, quantità e limiti. La completezza del significato delle parafrasi richiede una valutazione dedicata. Un testo deterministico verificato separatamente offre un percorso alternativo.',
      transfer: 'Spiegazione utilizzabile con i limiti del dossier',
      phases: ['narratore', 'fedelta', 'runtime'],
      points: ['Il dossier esiste prima della spiegazione e rimane il riferimento.', 'Ogni osservazione conservata ha una spiegazione; più studi per relazione richiedono un confronto.', 'Titoli, citazioni e dati osservati vengono conservati esattamente; le regole controllano anche eventuali omissioni di voci.', 'Il rifiuto della prosa attiva la verifica separata del ripiego deterministico.', 'La conformità ai controlli sulla narrazione rimane distinta dalla correttezza scientifica e dalla valutazione clinica.'],
      flow: flow([
        node('dossier','Dossier di riferimento\nRelazioni, osservazioni, esiti e limiti', 'dato'),
        node('catalogo','Proiezione del dossier\nCaso, osservazioni, fonti, controlli e limiti'),
        node('modello','Modello linguistico\nSpiegazione di ogni osservazione\nConfronto tra studi della stessa relazione', 'modello'),
        node('struttura','1 · Copertura e legame con il dossier\nOgni osservazione spiegata · confronto richiesto\nSchede e dati conservati esattamente', 'controllo'),
        node('contenuto','2 · Vincoli sulla spiegazione\nFonti · citazioni · quantità\nStati · polarità · limiti · raccomandazioni', 'controllo'),
        node('mostrare','Presentazione accettata\nTesto conforme ai controlli implementati', 'risultato'),
        node('alternativa','Preparare il ripiego deterministico\nTesto costruito dal dossier', 'codice'),
        node('esatto','3 · Verifica separata del ripiego\nRicostruzione e confronto esatto', 'controllo'),
        node('ripiego','Mostrare il ripiego verificato\nOrigine deterministica esplicita', 'risultato'),
        node('limite','Solo dossier strutturato\nTesti respinti conservati tra gli esiti', 'limite')
      ], [['dossier','catalogo','contenuti da presentare'],['catalogo','modello','contenuti ammessi'],['modello','struttura','spiegazione'],['struttura','contenuto','struttura valida'],['contenuto','mostrare','controlli superati'],['struttura','alternativa','formato non valido'],['contenuto','alternativa','testo respinto'],['modello','alternativa','generazione indisponibile','dashed'],['dossier','alternativa','contenuti del ripiego','dashed'],['alternativa','esatto','testo distinto'],['esatto','ripiego','conforme'],['esatto','limite','non conforme']], [['mostrare','alternativa'],['ripiego','limite']])
    }
  ];
  const rrfFlow = flow([
    node('passaggi','Passaggi dello stesso documento\nFiltri di ammissibilità prima della fusione', 'dato'),
    node('bm25','BM25 strutturale\nBM25 × prior di sezione × fattore di sezione\nInizio classifica: A, B, C, D, …'),
    node('medcpt','MedCPT\nPertinenza semantica\nInizio classifica: B, C, A, …\nD è oltre i primi 25', 'encoder'),
    node('fusione','Reciprocal Rank Fusion · RRF\nS(u) = Σ 1 / (60 + rango)\nRanghi da 1 · pesi uguali\nFino a 25 elementi per classifica'),
    node('ordine','Punteggi dei passaggi mostrati\nB = 0,03252247\nA = 0,03226646\nC = 0,03200205\nD = 0,01562500', 'risultato'),
    node('scelta','Selezione dei passaggi\nVincoli di sovrapposizione e top-k\nAl Reader: normalmente fino a 5 passaggi', 'risultato')
  ], [['passaggi','bm25','parole e struttura'],['passaggi','medcpt','significato'],['bm25','fusione','posizioni'],['medcpt','fusione','posizioni'],['fusione','ordine','somma dei contributi'],['ordine','scelta','non misura di supporto']], [['bm25','medcpt']]);
  const exampleSteps = {
    melanoma: [
      ['Dal testo vengono estratti e ancorati malattia, gene, variante e intervento.', 'Caso controllato: melanoma metastatico; BRAF V600K; interesse per dabrafenib e trametinib.'],
      ['Si segue la relazione documentata BRAF V600K → descrizione dello studio. Recuperarla non equivale a validarla.', 'GCA da approfondire: BRAF V600K → descrizione dello studio; fonte PubMed 28891408.'],
      ['Per la pubblicazione sono documentati cinque passaggi selezionati e un’osservazione con citazione. Il calcolo numerico RRF è un’illustrazione didattica, non la classifica misurata per questa fonte.', 'Osservazione BRAF: dabrafenib e trametinib nel contesto adiuvante dello stadio III; V600E oppure V600K.'],
      ['Nell’esempio la citazione è autentica e il supporto alla relazione non è attribuito. La relazione verso la descrizione dello studio segue i controlli della propria famiglia, senza attribuirle automaticamente quelli delle relazioni evidenza–farmaco.', 'Esito documentato BRAF: citazione autentica; supporto non attribuito. La differenza di contesto non è presentata come causa accertata dell’esito.'],
      ['Si raccoglie la relazione con la fonte, l’osservazione, gli esiti dei controlli e i limiti.', 'Voce BRAF nel dossier: fonte 28891408; osservazione adiuvante di stadio III; citazione autentica; supporto non attribuito.'],
      ['Il diagramma descrive la presentazione controllata del codice corrente. La frase seguente è una parafrasi didattica del dossier, non una citazione dell’output generato.', 'Parafrasi BRAF: “La fonte contiene una citazione autentica, ma non è stato attribuito supporto alla relazione cercata; il risultato non è trasferibile automaticamente al caso metastatico.”']
    ],
    studio: [
      ['Lo stesso caso BRAF V600K viene organizzato e controllato. Lo studio non è dichiarato nel testo iniziale.', 'Caso controllato: melanoma metastatico e BRAF V600K; nessuno studio aggiunto ai dati del caso.'],
      ['La ricerca recupera il collegamento al registro a livello di gene, senza renderlo specifico per la variante.', 'GCA da approfondire: studio NCT02279004 sulla genotipizzazione del plasma → BRAF.'],
      ['Nell’esempio documentato il registro usa fatti strutturati, senza chiamate al Reader generativo: è il percorso opzionale dedicato ai registri. Il percorso predefinito usa invece selezione e Reader.', 'Contenuto del registro collegato a BRAF: NCT02279004; studio sulla genotipizzazione del plasma; condizioni registrate comprendenti il melanoma.'],
      ['Il registro viene mantenuto come contesto di studio. Il suo collegamento a BRAF non equivale a una prova di efficacia o all’ammissione del caso.', 'Esito BRAF–registro: informazioni dello studio; eleggibilità individuale non valutata.'],
      ['La relazione entra nella sezione degli studi con la propria fonte e i propri limiti.', 'Voce BRAF nel dossier: NCT02279004, titolo e condizioni registrate; eleggibilità individuale non valutata.'],
      ['La spiegazione deve mantenere il significato di contesto di studio. Questa è una parafrasi didattica.', 'Parafrasi BRAF: “Lo studio NCT02279004 è collegato al gene BRAF; questo non stabilisce efficacia né eleggibilità individuale.”']
    ],
    diagnostica: [
      ['Il caso contiene BRAF V600K. Il test non viene aggiunto alla storia clinica perché non è dichiarato nel testo.', 'Caso controllato: melanoma metastatico e BRAF V600K; FoundationOne CDx non dichiarato.'],
      ['La ricerca recupera il collegamento diagnostico al gene BRAF, mantenendo il livello di specificità del record.', 'GCA recuperata: FoundationOne CDx → BRAF; nessun documento associato.'],
      ['Il percorso non risolve, seleziona o legge una pubblicazione assente e non produce citazioni.', 'Informazione BRAF del solo Knowledge Graph: FoundationOne CDx → BRAF; origine nel grafo conservata.'],
      ['Non viene attribuita una verifica documentale a questa associazione. L’assenza di documento non è una confutazione scientifica.', 'Esito FoundationOne CDx–BRAF: sola provenienza nel Knowledge Graph; nessuna citazione documentale.'],
      ['La relazione viene conservata nella sezione del solo grafo con il limite esplicito.', 'Voce BRAF nel dossier: FoundationOne CDx → BRAF; provenienza nel grafo; nessun documento associato.'],
      ['La spiegazione conserva l’origine e l’assenza di documento. Questa è una parafrasi didattica.', 'Parafrasi BRAF: “Il Knowledge Graph collega FoundationOne CDx a BRAF; per questo collegamento non è presente una fonte documentale.”']
    ]
  };
  function exampleStep(id, example) {
    const index = items.findIndex(item => item.id === id);
    if (index < 0) throw new Error('Macrofase sconosciuta');
    const steps = exampleSteps[example] || exampleSteps.melanoma;
    return { input: index ? steps[index - 1][1] : 'Caso sintetico: melanoma metastatico; BRAF V600K; dabrafenib e trametinib come intervento da cercare.', action: steps[index][0], result: steps[index][1] };
  }
  const configurations = [
    ['Selezione dei passaggi', 'BM25 strutturale + MedCPT, fusione RRF. Se MedCPT non è disponibile, ripiego esplicito su BM25 strutturale.', 'BM25 strutturale può essere scelto da solo come confronto.'],
    ['Registri degli studi clinici', 'Percorso documentale con selezione e Reader; le informazioni restano contesto di studio.', 'focused-v1: fatti strutturati del registro, senza nuova lettura generativa.'],
    ['Pianificazione dei documenti', 'Non si assume il piano focused di scelta e differimento dei documenti.', 'focused-v1 abilita piano dei documenti, intenzione di selezione e gestione dedicata del materiale da leggere.'],
    ['Contesto del Reader', 'Contesto adiacente abilitato, usato solo quando serve a risolvere riferimenti locali.', 'Espansione con ulteriore lettura opzionale; indice gerarchico abilitabile separatamente.'],
    ['Confronto semantico', 'Per EVIDENCE_DRUG, dopo osservazione ammessa e struttura superata.', 'Non è una verifica universale introdotta automaticamente da focused-v1.']
  ];
  const sources = [
    ['backend/research_pipeline/casecontext/prompt.py', 'SYSTEM_PROMPT'],
    ['backend/research_pipeline/casecontext/pipeline.py', 'build_retrieval_case_context'],
    ['backend/research_pipeline/retrieval/kg_retrieval.py', '_specificity_order_key'],
    ['backend/research_pipeline/retrieval/kg_retrieval.py', '_match_candidate'],
    ['backend/research_pipeline/retrieval/canonical_rrf.py', 'rrf_scores'],
    ['backend/research_pipeline/retrieval/canonical_rrf.py', 'select_rrf'],
    ['backend/research_pipeline/retrieval/live_sourceunit_selection.py', 'select_live_papers_for_association'],
    ['backend/research_pipeline/retrieval/document_plan.py', 'focused_enabled'],
    ['backend/research_pipeline/enrichment/context_reader.py', 'ContextPolicy'],
    ['backend/research_pipeline/enrichment/validator_v3.py', 'validate_enrichment_v3'],
    ['backend/research_pipeline/enrichment/verification_policy.py', 'policy_for'],
    ['backend/research_pipeline/enrichment/document_verification.py', 'structural_verify'],
    ['backend/research_pipeline/enrichment/document_verification.py', 'admit'],
    ['backend/research_pipeline/orchestrator.py', 'if candidate.get("relation_family") == "EVIDENCE_DRUG":'],
    ['backend/research_pipeline/narrative/controlled_narrator.py', 'call_controlled_narrator'],
    ['backend/research_pipeline/narrative/controlled.py', 'verify_controlled'],
    ['backend/research_pipeline/narrative/stage_runner.py', 'deterministic_verification = verify_controlled'],
    ['backend/research_pipeline/terminology/case_resolution.py', 'def resolve_case'],
    ['backend/research_pipeline/retrieval/normalization.py', 'def alteration_identity'],
    ['backend/research_pipeline/enrichment/semantic_alignment.py', 'def render_request'],
    ['backend/research_pipeline/enrichment/semantic_contract.py', 'def admission_blockers']
  ];
  const clarifications = {
    'macro-recupero': {
      title: 'Normalizzazione e identità: due operazioni diverse',
      paragraphs: [
        'Normalizzare significa rendere confrontabili forme testuali secondo regole esplicite, per esempio maiuscole, spazi o una notazione proteica riconosciuta. Risolvere l’identità significa collegare il nome a un’entità del vocabolario, usando nomi e alias ammessi. Somiglianza delle parole e identità biologica non sono la stessa cosa.',
        'Il sistema conserva il valore originale, l’identità eventualmente riconosciuta e lo stato di risoluzione. Il gene è risolto prima della variante: V600K va interpretata nel contesto di BRAF. Il contesto della malattia non viene cancellato e un nome non risolto non riceve un’identità inventata.'
      ],
      rows: [
        ['Melanoma metastatico', 'Nell’esempio: concetto melanoma riconosciuto; “metastatico” conservato come contesto separato.'],
        ['BRAF e V600K', 'Nell’esempio: identità del gene e della variante riconosciute; la coppia rimane esplicita. BRAF da solo non equivale a BRAF V600K.'],
        ['Dabrafenib e trametinib', 'Nell’esempio: stringa combinata non risolta come identità unica; valore originale mantenuto. Non viene sostituita con un singolo farmaco.']
      ],
      brief: 'Normalizzare rende confrontabili le forme testuali; risolvere collega nomi e alias a identità riconosciute. Nell’esempio melanoma conserva il contesto metastatico, V600K resta legata a BRAF e la stringa dabrafenib e trametinib rimane non risolta come identità unica. Originale e stato di risoluzione restano disponibili.'
    },
    'macro-verifiche': {
      title: 'Come funziona il confronto semantico',
      paragraphs: [
        'Qui “semantico” significa confrontare il significato della relazione cercata con la proposizione della fonte e il suo contesto. È diverso da MedCPT, che ordina i passaggi per pertinenza. Il confronto aggiuntivo si attiva solo per le relazioni evidenza–farmaco, dopo un’osservazione ammessa e un controllo strutturale superato; le altre famiglie usano il proprio validatore.',
        'Una chiamata separata al modello riceve la relazione strutturata e il testo ancorato alla fonte, senza il verdetto del Reader. Valuta dimensioni distinte: relazione e direzione, attribuzione agli autori o ad altri lavori, risultato osservato o semplice descrizione, ambito molecolare, popolazione, intervento, inferenza e incertezza.',
        'Il modello restituisce giudizi strutturati e passaggi letterali a loro sostegno. Il codice controlla formato, ancoraggio e condizioni di ammissione: una corrispondenza dichiarata dal modello non basta da sola. Un ambito più ristretto può consentire solo supporto limitato, alle condizioni previste. Il confronto non decide se una terapia sia adatta al paziente.'
      ],
      rows: [
        ['Corrispondenza o opposizione', 'Richiedono un risultato diretto, con argomenti e ambiti confrontabili; la sola presenza dei nomi non dimostra la relazione.'],
        ['Assenza di supporto e informazioni insufficienti', 'Nel confronto semantico, un risultato nullo esplicito è diverso dal silenzio della fonte. Disegno dello studio, criteri di ammissione o relazione non riportata non diventano automaticamente un risultato negativo.'],
        ['Esempi della pagina', 'Questa è la regola del componente, non la dichiarazione che sia stato chiamato in ogni esempio. La relazione BRAF V600K verso la descrizione dello studio non è una relazione evidenza–farmaco; registro e sola provenienza seguono i propri percorsi.']
      ],
      brief: 'Il confronto semantico aggiuntivo riguarda solo relazioni evidenza–farmaco, con osservazione ammessa e struttura superata. Un modello separato confronta relazione, ambiti e contesto della fonte; il codice verifica passaggi letterali e regole di ammissione. Silenzio della fonte e risultato nullo restano distinti. Non è il controllo finale della presentazione.'
    },
    'macro-presentazione': {
      title: 'Quando la presentazione è accettata o respinta',
      paragraphs: [
        'Prima del dossier si controllano le evidenze: autenticità della citazione, struttura della relazione e confronto semantico dove previsto. Dopo il dossier si controlla la spiegazione: il riferimento è ciò che il dossier contiene. Sono verifiche con oggetti e scopi distinti.',
        'Il dossier è già costruito e rimane il riferimento. A essere verificata è la spiegazione che lo presenta. “Accettata” significa conforme ai controlli implementati, anche quando il dossier contiene assenza di supporto, incertezza o sola provenienza nel grafo.',
        'Prima si verificano formato, identità, ordine, copertura e legame con il dossier ricevuto. Poi si applicano controlli su entità, fonti, citazioni, quantità, stati, polarità, raccomandazioni e limiti critici riconoscibili. La prosa libera conserva un limite di verifica semantica generale.',
        'La verifica finale usa regole deterministiche. In caso di rifiuto il testo alternativo precostruito viene verificato separatamente con un confronto esatto, e il suo successo rimane distinto da quello del modello. Il dossier strutturato resta disponibile se entrambi i testi falliscono.'
      ],
      rows: [
        ['Prima del dossier · evidenze', 'Il confronto semantico evidenza–farmaco riguarda la corrispondenza della relazione con la fonte, nel ramo previsto.'],
        ['Dopo il dossier · spiegazione', 'Il verificatore della narrazione applica controlli deterministici sul testo. Il confronto semantico a monte non verifica automaticamente questa prosa.'],
        ['Struttura e legame con l’ingresso', 'Ogni osservazione conservata deve avere una spiegazione. Più studi per relazione richiedono un confronto riferito a tutte le osservazioni. Schede e dati vengono confrontati esattamente con l’ingresso; più passaggi dello stesso studio restano distinti.'],
        ['Vincoli sul contenuto', 'Fonti, citazioni e quantità restano attribuite alle proprie voci; le regole cercano alterazioni di stati, polarità, limiti critici e raccomandazioni. L’assenza di osservazioni conservate resta distinta dal mancato recupero dei documenti.'],
        ['Presentazione accettata', 'Spiegazione conforme ai controlli implementati sul dossier. Il superamento delle regole rimane distinto da una prova di equivalenza semantica generale.'],
        ['Alternativa deterministica accettata', 'Spiegazione del modello respinta o indisponibile; alternativa costruita dal codice e verificata con confronto esatto. L’origine alternativa rimane distinta.'],
        ['Testo respinto', 'Formato, identità o copertura errati, oppure violazioni dei vincoli rilevate nella prosa. Un errore nel confronto esatto respinge il ripiego deterministico. Rimane la vista strutturata del dossier.'],
        ['Esempi didattici di alterazioni', 'Trasformare “eleggibilità non valutata” in “paziente eleggibile”, o presentare un collegamento solo grafo come conferma documentale, modifica i fatti. Sono esempi di violazione, non errori osservati nell’esecuzione documentata.']
      ],
      brief: 'Il modello spiega il contenuto del dossier; il codice verifica formato, identità, copertura, fonti, citazioni, quantità e vincoli riconoscibili. La prosa libera conserva un limite di verifica semantica generale. Il ripiego deterministico viene verificato separatamente con confronto esatto. Il dossier resta disponibile anche quando la spiegazione viene respinta.'
    }
  };
  for (const item of items) item.clarification = clarifications[item.id];
  const api = { items, rrf, rrfFlow, exampleStep, configurations, sources };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.ArchitectureMacros = api;
})(globalThis);
