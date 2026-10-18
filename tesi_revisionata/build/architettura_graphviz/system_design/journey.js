(function (root) {
  'use strict';
  // Educational paraphrases, checked against E2E20-16 and the source manifest.
  // They are not literal intermediate payloads or generated clinical advice.
  const common = {
    input: ['Il testo del caso viene registrato come punto di partenza dell’analisi.', 'Caso sintetico registrato: melanoma metastatico; BRAF V600K; interesse per dabrafenib e trametinib.'],
    parser: ['Il modello separa malattia, gene, variante e intervento e conserva i riferimenti al testo.', 'Dati estratti: malattia = melanoma metastatico; gene = BRAF; variante = V600K; intervento = dabrafenib e trametinib.'],
    ancoraggio: ['I valori estratti vengono confrontati con le parole del caso: “BRAF” e “V600K” sono entrambi presenti.', 'Dati ancorati al testo: melanoma metastatico, BRAF V600K e dabrafenib e trametinib; nessuna terapia pregressa valorizzata.'],
    ammissibilita: ['Il controllo trova i dati minimi necessari per questa ricerca. L’ammissione riguarda la ricerca, non l’accesso a uno studio clinico.', 'Ricerca ammessa con i dati verificati del caso: melanoma metastatico, BRAF V600K, dabrafenib e trametinib.'],
    piano: ['Il sistema risolve melanoma in DOID:1909 e conserva “metastatico” come contesto. Riconosce BRAF (NCBIGene:673) e V600K nel gene BRAF (CIViCVariant:563). La stringa combinata “dabrafenib e trametinib” resta UNMAPPED come identità unica e non viene cancellata.', 'Contesto di ricerca: melanoma + contesto metastatico; BRAF–V600K con identità riconosciute; “dabrafenib e trametinib” conservato come valore originale non risolto.' ]
  };
  const branches = {
    melanoma: {
      corpus: ['Si preparano i collegamenti già presenti nel grafo: BRAF V600K rimanda a una descrizione di studio, associata alla pubblicazione 28891408.', 'Conoscenza disponibile: associazione BRAF V600K–descrizione dello studio, con riferimento alla pubblicazione 28891408.'],
      retrieval: ['Fra le associazioni recuperate nell’analisi si segue quella riferita a BRAF V600K e alla pubblicazione 28891408. Il collegamento nel grafo è ancora da confrontare con la fonte.', 'Associazione da approfondire: BRAF V600K–descrizione dello studio; riferimento PubMed 28891408.'],
      risoluzione: ['Il riferimento viene risolto verso il contenuto disponibile della pubblicazione. Il sistema conserva identità e origine della fonte.', 'Fonte disponibile per l’associazione: pubblicazione 28891408, con contenuto e provenienza.'],
      unita: ['Il contenuto viene suddiviso in passaggi identificabili, così da poter ritrovare il testo usato in seguito.', 'Passaggi identificabili della pubblicazione 28891408, con testo e posizione nella fonte.'],
      selezione: ['Si seleziona il materiale da leggere per l’associazione. Nell’analisi archiviata risultano cinque passaggi selezionati per questa pubblicazione.', 'Materiale selezionato: cinque passaggi della pubblicazione 28891408.'],
      reader: ['Il modello ricava un’osservazione con citazione: la fonte parla di trattamento adiuvante nel melanoma di stadio III e di varianti V600E oppure V600K.', 'Osservazione con citazione: dabrafenib e trametinib nel contesto adiuvante di stadio III; V600E oppure V600K.'],
      validazione: ['Si distinguono autenticità della citazione e supporto alla relazione. Nell’archivio la citazione è autentica, ma il supporto non è attribuito. La differenza dal caso metastatico resta visibile, senza essere assunta come causa dell’esito.', 'Controlli registrati: citazione autenticata; supporto non attribuito alla relazione conservata.'],
      gates: ['Le regole combinano associazione e osservazioni ammesse. L’autenticità del testo non autorizza a trasformare l’esito in una conferma per il caso.', 'Valutazione da conservare: la relazione non riceve supporto; la citazione autentica resta consultabile.'],
      status: ['L’esito viene reso leggibile, mantenendo separati ciò che dice il grafo, ciò che è stato letto e ciò che i controlli consentono di concludere.', 'Esito esposto: pubblicazione 28891408, citazione autentica e supporto non attribuito; contesto della fonte distinto dal caso.'],
      dossier: ['La voce viene raccolta nel dossier insieme alle altre associazioni e alle rispettive fonti, senza perdere osservazione e controlli.', 'Voce nel dossier: associazione BRAF V600K, pubblicazione 28891408, osservazione, citazione e supporto non attribuito.'],
      narratore: ['La spiegazione viene composta a partire dai contenuti del dossier. La frase seguente è una parafrasi didattica, non una citazione del testo generato.', 'Parafrasi didattica: “È stata consultata la pubblicazione 28891408; la citazione è autentica, ma non è stato attribuito supporto alla relazione.”'],
      fedelta: ['La presentazione viene confrontata con il dossier. Nell’analisi archiviata il controllo finale passa; questo verifica la fedeltà della spiegazione, non l’applicabilità clinica.', 'Esito finale archiviato: controllo di fedeltà superato; dossier e limiti della relazione restano il riferimento.']
    },
    studio: {
      corpus: ['Si prepara il collegamento del grafo tra BRAF e lo studio NCT02279004 sulla genotipizzazione del plasma.', 'Conoscenza disponibile: associazione BRAF–studio NCT02279004, a livello di gene.'],
      retrieval: ['Si segue il collegamento a NCT02279004 emerso dalla ricerca. Lo studio non era dichiarato nel caso e il collegamento a BRAF non diventa specifico per V600K.', 'Associazione da approfondire: gene BRAF–studio NCT02279004; percorso registro.'],
      risoluzione: ['Il riferimento NCT identifica la copia del registro disponibile nell’analisi del 15 ottobre 2026.', 'Fonte disponibile: copia del registro NCT02279004 usata nell’analisi archiviata.'],
      unita: ['La copia del registro viene organizzata in parti riconoscibili, tra cui titolo e sintesi dello studio.', 'Parti del registro NCT02279004 identificabili e riconducibili alla copia consultata.'],
      selezione: ['Il percorso individua il materiale del registro da associare al collegamento. La selezione non stabilisce l’eleggibilità del caso.', 'Materiale del registro NCT02279004 disponibile per descrivere il collegamento a BRAF.'],
      reader: ['Con focused-v1 il sistema usa i fatti strutturati del registro senza lettura generativa. Il percorso predefinito usa selezione e Reader: non si attribuisce automaticamente a entrambi lo stesso comportamento.', 'Informazioni del registro: NCT02279004, studio sulla genotipizzazione del plasma; eleggibilità individuale non valutata.'],
      validazione: ['Si controllano origine e identità dei contenuti del registro, mantenendo distinta la descrizione dello studio da una prova di efficacia.', 'Contenuto di registro con origine conservata; nessuna conclusione di efficacia o eleggibilità individuale.'],
      gates: ['La relazione viene trattata come contesto di uno studio registrato. Non viene promossa a evidenza di efficacia di dabrafenib e trametinib.', 'Valutazione del percorso registro: contesto di studio; eleggibilità individuale non valutata.'],
      status: ['L’esito viene presentato come informazione di registro, separata dalle osservazioni tratte dalle pubblicazioni.', 'Esito esposto: NCT02279004 collegato a BRAF; contesto di registro e limiti dichiarati.'],
      dossier: ['Il collegamento confluisce nella sezione degli studi con titolo, condizioni registrate e limiti.', 'Voce nel dossier: studio NCT02279004, condizioni registrate e indicazione di eleggibilità non valutata.'],
      narratore: ['La presentazione conserva il significato della voce. La frase seguente è una parafrasi didattica.', 'Parafrasi didattica: “Compare lo studio NCT02279004 collegato a BRAF; l’associazione non stabilisce efficacia né eleggibilità individuale.”'],
      fedelta: ['Il controllo confronta la presentazione con il dossier, mantenendo i limiti propri del registro. Nell’analisi archiviata il controllo finale passa.', 'Esito finale archiviato: controllo di fedeltà superato; lo studio resta informazione di registro.']
    },
    diagnostica: {
      corpus: ['Si prepara il collegamento del grafo tra FoundationOne CDx e BRAF. Questo record non contiene una pubblicazione o uno studio associato.', 'Conoscenza disponibile: FoundationOne CDx–BRAF, con sola provenienza nel Knowledge Graph.'],
      retrieval: ['Il collegamento diagnostico emerge dalla ricerca nel grafo. FoundationOne CDx non viene aggiunto ai dati dichiarati del caso e BRAF non diventa V600K.', 'Associazione da conservare: FoundationOne CDx–BRAF; nessun documento associato.'],
      risoluzione: ['Per questa associazione non esiste un riferimento documentale da risolvere: il percorso mantiene la provenienza del grafo.', 'Percorso senza documento: FoundationOne CDx–BRAF, sola provenienza nel Knowledge Graph.'],
      unita: ['Non si suddivide alcun documento per questa associazione: non è presente una pubblicazione associata.', 'Percorso senza passaggi documentali: FoundationOne CDx–BRAF, origine nel grafo conservata.'],
      selezione: ['Non vengono scelti passaggi da leggere per questa associazione, perché non c’è un documento associato.', 'Percorso senza materiale da leggere: FoundationOne CDx–BRAF, con limite documentale esplicito.'],
      reader: ['Non viene simulata una lettura della letteratura e non viene prodotta una citazione.', 'Nessuna osservazione documentale: resta il collegamento FoundationOne CDx–BRAF con origine nel grafo.'],
      validazione: ['Non c’è una citazione da autenticare per questo collegamento. Il limite viene conservato, senza attribuire un controllo della letteratura.', 'Nessuna validazione documentale attribuita: FoundationOne CDx–BRAF resta associazione del grafo.'],
      gates: ['Il percorso conserva la natura dell’associazione: la mancanza di documento non diventa né prova scientifica né confutazione del collegamento.', 'Valutazione del percorso solo grafo: associazione conservata senza supporto documentale attribuito.'],
      status: ['L’informazione viene esposta con la sua origine e il suo limite, distinta dalle pubblicazioni lette.', 'Esito esposto: FoundationOne CDx–BRAF, sola provenienza nel Knowledge Graph.'],
      dossier: ['Il collegamento confluisce nella sezione delle relazioni del solo grafo, senza citazioni inventate.', 'Voce nel dossier: FoundationOne CDx–BRAF, origine nel grafo e assenza di documento associato.'],
      narratore: ['La spiegazione descrive soltanto ciò che il dossier conserva. La frase seguente è una parafrasi didattica.', 'Parafrasi didattica: “Il grafo collega FoundationOne CDx a BRAF; per questa associazione non è disponibile una fonte documentale.”'],
      fedelta: ['Il controllo finale deve preservare l’assenza di fonte documentale. Nell’analisi archiviata la verifica della presentazione passa.', 'Esito finale archiviato: controllo di fedeltà superato; il collegamento resta informazione del solo grafo.']
    }
  };
  const order = ['input', 'parser', 'ancoraggio', 'ammissibilita', 'piano', 'retrieval', 'risoluzione', 'unita', 'selezione', 'reader', 'validazione', 'gates', 'status', 'dossier', 'narratore', 'fedelta'];
  function rawStep(id, example, caseText) {
    const branch = branches[example] || branches.melanoma;
    if (id === 'runtime') return { input: 'L’intera analisi del caso sintetico, dall’avvio al dossier e alla presentazione.', action: 'Il coordinatore registra avanzamento, operazioni e risorse durante tutto il percorso. Non è una fase successiva alla spiegazione.', result: 'Traccia archiviata dell’analisi del 15 ottobre 2026, con stato di ogni attività e risultati consultabili.', context: 'Coordinamento trasversale · attivo lungo l’intera analisi' };
    const pair = common[id] || branch[id];
    const index = order.indexOf(id);
    const previous = order[index - 1];
    return { input: id === 'corpus' ? 'Entità, collegamenti e riferimenti del Knowledge Graph già disponibile.' : id === 'input' ? caseText : (common[previous] || branch[previous])[1], action: pair[0], result: pair[1], context: id === 'corpus' ? 'Preparazione della conoscenza · prima della ricerca sul caso' : 'Il caso avanza · fase ' + (index + 1) + ' di 16' };
  }
  function step(id, example, caseText) {
    const value = rawStep(id, example, caseText);
    return Object.fromEntries(Object.entries(value).map(([key, text]) => [key, text
      .replace(/ del 15 ottobre 2026/g, '')
      .replace(/nell’analisi archiviata/gi, 'nell’esempio documentato')
      .replace(/nell’analisi registrata/gi, 'nell’esempio documentato')
      .replace(/nell’archivio/gi, 'nell’esempio documentato')
      .replace(/analisi archiviata/gi, 'esempio documentato')
      .replace(/esito finale archiviato/gi, 'esito finale documentato')
      .replace(/traccia archiviata dell’analisi/gi, 'traccia del percorso')
      .replace(/analisi realmente registrata/gi, 'esempio documentato')
    ]));
  }
  const api = { step, order };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.ArchitectureJourney = api;
})(globalThis);
