'use strict';
// Source-authored explanations. Graph nodes name implemented operations or data,
// never a generic input / processing / check / output scaffold.
const n = (id, title, kind = 'codice', detail = title, shape = 'box') => ({ id, title, kind, detail, shape });
const f = (nodes, edges, ranks = [], direction = 'TB') => ({ nodes, edges, ranks, direction });
module.exports = {
  corpus: {
    explanation: 'Il Knowledge Graph contiene collegamenti tra profili molecolari, descrizioni di evidenza, farmaci, studi e test. La preparazione li trasforma in relazioni candidate ricercabili, mantenendo gli argomenti del collegamento e la sua origine.',
    how: ['La materializzazione legge nodi e archi e produce record di relazione: soggetto, predicato, oggetto e riferimenti documentali, quando presenti.', 'Le relazioni complementari possono essere collegate solo attraverso la stessa evidenza e gli identificatori previsti dalla regola di composizione. La somiglianza del testo non basta.', 'Il risultato serve al recupero: la presenza di un collegamento nel grafo non è una verifica della pubblicazione.'],
    flow: f([
      n('nodi','Nodi del Knowledge Graph\nVarianti · evidenze · farmaci · studi','dato'),
      n('archi','Archi e riferimenti\nQuali entità sono collegate?','dato'),
      n('materializzare','Materializzare le GCA\nSoggetto + relazione + oggetto'),
      n('collegare','Comporre relazioni complementari\nSolo con riferimenti di evidenza coincidenti'),
      n('provenienza','Conservare nodi, archi e fonte\nOgni relazione resta ricostruibile','controllo'),
      n('corpus','Corpus delle relazioni candidate\nPronto per compatibilità e specificità','risultato')
    ],[['nodi','materializzare','entità'],['archi','materializzare','collegamenti'],['materializzare','collegare','record di relazione'],['collegare','provenienza','origine dei record collegati'],['provenienza','corpus','relazioni con provenienza']], [['nodi','archi']])
  },
  input: {
    explanation: 'L’avvio conserva il testo originale del caso e crea il contesto di esecuzione che accompagnerà l’analisi. In questo punto non vengono ancora interpretati gene, variante o malattia.',
    how: ['Il testo viene mantenuto come riferimento per verificare successivamente le informazioni estratte dal Case Parser.', 'L’orchestratore inizializza stato del lavoro, registrazione degli eventi e budget delle chiamate; poi passa il testo al parser.'],
    flow: f([
      n('testo','Testo clinico originale\nDescrizione e domanda da approfondire','dato'),
      n('inizio','Aprire l’analisi\nCollegare il lavoro al caso'),
      n('risorse','Inizializzare il budget\nLimiti delle chiamate ai modelli'),
      n('registrazione','Registrare avvio e avanzamento\nConservare il testo originale'),
      n('parser','Inviare il testo al Case Parser\nLa lettura strutturata inizia dopo','risultato')
    ],[['testo','inizio','testo invariato'],['inizio','risorse','impostazioni'],['risorse','registrazione','contesto del lavoro'],['registrazione','parser','testo + caso']])
  },
  parser: {
    explanation: 'Il Case Parser usa un modello linguistico per trasformare il testo in campi strutturati. Deve indicare anche le parole da cui li ha ricavati: estrarre “BRAF” non è ancora dimostrare che quel dato sia corretto.',
    how: ['La richiesta specifica i campi attesi: malattia, gene, alterazione, interventi e intento della domanda, con citazioni letterali del caso.', 'La risposta deve rispettare lo schema richiesto. Testo libero o una struttura non valida non vengono trattati come un caso correttamente estratto.', 'I valori mancanti rimangono nulli o liste vuote. Gene e variante restano associati nello stesso biomarcatore; l’intervento da valutare non diventa una terapia pregressa.'],
    flow: f([
      n('testo','Testo clinico\n«Melanoma metastatico … BRAF V600K»','dato'),
      n('richiesta','Richiesta di estrazione\nCampi attesi + citazioni obbligatorie'),
      n('modello','Case Parser · modello linguistico\nPropone valori e riferimenti al testo','modello'),
      n('schema','Risposta nello schema richiesto?','controllo','Controllo del formato e degli argomenti della risposta.','diamond'),
      n('campi','Caso strutturato proposto\nMalattia: melanoma metastatico\nBiomarcatore: gene BRAF, variante V600K\nIntervento cercato: dabrafenib e trametinib','risultato'),
      n('errore','Risposta inutilizzabile\nNessun caso estratto da inviare alla ricerca','limite')
    ],[['testo','richiesta','testo'],['richiesta','modello','istruzioni + schema'],['modello','schema','risposta'],['schema','campi','valida'],['schema','errore','non valida']])
  },
  ancoraggio: {
    explanation: 'Il Match Verifier cerca nel testo originale le citazioni indicate dal parser e verifica che sostengano il valore estratto. È codice deterministico: non chiede allo stesso modello di confermare la propria risposta.',
    how: ['Per ciascun campo si cerca la citazione letterale. Se compare una sola volta, la posizione viene ricostruita dal testo.', 'Se la citazione compare più volte, gli offset devono disambiguare l’occorrenza; altrimenti il campo resta incerto.', 'Gene e variante sono controllati anche con riferimenti separati. Un valore non dichiarato resta assente, anziché essere completato.'],
    flow: f([
      n('campo','Valore del parser + citazione\nEsempio: variante V600K, citazione «V600K»','dato'),
      n('originale','Testo clinico originale','dato'),
      n('ricerca','Cercare la citazione letterale\nContare le occorrenze nel testo'),
      n('posizione','Ricostruire o disambiguare la posizione\nGli offset aiutano solo se coerenti'),
      n('valore','Confrontare valore e citazione\nControllare separatamente gene e variante','controllo'),
      n('esiti','Campo ancorato · non corrispondente · incerto\nCampo non valorizzato → assente','risultato')
    ],[['campo','ricerca','citazione proposta'],['originale','ricerca','testo autorevole'],['ricerca','posizione','occorrenze'],['posizione','valore','citazione localizzata'],['valore','esiti','esito per campo']], [['campo','originale']])
  },
  ammissibilita: {
    explanation: 'Avere campi presenti nel testo non basta per avviare una ricerca significativa. Il gate considera le menzioni verificate, il loro ruolo, eventuali contraddizioni e i dati richiesti dalla domanda.',
    how: ['La catena deterministica distingue menzioni positive, negate, incerte o storiche e rileva contraddizioni e istruzioni estranee al contenuto clinico.', 'La sufficienza dipende dall’intento: per valutare un intervento deve esserci l’intervento oggetto della domanda. La malattia non viene inventata e non è un requisito universale per qualsiasi ricerca.', 'Se il caso non è utilizzabile, il recupero non parte; il sistema restituisce il motivo concreto, come un dato necessario mancante o un contesto contraddittorio.'],
    flow: f([
      n('menzioni','Menzioni ancorate al testo\nTipo, ruolo e stato dell’asserzione','dato'),
      n('semantica','Verifiche deterministiche sulle menzioni\nNegazione · ruolo clinico · tipo di entità','controllo'),
      n('contraddizioni','Rilevare contraddizioni\nSeparare istruzioni e fatti clinici','controllo'),
      n('sufficienza','Dati sufficienti per questa domanda?\nValutazione di terapia → intervento richiesto','controllo','Il controllo dipende dall’intento dichiarato.','diamond'),
      n('ammesso','Proiettare solo i fatti accettati\nIl recupero GCA può iniziare','risultato'),
      n('fermo','Recupero non avviato\nDati mancanti, ambigui, fuori ambito\no contraddittori: motivo esplicito','limite')
    ],[['menzioni','semantica','menzioni'],['semantica','contraddizioni','menzioni accettate o escluse'],['contraddizioni','sufficienza','fatti + intento'],['sufficienza','ammesso','sì'],['sufficienza','fermo','no']])
  },
  piano: {
    explanation: 'L’Entity Resolution prepara il confronto tra le parole del caso e le entità del Knowledge Graph. Non è una nuova lettura clinica: collega i nomi a identità riconosciute, conserva il contesto e rende espliciti i nomi che non riesce a risolvere.',
    how: ['La proiezione passa alla ricerca soltanto menzioni accettate dai controlli precedenti. I valori scartati dal parser non vengono reinseriti nella domanda.', 'Per la malattia si separano concetto riconosciuto e contesto residuo: riconoscere melanoma non autorizza a cancellare “metastatico”.', 'Il gene viene risolto prima della variante; la variante è interpretata nel contesto del suo gene. Per gli interventi si cercano nomi e alias nel vocabolario.', 'L’uscita conserva valore originale, identità trovata e stato di risoluzione. Un nome non riconosciuto resta visibile: non viene trasformato in un’identità inventata.'],
    workedExample: [
      {name:'«melanoma metastatico»',description:'Concetto melanoma: DOID:1909. “metastatico” è conservato come contesto separato (metastatic), non eliminato.'},
      {name:'«BRAF»',description:'Identità del gene riconosciuta: NCBIGene:673.'},
      {name:'«V600K» associata a BRAF',description:'Variante riconosciuta nel contesto del gene: CIViCVariant:563. Il legame BRAF–V600K rimane esplicito.'},
      {name:'«dabrafenib e trametinib»',description:'Nell’esempio documentato la stringa combinata è UNMAPPED: non è risolta come identità unica. Il valore originale rimane disponibile per la ricerca.'}
    ],
    flow: f([
      n('menzioni','Fatti accettati del caso\nMalattia · biomarcatori · intervento','dato'),
      n('proiezione','Proiezione per il recupero\nEscludere le menzioni non accettate'),
      n('malattia','Risolvere la malattia\nConcetto ontologico + contesto separato'),
      n('gene','Risolvere il gene\nNome o sinonimo → identità del gene'),
      n('variante','Risolvere la variante nel suo gene\nConservare la coppia gene–variante'),
      n('intervento','Cercare nomi e alias dell’intervento\nNon forzare un’identità assente'),
      n('contesto','Contesto di ricerca\nValori originali + identità + stati\nContesto di malattia e coppie molecolari','risultato'),
      n('nonrisolti','Nomi non risolti o ambigui\nRestano dichiarati, senza equivalenze inventate','limite')
    ],[['menzioni','proiezione','solo dati accettati'],['proiezione','malattia','malattia'],['proiezione','gene','biomarcatore'],['gene','variante','gene riconosciuto + alterazione'],['proiezione','intervento','intervento cercato'],['malattia','contesto','concetto + contesto'],['variante','contesto','gene + variante'],['intervento','contesto','identità o valore originale'],['intervento','nonrisolti','nome non riconosciuto'],['nonrisolti','contesto','stato conservato']], [['malattia','gene','intervento']])
  },
  retrieval: {
    explanation: 'Il recupero confronta il contesto del caso con le relazioni candidate del grafo. La compatibilità decide quali relazioni ammettere; la specificità ordina soltanto quelle già ammesse.',
    how: ['I filtri dipendono dalla famiglia della relazione e dalle identità disponibili: non applicano indistintamente gli stessi requisiti a pubblicazioni, studi e test.', 'L’ordinamento lessicografico considera le caratteristiche di specificità, mantenendo la differenza tra gene, variante e contesto. Non è un punteggio di efficacia.', 'Dopo raggruppamento e limiti per famiglia, ogni relazione mantiene la propria fonte: riferimento documentale oppure sola provenienza nel grafo.'],
    flow: f([
      n('caso','Contesto del caso\nIdentità, coppie molecolari e valori originali','dato'),
      n('gca','Corpus GCA\nRelazioni con argomenti e provenienza','dato'),
      n('filtri','Filtrare per compatibilità\nRegole specifiche della famiglia','controllo'),
      n('escluse','Relazioni non compatibili\nEscluse con il motivo del confronto','limite'),
      n('ordine','Ordinare le relazioni compatibili\nSpecificità lessicografica'),
      n('gruppi','Raggruppare record equivalenti\nApplicare i limiti per famiglia'),
      n('fonti','Relazioni da approfondire\nPubblicazione · registro · solo grafo','risultato')
    ],[['caso','filtri','domanda'],['gca','filtri','relazioni'],['filtri','escluse','incompatibili'],['filtri','ordine','compatibili'],['ordine','gruppi','ordine di specificità'],['gruppi','fonti','relazioni selezionate']], [['caso','gca']])
  },
  risoluzione: {
    explanation: 'La relazione del grafo può indicare una pubblicazione o uno studio, ma il riferimento non è ancora testo leggibile. Il resolver cerca il contenuto associato e registra esattamente quale fonte è disponibile.',
    how: ['Il sistema prova prima la copia disponibile localmente; se manca, il percorso autorizzato tenta il recupero attraverso la sorgente prevista.', 'La disponibilità distingue testo completo, abstract, registro e contenuto non disponibile. Un identificatore bibliografico non viene presentato come se fosse un testo letto.', 'Le relazioni senza documento seguono il percorso del solo grafo: non si inventa un articolo per farle attraversare il Reader.'],
    flow: f([
      n('id','Riferimento nell’associazione\nPubMed, PMC o registro NCT','dato'),
      n('cache','Esiste una copia utilizzabile?','controllo','Prima si consulta il contenuto locale disponibile.','diamond'),
      n('copia','Caricare la copia della fonte'),
      n('remoto','Tentare il recupero autorizzato\nSolo se la copia manca'),
      n('contenuto','Contenuto con identità della fonte\nTesto completo · abstract · registro','risultato'),
      n('indisponibile','Contenuto non disponibile\nIl riferimento non diventa prova letta','limite')
    ],[['id','cache','riferimento'],['cache','copia','sì'],['cache','remoto','no'],['copia','contenuto','contenuto disponibile'],['remoto','contenuto','fonte raggiunta'],['remoto','indisponibile','recupero fallito']], [['copia','remoto']])
  },
  unita: {
    explanation: 'Il contenuto della fonte viene suddiviso in unità citabili, mantenendo il legame con il documento e la posizione. Il Reader potrà citare un passaggio identificabile, non una frase senza origine.',
    how: ['Il caricatore interpreta il formato disponibile: testo di abstract, struttura dell’articolo, PDF locale o parti del registro.', 'Ogni unità conserva testo, documento, tipo e localizzatore, quando ricostruibile: sezione, paragrafo, frase o pagina.', 'Gli identificatori distinguono le occorrenze: due passaggi con testo uguale in punti diversi non devono perdere la propria posizione.'],
    flow: f([
      n('documento','Contenuto risolto + formato\nArticolo, abstract, PDF o registro','dato'),
      n('parsing','Interpretare la struttura del documento'),
      n('segmenti','Estrarre unità della fonte\nFrasi · paragrafi · tabelle · didascalie'),
      n('posizioni','Associare documento e posizione\nSezione, frase o pagina disponibili'),
      n('occorrenze','Distinguere le occorrenze\nTesto uguale non implica stessa posizione'),
      n('unita','Unità selezionabili e citabili\nTesto + fonte + posizione','risultato')
    ],[['documento','parsing','formato'],['parsing','segmenti','struttura'],['segmenti','posizioni','testo'],['posizioni','occorrenze','origine'],['occorrenze','unita','unità identificabili']])
  },
  selezione: {
    explanation: 'La selezione cerca, dentro ciascun documento, i passaggi più pertinenti alla relazione da approfondire. Il percorso predefinito combina una classifica lessicale strutturale e una classifica semantica mediante RRF.',
    how: ['BM25 strutturale pesa la corrispondenza lessicale con prior e fattore di sezione. MedCPT ordina i passaggi per pertinenza semantica.', 'I filtri di ammissibilità precedono la fusione. RRF somma 1/(60+rango), con ranghi da uno e fino a 25 risultati per classifica; non confronta direttamente i punteggi delle due scale.', 'La selezione finale applica top-k e vincoli di sovrapposizione. Se MedCPT non è disponibile, si ripiega su BM25 strutturale. focused-v1 aggiunge pianificazione dei documenti e regole dedicate al materiale da leggere.'],
    flow: f([
      n('domanda','Relazione cercata + unità del documento','dato'),
      n('filtri','Escludere unità non ammissibili\nPrima della fusione','controllo'),
      n('bm25','BM25 strutturale\nParole × prior e fattore di sezione'),
      n('dense','MedCPT\nPertinenza semantica','encoder'),
      n('rrf','Reciprocal Rank Fusion\nSomma di 1 / (60 + rango)'),
      n('top','Selezionare fino a top-k passaggi\nApplicare vincoli di sovrapposizione'),
      n('reader','Unità autorizzate per il Reader','risultato')
    ],[['domanda','filtri','unità e relazione'],['filtri','bm25','unità ammissibili'],['filtri','dense','unità ammissibili'],['bm25','rrf','posizioni nella classifica'],['dense','rrf','posizioni nella classifica'],['rrf','top','ordine fuso'],['bm25','top','ripiego se MedCPT non disponibile','dashed'],['top','reader','passaggi selezionati']], [['bm25','dense']])
  },
  reader: {
    explanation: 'Il Reader produce una relazione osservata nella fonte e una citazione che la accompagna. L’osservazione è distinta dalla relazione cercata nel grafo: deve descrivere ciò che il testo permette di dire, oppure astenersi.',
    how: ['La richiesta contiene la relazione da esaminare e i passaggi selezionati. Il modello restituisce soggetti, intervento, contesto e citazione, oppure un’astensione.', 'Il contesto adiacente può chiarire riferimenti locali, ma rimane separato dai passaggi autorizzati alla citazione.', 'Il predefinito tratta anche il registro attraverso selezione e Reader. focused-v1 usa invece fatti strutturati per i registri risolti. Le relazioni del solo grafo non producono citazioni.'],
    flow: f([
      n('evidenza','Passaggi da leggere\nDa qui si può ricavare la citazione','dato'),
      n('contesto','Testo vicino al passaggio\nAiuta a capire riferimenti e contesto','dato'),
      n('lettore','Reader · modello linguistico\nLeggere che cosa afferma la fonte','modello'),
      n('osservazione','Descrizione di ciò che dice la fonte\nCon il passaggio citato','risultato'),
      n('astensione','Informazioni insufficienti\nIl Reader si astiene','limite'),
      n('registro','Informazioni di uno studio registrato','dato'),
      n('organizzare','Opzione per i registri\nOrganizzare i dati già presenti'),
      n('informazioni','Informazioni dello studio\nCon origine e limiti conservati','risultato'),
      n('solo-grafo','Collegamento presente nel grafo','dato'),
      n('origine','Conservare il collegamento\nE la sua origine nel grafo','risultato')
    ],[['evidenza','lettore','passaggi scelti'],['contesto','lettore','aiuto alla lettura','dashed'],['lettore','osservazione','descrizione proposta'],['lettore','astensione','testo insufficiente'],['registro','evidenza','percorso predefinito'],['registro','organizzare','percorso opzionale','dashed'],['organizzare','informazioni','dati dello studio','dashed'],['solo-grafo','origine','sola provenienza']])
  },
  validazione: {
    explanation: 'Le verifiche rispondono a domande diverse: la citazione è autentica? L’osservazione è coerente con il testo? La fonte sostiene la relazione cercata? Superare il primo controllo non implica superare gli altri.',
    how: ['Il validatore ritrova la citazione letterale nell’unità selezionata e ne controlla l’appartenenza al documento; verifica inoltre gli argomenti dell’osservazione.', 'Per EVIDENCE_DRUG si verificano provenienza autorizzata, identità di gene, variante e intervento e legami nella proposizione. Struttura incompatibile e struttura non risolta fermano il confronto semantico.', 'Il confronto semantico aggiuntivo parte solo con osservazione ammessa e struttura PASS. Le altre famiglie usano il proprio validatore. Supporto, contraddizione, assenza di supporto e incertezza non vengono fusi in un solo sì/no.'],
    flow: f([
      n('citazione','Frase citata e fonte di origine','dato'),
      n('letterale','La frase è presente\nnel passaggio della fonte corretta?','controllo'),
      n('osservazione','Le entità descritte nell’osservazione\nSono presenti nella frase?','controllo'),
      n('famiglia','Quale relazione stiamo verificando?','controllo','Ogni tipo di relazione segue controlli specifici.','diamond'),
      n('altri','Per gli altri tipi di relazione\nApplicare i controlli adatti alla fonte'),
      n('struttura','Relazione tra evidenza e farmaco\nControllare identità, origine e collegamenti','controllo'),
      n('semantica','Se i controlli precedenti sono superati\nConfrontare il significato della relazione\nCon ciò che afferma la fonte','modello'),
      n('fermo','Dati incompatibili o incompleti\nConservare il motivo del limite','limite'),
      n('ammissione','Esito sulla relazione\nSupporto pieno o limitato · contraddizione\nAssenza di supporto · informazioni insufficienti','risultato')
    ],[['citazione','letterale','testo e origine'],['letterale','osservazione','frase autentica'],['osservazione','famiglia','osservazione verificata'],['famiglia','altri','altro tipo'],['famiglia','struttura','evidenza–farmaco'],['struttura','semantica','controlli superati'],['struttura','fermo','da chiarire'],['altri','ammissione','esiti dei controlli'],['semantica','ammissione','confronto e regole']], [['altri','struttura']])
  },
  gates: {
    explanation: 'Le regole deterministiche non rileggono liberamente le fonti. Ricevono soltanto osservazioni ammesse al gate e valutano la relazione secondo l’intento della domanda e la direzione dell’evidenza.',
    how: ['L’adattatore ammette al gate soltanto esiti di validazione accettati con supporto forte/pieno. Un’astensione o un supporto non attribuito non viene promosso a evidenza valida.', 'La valutazione distingue ricerca di possibili interventi e valutazione di un intervento indicato. Per quest’ultima confronta la direzione della relazione con il segnale documentale ammesso.', 'Gli esiti del gate e il supporto documentale conservato nel dossier sono informazioni distinte: nell’esempio BRAF il gate è ambiguo per assenza di osservazioni ammesse, mentre la relazione nel dossier ha supporto non attribuito.'],
    workedExample: [{name:'Citazione della pubblicazione 28891408',description:'Autentica, ma supporto non attribuito alla relazione: non viene ammessa come segnale positivo al gate.'},{name:'Esito del gate per quella relazione',description:'AMBIGUOUS, con NO_VALIDATED_ENRICHMENT_AVAILABLE e direzione NO_DOCUMENT_SIGNAL. Questo non significa che non esista una citazione.'}],
    flow: f([
      n('validazioni','Esiti delle osservazioni\nValidazione e supporto alla relazione','dato'),
      n('filtro','Adattatore di ammissione al gate\nEsito accettato + supporto forte/pieno','controllo'),
      n('intento','Quale intento della domanda?','controllo','Ricerca di interventi o valutazione di un intervento.','diamond'),
      n('scoperta','Ricerca di interventi\nClassificare come relazione scoperta'),
      n('valutazione','Valutazione dell’intervento\nConfrontare direzione e osservazioni ammesse'),
      n('assenza','Nessuna osservazione ammessa\nDirezione senza segnale documentale','limite'),
      n('esito','Esito deterministico della relazione\nStato, dimensioni controllate e avvisi','risultato')
    ],[['validazioni','filtro','esiti originali conservati'],['filtro','intento','osservazioni ammesse'],['intento','scoperta','ricerca'],['intento','valutazione','valutazione'],['valutazione','assenza','nessuna osservazione valida'],['scoperta','esito','relazione scoperta'],['valutazione','esito','concordanza, conflitto o incertezza'],['assenza','esito','esito ambiguo']], [['scoperta','valutazione']])
  },
  status: {
    explanation: 'Questo passaggio espone gli esiti già calcolati per ogni associazione. Non aggiunge una nuova conferma scientifica e non sostituisce la valutazione documentale della relazione.',
    how: ['L’orchestratore raccoglie, per ciascuna relazione, stato del gate, raggruppamento e avvisi. Il motivo rimane associato al risultato.', 'Lo stato dell’analisi descrive se il lavoro è stato completato o interrotto; è distinto dal supporto alla singola relazione.', 'Una relazione non confermata rimane visibile con il proprio motivo: non scompare per lasciare soltanto risultati apparentemente positivi.'],
    flow: f([
      n('valutazioni','Valutazioni deterministiche\nUna per associazione','dato'),
      n('stati','Esporre lo stato della relazione\nDiretta, parziale, contraddetta o ambigua'),
      n('avvisi','Associare avvisi e motivi\nPer esempio: nessun segnale documentale'),
      n('statoanalisi','Stato del lavoro\nCompletato, parziale o interrotto','dato'),
      n('risultati','Risultati consultabili\nRelazione + stato + motivo\nStato del lavoro esposto separatamente','risultato')
    ],[['valutazioni','stati','esiti già calcolati'],['stati','avvisi','stato e raggruppamento'],['avvisi','risultati','motivi conservati'],['statoanalisi','risultati','avanzamento, non supporto scientifico']])
  },
  dossier: {
    explanation: 'Il dossier è la rappresentazione strutturata di ciò che il sistema ha trovato e di come lo ha valutato. Aggrega le osservazioni senza perdere le differenze tra le fonti o nascondere un risultato non favorevole.',
    how: ['Le osservazioni di più documenti o passaggi vengono conservate e aggregate per relazione; non si usa soltanto l’ultima osservazione letta.', 'Pubblicazioni, registri e relazioni del solo grafo rimangono sezioni distinte. Ogni voce mantiene relazione, origine, osservazione, controlli e limiti.', 'Il confronto con il lavoro svolto verifica che risultati, esclusioni e attività non eseguite siano rappresentati. Non certifica la completezza della letteratura.'],
    flow: f([
      n('paper','Pubblicazioni\nOsservazioni, citazioni e controlli','dato'),
      n('registri','Registri di studio\nInformazioni e limiti di eleggibilità','dato'),
      n('grafo','Solo Knowledge Graph\nRelazioni e provenienza','dato'),
      n('aggregare','Aggregare osservazioni per relazione\nConservare supporto, conflitti e incertezze'),
      n('sezioni','Costruire le sezioni del dossier\nRelazione + fonte + osservazione\nControlli + limiti'),
      n('accounting','Confrontare risultati e lavoro svolto\nRendere visibili omissioni e attività non eseguite','controllo'),
      n('dossier','Dossier di riferimento\nGià disponibile prima della spiegazione','risultato')
    ],[['paper','aggregare','tutte le osservazioni'],['aggregare','sezioni','esito documentale della relazione'],['registri','sezioni','contesto di studio'],['grafo','sezioni','origine nel grafo'],['sezioni','accounting','voci del dossier'],['accounting','dossier','contenuto riconciliato']], [['paper','registri','grafo']])
  },
  narratore: {
    explanation: 'Il narratore riceve il contenuto ammesso del dossier e lo spiega in italiano. Il prompt in inglese richiede di collegare domanda, osservazioni, controlli e limiti, conservando le decisioni già registrate.',
    how: ['La proiezione seleziona caso, relazioni, osservazioni, fonti e limiti da trasmettere al modello.', 'Il modello restituisce una sintesi, una spiegazione per ogni relazione, i limiti e una chiusura. Il verificatore applica i controlli di fedeltà prima della presentazione.', 'Un testo deterministico alternativo viene preparato e verificato separatamente in caso di rifiuto o indisponibilità della spiegazione generata.'],
    flow: f([
      n('dossier','Dossier già costruito','dato'),
      n('catalogo','Proiettare i contenuti ammessi\nCaso, fonti, osservazioni, controlli e limiti'),
      n('piano','Modello: spiegare il dossier ricevuto\nPrompt inglese, testo italiano','modello'),
      n('validare','Validare formato, identità e copertura','controllo'),
      n('comporre','Testo generato da verificare'),
      n('alternativa','Preparare il testo deterministico alternativo'),
      n('testo','Testo proposto per la verifica finale','risultato')
    ],[['dossier','catalogo','fatti e limiti'],['catalogo','piano','contenuti'],['piano','validare','spiegazione'],['validare','comporre','formato valido'],['dossier','alternativa','ripiego distinto'],['comporre','testo','proposta'],['alternativa','testo','alternativa da verificare']], [['comporre','alternativa']])
  },
  fedelta: {
    explanation: 'Il verificatore controlla la spiegazione rispetto al dossier: identità, citazioni, fonti, quantità, stati, polarità e limiti riconoscibili. La prosa libera viene sottoposta a regole esplicite; il ripiego precostruito permette anche un confronto esatto.',
    how: ['Il codice ricava dal dossier identità, fonti, citazioni e vincoli da rispettare.', 'La prosa generata passa controlli strutturali e lessicali. Un superamento attesta conformità alle regole implementate e conserva un limite di verifica semantica generale.', 'Se la prosa viene respinta, il ripiego deterministico è verificato separatamente tramite ricostruzione esatta. Il dossier rimane il riferimento disponibile.'],
    flow: f([
      n('dossier','Dossier di riferimento','dato'),
      n('proposta','Spiegazione prodotta dal modello','dato'),
      n('struttura','Struttura, identità e legame con l’ingresso\nOrdine, copertura e impronte','controllo'),
      n('contenuto','Vincoli sul testo\nFonti, citazioni e quantità\nStati, polarità, limiti e raccomandazioni','controllo'),
      n('fedele','Presentazione conforme ai controlli\nCon il limite semantico dichiarato','risultato'),
      n('alternativa','Testo deterministico dal dossier'),
      n('esatto','Verifica separata\nRicostruzione e confronto esatto','controllo'),
      n('ripiego','Mostrare il ripiego verificato','risultato'),
      n('rifiuto','Solo dossier strutturato','limite')
    ],[['proposta','struttura','testo generato'],['struttura','contenuto','struttura valida'],['dossier','contenuto','riferimento','dashed'],['contenuto','fedele','controlli superati'],['struttura','alternativa','formato non valido'],['contenuto','alternativa','testo respinto'],['dossier','alternativa','fatti del dossier'],['alternativa','esatto','ripiego distinto'],['esatto','ripiego','conforme'],['esatto','rifiuto','non conforme']])
  },
  runtime: {
    explanation: 'L’orchestratore accompagna tutti i passaggi: ne gestisce l’ordine, controlla le risorse prima delle chiamate e registra che cosa è stato eseguito. Non è un’ultima elaborazione dopo la spiegazione.',
    how: ['Ogni attività aggiorna lo stato del lavoro attraverso avvio, conclusione o problema. Le operazioni restano ricostruibili.', 'Il budget viene controllato prima del trasporto al modello; tentativi e consumi sono distinti dal significato scientifico dei risultati.', 'Se una risorsa si esaurisce, il lavoro può interrompersi o lasciare attività non eseguite. “Non eseguito” non viene trasformato in “la fonte non sostiene la relazione”.'],
    flow: f([
      n('orchestratore','Orchestratore\nOrdine e avanzamento dei passaggi'),
      n('budget','Prima di chiamare un modello\nVerificare il budget disponibile','controllo'),
      n('chiamata','Eseguire la chiamata consentita\nParser, Reader, confronto o narratore','modello'),
      n('risorse','Budget esaurito o chiamata fallita\nNon inventare l’operazione mancante','limite'),
      n('eventi','Registrare esiti e lavoro non eseguito\nPreservare l’origine delle operazioni'),
      n('consultazione','Stato del lavoro consultabile\nSeparato dal supporto scientifico','risultato')
    ],[['orchestratore','budget','attività che richiede un modello'],['budget','chiamata','risorse disponibili'],['budget','risorse','risorse non disponibili'],['chiamata','eventi','esito della chiamata'],['risorse','eventi','motivo e attività mancanti'],['orchestratore','eventi','avanzamento dei passaggi'],['eventi','consultazione','lavoro realmente svolto']])
  }
};
