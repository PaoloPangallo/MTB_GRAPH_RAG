(function(root){const data={
  "title": "Come funziona l’architettura",
  "verifiedOn": "17 ottobre 2026",
  "groups": [
    {
      "id": "preparazione",
      "title": "Preparare la conoscenza",
      "description": "Dal Knowledge Graph alle associazioni"
    },
    {
      "id": "caso",
      "title": "Comprendere il caso",
      "description": "Dal testo a informazioni controllate"
    },
    {
      "id": "recupero",
      "title": "Cercare i collegamenti",
      "description": "Dalle identità alle associazioni pertinenti"
    },
    {
      "id": "fonti",
      "title": "Raggiungere e scegliere le fonti",
      "description": "Dai riferimenti ai passaggi da leggere"
    },
    {
      "id": "verifica",
      "title": "Leggere e controllare",
      "description": "Dalle osservazioni agli esiti"
    },
    {
      "id": "risultato",
      "title": "Restituire il risultato",
      "description": "Dal dossier alla spiegazione"
    },
    {
      "id": "trasversale",
      "title": "Seguire l’intera analisi",
      "description": "Risorse, avanzamento e tracciabilità"
    }
  ],
  "phases": [
    {
      "id": "corpus",
      "number": "1",
      "title": "Preparare le associazioni candidate",
      "group": "preparazione",
      "stageIds": [],
      "type": "codice",
      "summary": "Il Knowledge Graph contiene collegamenti tra profili molecolari, descrizioni di evidenza, farmaci, studi e test. La preparazione li trasforma in relazioni candidate ricercabili, mantenendo gli argomenti del collegamento e la sua origine.",
      "component": "Preparazione della conoscenza",
      "input": [
        {
          "name": "Knowledge Graph",
          "description": "Conoscenza oncologica organizzata come entità e collegamenti."
        },
        {
          "name": "Origine delle informazioni",
          "description": "Risorsa e percorso da cui proviene ogni collegamento."
        }
      ],
      "output": [
        {
          "name": "Associazioni candidate",
          "description": "Collegamenti pronti per essere confrontati con il caso."
        },
        {
          "name": "Traccia dell’origine",
          "description": "Riferimenti che permettono di ricostruire come sono stati ottenuti."
        }
      ],
      "controls": [
        "Controllare che la raccolta utilizzata sia quella prevista.",
        "Collegare informazioni complementari soltanto quando i riferimenti coincidono.",
        "Conservare l’origine di entrambi i collegamenti quando vengono uniti."
      ],
      "failures": [
        "Se la raccolta non è quella prevista, il sistema si ferma.",
        "Se due collegamenti non possono essere uniti con certezza, non vengono fusi."
      ],
      "design": "La conoscenza viene preparata prima della ricerca sul caso. Le associazioni candidate indicano che cosa approfondire, senza essere già conclusioni sul paziente.",
      "refs": [
        {
          "file": "mtb_gca_v4.py",
          "symbol": "materialize_source"
        },
        {
          "file": "backend/research_pipeline/data_access.py",
          "symbol": "read_candidate_corpus_utf8"
        },
        {
          "file": "backend/research_pipeline/data_access.py",
          "symbol": "adapt_candidate_for_runtime"
        },
        {
          "file": "backend/research_pipeline/retrieval/composite_evidence.py",
          "symbol": "derive_composite_relations"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "nodi",
            "title": "Nodi del Knowledge Graph\nVarianti · evidenze · farmaci · studi",
            "kind": "dato",
            "detail": "Nodi del Knowledge Graph\nVarianti · evidenze · farmaci · studi",
            "shape": "box"
          },
          {
            "id": "archi",
            "title": "Archi e riferimenti\nQuali entità sono collegate?",
            "kind": "dato",
            "detail": "Archi e riferimenti\nQuali entità sono collegate?",
            "shape": "box"
          },
          {
            "id": "materializzare",
            "title": "Materializzare le GCA\nSoggetto + relazione + oggetto",
            "kind": "codice",
            "detail": "Materializzare le GCA\nSoggetto + relazione + oggetto",
            "shape": "box"
          },
          {
            "id": "collegare",
            "title": "Comporre relazioni complementari\nSolo con riferimenti di evidenza coincidenti",
            "kind": "codice",
            "detail": "Comporre relazioni complementari\nSolo con riferimenti di evidenza coincidenti",
            "shape": "box"
          },
          {
            "id": "provenienza",
            "title": "Conservare nodi, archi e fonte\nOgni relazione resta ricostruibile",
            "kind": "controllo",
            "detail": "Conservare nodi, archi e fonte\nOgni relazione resta ricostruibile",
            "shape": "box"
          },
          {
            "id": "corpus",
            "title": "Corpus delle relazioni candidate\nPronto per compatibilità e specificità",
            "kind": "risultato",
            "detail": "Corpus delle relazioni candidate\nPronto per compatibilità e specificità",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "nodi",
            "materializzare",
            "entità"
          ],
          [
            "archi",
            "materializzare",
            "collegamenti"
          ],
          [
            "materializzare",
            "collegare",
            "record di relazione"
          ],
          [
            "collegare",
            "provenienza",
            "origine dei record collegati"
          ],
          [
            "provenienza",
            "corpus",
            "relazioni con provenienza"
          ]
        ],
        "ranks": [
          [
            "nodi",
            "archi"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Nel Knowledge Graph BRAF V600K è collegato alla descrizione di uno studio; la stessa descrizione è collegata a dabrafenib e a trametinib. Il sistema può ricostruire il percorso conservandone le origini.",
      "technicalNumber": "0",
      "explanation": "Il Knowledge Graph contiene collegamenti tra profili molecolari, descrizioni di evidenza, farmaci, studi e test. La preparazione li trasforma in relazioni candidate ricercabili, mantenendo gli argomenti del collegamento e la sua origine.",
      "how": [
        "La materializzazione legge nodi e archi e produce record di relazione: soggetto, predicato, oggetto e riferimenti documentali, quando presenti.",
        "Le relazioni complementari possono essere collegate solo attraverso la stessa evidenza e gli identificatori previsti dalla regola di composizione. La somiglianza del testo non basta.",
        "Il risultato serve al recupero: la presenza di un collegamento nel grafo non è una verifica della pubblicazione."
      ]
    },
    {
      "id": "input",
      "number": "2",
      "title": "Accogliere il caso",
      "group": "caso",
      "stageIds": [
        "stage_1_case_input"
      ],
      "type": "codice",
      "summary": "L’avvio conserva il testo originale del caso e crea il contesto di esecuzione che accompagnerà l’analisi. In questo punto non vengono ancora interpretati gene, variante o malattia.",
      "component": "Avvio dell’analisi",
      "input": [
        {
          "name": "Testo del caso",
          "description": "Descrizione clinica e domanda da approfondire."
        }
      ],
      "output": [
        {
          "name": "Analisi avviata",
          "description": "Un percorso riconoscibile, legato al caso di partenza."
        },
        {
          "name": "Prima registrazione",
          "description": "Informazioni necessarie a ricostruire ciò che accade dopo."
        }
      ],
      "controls": [
        "Associare tutte le operazioni alla stessa analisi.",
        "Controllare che ci siano risorse disponibili prima di iniziare."
      ],
      "failures": [
        "Se non è possibile avviare una nuova analisi, il sistema lo segnala.",
        "Un problema successivo non cancella le operazioni già registrate."
      ],
      "design": "Identificare l’analisi permette di risalire al testo originale, alle fonti lette e al risultato finale.",
      "refs": [
        {
          "file": "backend/research_pipeline/run_store.py",
          "symbol": "RunStore"
        },
        {
          "file": "backend/research_pipeline/recording.py",
          "symbol": "RunRecorder"
        },
        {
          "file": "backend/research_pipeline/contracts.py",
          "symbol": "STAGE_TYPES"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "testo",
            "title": "Testo clinico originale\nDescrizione e domanda da approfondire",
            "kind": "dato",
            "detail": "Testo clinico originale\nDescrizione e domanda da approfondire",
            "shape": "box"
          },
          {
            "id": "inizio",
            "title": "Aprire l’analisi\nCollegare il lavoro al caso",
            "kind": "codice",
            "detail": "Aprire l’analisi\nCollegare il lavoro al caso",
            "shape": "box"
          },
          {
            "id": "risorse",
            "title": "Inizializzare il budget\nLimiti delle chiamate ai modelli",
            "kind": "codice",
            "detail": "Inizializzare il budget\nLimiti delle chiamate ai modelli",
            "shape": "box"
          },
          {
            "id": "registrazione",
            "title": "Registrare avvio e avanzamento\nConservare il testo originale",
            "kind": "codice",
            "detail": "Registrare avvio e avanzamento\nConservare il testo originale",
            "shape": "box"
          },
          {
            "id": "parser",
            "title": "Inviare il testo al Case Parser\nLa lettura strutturata inizia dopo",
            "kind": "risultato",
            "detail": "Inviare il testo al Case Parser\nLa lettura strutturata inizia dopo",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "testo",
            "inizio",
            "testo invariato"
          ],
          [
            "inizio",
            "risorse",
            "impostazioni"
          ],
          [
            "risorse",
            "registrazione",
            "contesto del lavoro"
          ],
          [
            "registrazione",
            "parser",
            "testo + caso"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "L’esempio parte da un caso dichiaratamente sintetico: melanoma metastatico, BRAF V600K e interesse per dabrafenib e trametinib. Non sono disponibili esiti terapeutici del paziente.",
      "technicalNumber": "1",
      "explanation": "L’avvio conserva il testo originale del caso e crea il contesto di esecuzione che accompagnerà l’analisi. In questo punto non vengono ancora interpretati gene, variante o malattia.",
      "how": [
        "Il testo viene mantenuto come riferimento per verificare successivamente le informazioni estratte dal Case Parser.",
        "L’orchestratore inizializza stato del lavoro, registrazione degli eventi e budget delle chiamate; poi passa il testo al parser."
      ]
    },
    {
      "id": "parser",
      "number": "3",
      "title": "Case Parser: dal testo ai campi",
      "group": "caso",
      "stageIds": [
        "stage_2_casecontext_parser"
      ],
      "type": "modello",
      "summary": "Il Case Parser usa un modello linguistico per trasformare il testo in campi strutturati. Deve indicare anche le parole da cui li ha ricavati: estrarre “BRAF” non è ancora dimostrare che quel dato sia corretto.",
      "component": "Lettura del caso",
      "input": [
        {
          "name": "Descrizione libera",
          "description": "Il testo fornito all’inizio dell’analisi."
        }
      ],
      "output": [
        {
          "name": "Descrizione organizzata del caso",
          "description": "Malattia, gene, variante, trattamento di interesse e domanda."
        },
        {
          "name": "Riferimenti al testo",
          "description": "Le frasi da cui sono state ricavate le informazioni."
        }
      ],
      "controls": [
        "Separare i dati presenti dalle informazioni mancanti.",
        "Collegare ogni elemento importante alle parole originali.",
        "Non cercare ancora informazioni nel Knowledge Graph."
      ],
      "failures": [
        "Se la descrizione organizzata non è valida, la ricerca non prosegue.",
        "Un dato proposto dall’assistente deve ancora essere controllato."
      ],
      "design": "Organizzare il testo e autorizzarne l’uso sono due passaggi distinti: la lettura assistita non sostituisce i controlli.",
      "refs": [
        {
          "file": "backend/research_pipeline/casecontext/parser.py",
          "symbol": "call_parser"
        },
        {
          "file": "backend/research_pipeline/models.py",
          "symbol": "CaseContext"
        },
        {
          "file": "backend/research_pipeline/orchestrator.py",
          "symbol": "run_case",
          "anchor": "stage_2_casecontext_parser"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "testo",
            "title": "Testo clinico\n«Melanoma metastatico … BRAF V600K»",
            "kind": "dato",
            "detail": "Testo clinico\n«Melanoma metastatico … BRAF V600K»",
            "shape": "box"
          },
          {
            "id": "richiesta",
            "title": "Richiesta di estrazione\nCampi attesi + citazioni obbligatorie",
            "kind": "codice",
            "detail": "Richiesta di estrazione\nCampi attesi + citazioni obbligatorie",
            "shape": "box"
          },
          {
            "id": "modello",
            "title": "Case Parser · modello linguistico\nPropone valori e riferimenti al testo",
            "kind": "modello",
            "detail": "Case Parser · modello linguistico\nPropone valori e riferimenti al testo",
            "shape": "box"
          },
          {
            "id": "schema",
            "title": "Risposta nello schema richiesto?",
            "kind": "controllo",
            "detail": "Controllo del formato e degli argomenti della risposta.",
            "shape": "diamond"
          },
          {
            "id": "campi",
            "title": "Caso strutturato proposto\nMalattia: melanoma metastatico\nBiomarcatore: gene BRAF, variante V600K\nIntervento cercato: dabrafenib e trametinib",
            "kind": "risultato",
            "detail": "Caso strutturato proposto\nMalattia: melanoma metastatico\nBiomarcatore: gene BRAF, variante V600K\nIntervento cercato: dabrafenib e trametinib",
            "shape": "box"
          },
          {
            "id": "errore",
            "title": "Risposta inutilizzabile\nNessun caso estratto da inviare alla ricerca",
            "kind": "limite",
            "detail": "Risposta inutilizzabile\nNessun caso estratto da inviare alla ricerca",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "testo",
            "richiesta",
            "testo"
          ],
          [
            "richiesta",
            "modello",
            "istruzioni + schema"
          ],
          [
            "modello",
            "schema",
            "risposta"
          ],
          [
            "schema",
            "campi",
            "valida"
          ],
          [
            "schema",
            "errore",
            "non valida"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "Dal testo dell’esempio vengono conservati separatamente melanoma metastatico, BRAF, V600K e dabrafenib e trametinib. Il gene non viene confuso con la variante.",
      "technicalNumber": "2",
      "explanation": "Il Case Parser usa un modello linguistico per trasformare il testo in campi strutturati. Deve indicare anche le parole da cui li ha ricavati: estrarre “BRAF” non è ancora dimostrare che quel dato sia corretto.",
      "how": [
        "La richiesta specifica i campi attesi: malattia, gene, alterazione, interventi e intento della domanda, con citazioni letterali del caso.",
        "La risposta deve rispettare lo schema richiesto. Testo libero o una struttura non valida non vengono trattati come un caso correttamente estratto.",
        "I valori mancanti rimangono nulli o liste vuote. Gene e variante restano associati nello stesso biomarcatore; l’intervento da valutare non diventa una terapia pregressa."
      ]
    },
    {
      "id": "ancoraggio",
      "number": "4",
      "title": "Controllare il legame con il testo",
      "group": "caso",
      "stageIds": [
        "stage_3_casecontext_match"
      ],
      "type": "controllo",
      "summary": "Il Match Verifier cerca nel testo originale le citazioni indicate dal parser e verifica che sostengano il valore estratto. È codice deterministico: non chiede allo stesso modello di confermare la propria risposta.",
      "component": "Confronto con il testo iniziale",
      "input": [
        {
          "name": "Informazioni ricavate",
          "description": "I dati organizzati dopo la lettura."
        },
        {
          "name": "Testo iniziale",
          "description": "Le parole realmente fornite per il caso."
        }
      ],
      "output": [
        {
          "name": "Dati controllati",
          "description": "Informazioni con il relativo riscontro nel testo."
        },
        {
          "name": "Dubbi espliciti",
          "description": "Elementi assenti, incerti o in contrasto."
        }
      ],
      "controls": [
        "Confrontare ogni valore con il testo.",
        "Distinguere un dato mancante da un dato contraddetto.",
        "Mantenere i riferimenti alle frasi di partenza."
      ],
      "failures": [
        "Un contrasto su un dato essenziale può fermare la ricerca.",
        "Un testo senza contraddizioni può comunque essere insufficiente."
      ],
      "design": "Il primo controllo chiede se i dati provengono dal testo. Il successivo chiede se bastano per cercare.",
      "refs": [
        {
          "file": "backend/research_pipeline/casecontext/match_verifier.py",
          "symbol": "verify_case_context"
        },
        {
          "file": "backend/research_pipeline/casecontext/match_verifier.py",
          "symbol": "essential_fields_pass"
        },
        {
          "file": "backend/research_pipeline/orchestrator.py",
          "symbol": "run_case",
          "anchor": "stage_3_casecontext_match"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "campo",
            "title": "Valore del parser + citazione\nEsempio: variante V600K, citazione «V600K»",
            "kind": "dato",
            "detail": "Valore del parser + citazione\nEsempio: variante V600K, citazione «V600K»",
            "shape": "box"
          },
          {
            "id": "originale",
            "title": "Testo clinico originale",
            "kind": "dato",
            "detail": "Testo clinico originale",
            "shape": "box"
          },
          {
            "id": "ricerca",
            "title": "Cercare la citazione letterale\nContare le occorrenze nel testo",
            "kind": "codice",
            "detail": "Cercare la citazione letterale\nContare le occorrenze nel testo",
            "shape": "box"
          },
          {
            "id": "posizione",
            "title": "Ricostruire o disambiguare la posizione\nGli offset aiutano solo se coerenti",
            "kind": "codice",
            "detail": "Ricostruire o disambiguare la posizione\nGli offset aiutano solo se coerenti",
            "shape": "box"
          },
          {
            "id": "valore",
            "title": "Confrontare valore e citazione\nControllare separatamente gene e variante",
            "kind": "controllo",
            "detail": "Confrontare valore e citazione\nControllare separatamente gene e variante",
            "shape": "box"
          },
          {
            "id": "esiti",
            "title": "Campo ancorato · non corrispondente · incerto\nCampo non valorizzato → assente",
            "kind": "risultato",
            "detail": "Campo ancorato · non corrispondente · incerto\nCampo non valorizzato → assente",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "campo",
            "ricerca",
            "citazione proposta"
          ],
          [
            "originale",
            "ricerca",
            "testo autorevole"
          ],
          [
            "ricerca",
            "posizione",
            "occorrenze"
          ],
          [
            "posizione",
            "valore",
            "citazione localizzata"
          ],
          [
            "valore",
            "esiti",
            "esito per campo"
          ]
        ],
        "ranks": [
          [
            "campo",
            "originale"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Il sistema può ritrovare BRAF V600K nella descrizione iniziale. Non deve sostituire V600K con una variante più comune o completare informazioni non dichiarate.",
      "technicalNumber": "3",
      "explanation": "Il Match Verifier cerca nel testo originale le citazioni indicate dal parser e verifica che sostengano il valore estratto. È codice deterministico: non chiede allo stesso modello di confermare la propria risposta.",
      "how": [
        "Per ciascun campo si cerca la citazione letterale. Se compare una sola volta, la posizione viene ricostruita dal testo.",
        "Se la citazione compare più volte, gli offset devono disambiguare l’occorrenza; altrimenti il campo resta incerto.",
        "Gene e variante sono controllati anche con riferimenti separati. Un valore non dichiarato resta assente, anziché essere completato."
      ]
    },
    {
      "id": "ammissibilita",
      "number": "5",
      "title": "Decidere se si può iniziare la ricerca",
      "group": "caso",
      "stageIds": [
        "stage_3b_pre_retrieval_eligibility_gate"
      ],
      "type": "controllo",
      "summary": "Avere campi presenti nel testo non basta per avviare una ricerca significativa. Il gate considera le menzioni verificate, il loro ruolo, eventuali contraddizioni e i dati richiesti dalla domanda.",
      "component": "Controllo di sufficienza",
      "input": [
        {
          "name": "Descrizione controllata",
          "description": "Le informazioni sostenute dal testo."
        },
        {
          "name": "Domanda da approfondire",
          "description": "Il tipo di ricerca richiesto."
        }
      ],
      "output": [
        {
          "name": "Decisione di proseguire",
          "description": "Dati sufficienti per una ricerca significativa."
        },
        {
          "name": "Richiesta di chiarimento",
          "description": "Indicazione di ciò che manca o non è coerente."
        }
      ],
      "controls": [
        "Verificare i dati necessari per la domanda specifica.",
        "Individuare contraddizioni e istruzioni estranee riconosciute dal controllo.",
        "Non inventare malattia, variante o trattamento."
      ],
      "failures": [
        "Se i dati non bastano, il sistema si ferma.",
        "Se c’è un’ambiguità importante, rende necessario un chiarimento."
      ],
      "design": "Questo controllo riguarda l’avvio della ricerca. Non decide se una persona può ricevere un trattamento o partecipare a uno studio.",
      "refs": [
        {
          "file": "backend/research_pipeline/casecontext/pipeline.py",
          "symbol": "run"
        },
        {
          "file": "backend/research_pipeline/casecontext/pipeline.py",
          "symbol": "validate_minimal_case_context"
        },
        {
          "file": "backend/research_pipeline/eligibility/gate.py",
          "symbol": "evaluate"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "menzioni",
            "title": "Menzioni ancorate al testo\nTipo, ruolo e stato dell’asserzione",
            "kind": "dato",
            "detail": "Menzioni ancorate al testo\nTipo, ruolo e stato dell’asserzione",
            "shape": "box"
          },
          {
            "id": "semantica",
            "title": "Verifiche deterministiche sulle menzioni\nNegazione · ruolo clinico · tipo di entità",
            "kind": "controllo",
            "detail": "Verifiche deterministiche sulle menzioni\nNegazione · ruolo clinico · tipo di entità",
            "shape": "box"
          },
          {
            "id": "contraddizioni",
            "title": "Rilevare contraddizioni\nSeparare istruzioni e fatti clinici",
            "kind": "controllo",
            "detail": "Rilevare contraddizioni\nSeparare istruzioni e fatti clinici",
            "shape": "box"
          },
          {
            "id": "sufficienza",
            "title": "Dati sufficienti per questa domanda?\nValutazione di terapia → intervento richiesto",
            "kind": "controllo",
            "detail": "Il controllo dipende dall’intento dichiarato.",
            "shape": "diamond"
          },
          {
            "id": "ammesso",
            "title": "Proiettare solo i fatti accettati\nIl recupero GCA può iniziare",
            "kind": "risultato",
            "detail": "Proiettare solo i fatti accettati\nIl recupero GCA può iniziare",
            "shape": "box"
          },
          {
            "id": "fermo",
            "title": "Recupero non avviato\nDati mancanti, ambigui, fuori ambito\no contraddittori: motivo esplicito",
            "kind": "limite",
            "detail": "Recupero non avviato\nDati mancanti, ambigui, fuori ambito\no contraddittori: motivo esplicito",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "menzioni",
            "semantica",
            "menzioni"
          ],
          [
            "semantica",
            "contraddizioni",
            "menzioni accettate o escluse"
          ],
          [
            "contraddizioni",
            "sufficienza",
            "fatti + intento"
          ],
          [
            "sufficienza",
            "ammesso",
            "sì"
          ],
          [
            "sufficienza",
            "fermo",
            "no"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "Nell’esempio sono espliciti malattia, gene, variante e interesse della ricerca. L’analisi registrata prosegue; non si tratta di una valutazione dell’eleggibilità del caso a uno studio.",
      "technicalNumber": "3b",
      "explanation": "Avere campi presenti nel testo non basta per avviare una ricerca significativa. Il gate considera le menzioni verificate, il loro ruolo, eventuali contraddizioni e i dati richiesti dalla domanda.",
      "how": [
        "La catena deterministica distingue menzioni positive, negate, incerte o storiche e rileva contraddizioni e istruzioni estranee al contenuto clinico.",
        "La sufficienza dipende dall’intento: per valutare un intervento deve esserci l’intervento oggetto della domanda. La malattia non viene inventata e non è un requisito universale per qualsiasi ricerca.",
        "Se il caso non è utilizzabile, il recupero non parte; il sistema restituisce il motivo concreto, come un dato necessario mancante o un contesto contraddittorio."
      ]
    },
    {
      "id": "piano",
      "number": "6",
      "title": "Entity Resolution: dai nomi alle identità",
      "group": "recupero",
      "stageIds": [
        "stage_4_retrieval_plan"
      ],
      "type": "codice",
      "summary": "L’Entity Resolution prepara il confronto tra le parole del caso e le entità del Knowledge Graph. Non è una nuova lettura clinica: collega i nomi a identità riconosciute, conserva il contesto e rende espliciti i nomi che non riesce a risolvere.",
      "component": "Riconoscimento delle entità",
      "input": [
        {
          "name": "Dati accettati",
          "description": "Informazioni che hanno superato i controlli sul caso."
        },
        {
          "name": "Nomi e sinonimi riconosciuti",
          "description": "Vocabolario della conoscenza consultata."
        }
      ],
      "output": [
        {
          "name": "Contesto per la ricerca",
          "description": "Identità da confrontare con le associazioni candidate."
        },
        {
          "name": "Nomi non risolti",
          "description": "Dubbi e limiti di riconoscimento visibili."
        }
      ],
      "controls": [
        "Usare soltanto informazioni accettate.",
        "Tenere distinti gene, variante e combinazioni di alterazioni.",
        "Non considerare equivalenti nomi che non è possibile ricondurre con certezza alla stessa entità."
      ],
      "failures": [
        "Un nome non riconosciuto rimane esplicito.",
        "Un dato valido non deve scomparire nel passaggio alla ricerca."
      ],
      "design": "Riconoscere sinonimi aiuta a cercare senza cambiare ciò che il caso afferma.",
      "refs": [
        {
          "file": "backend/research_pipeline/casecontext/pipeline.py",
          "symbol": "build_retrieval_case_context"
        },
        {
          "file": "backend/research_pipeline/terminology/case_resolution.py",
          "symbol": "resolve_case"
        },
        {
          "file": "backend/research_pipeline/casecontext/pipeline.py",
          "symbol": "projection_audit"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "menzioni",
            "title": "Fatti accettati del caso\nMalattia · biomarcatori · intervento",
            "kind": "dato",
            "detail": "Fatti accettati del caso\nMalattia · biomarcatori · intervento",
            "shape": "box"
          },
          {
            "id": "proiezione",
            "title": "Proiezione per il recupero\nEscludere le menzioni non accettate",
            "kind": "codice",
            "detail": "Proiezione per il recupero\nEscludere le menzioni non accettate",
            "shape": "box"
          },
          {
            "id": "malattia",
            "title": "Risolvere la malattia\nConcetto ontologico + contesto separato",
            "kind": "codice",
            "detail": "Risolvere la malattia\nConcetto ontologico + contesto separato",
            "shape": "box"
          },
          {
            "id": "gene",
            "title": "Risolvere il gene\nNome o sinonimo → identità del gene",
            "kind": "codice",
            "detail": "Risolvere il gene\nNome o sinonimo → identità del gene",
            "shape": "box"
          },
          {
            "id": "variante",
            "title": "Risolvere la variante nel suo gene\nConservare la coppia gene–variante",
            "kind": "codice",
            "detail": "Risolvere la variante nel suo gene\nConservare la coppia gene–variante",
            "shape": "box"
          },
          {
            "id": "intervento",
            "title": "Cercare nomi e alias dell’intervento\nNon forzare un’identità assente",
            "kind": "codice",
            "detail": "Cercare nomi e alias dell’intervento\nNon forzare un’identità assente",
            "shape": "box"
          },
          {
            "id": "contesto",
            "title": "Contesto di ricerca\nValori originali + identità + stati\nContesto di malattia e coppie molecolari",
            "kind": "risultato",
            "detail": "Contesto di ricerca\nValori originali + identità + stati\nContesto di malattia e coppie molecolari",
            "shape": "box"
          },
          {
            "id": "nonrisolti",
            "title": "Nomi non risolti o ambigui\nRestano dichiarati, senza equivalenze inventate",
            "kind": "limite",
            "detail": "Nomi non risolti o ambigui\nRestano dichiarati, senza equivalenze inventate",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "menzioni",
            "proiezione",
            "solo dati accettati"
          ],
          [
            "proiezione",
            "malattia",
            "malattia"
          ],
          [
            "proiezione",
            "gene",
            "biomarcatore"
          ],
          [
            "gene",
            "variante",
            "gene riconosciuto + alterazione"
          ],
          [
            "proiezione",
            "intervento",
            "intervento cercato"
          ],
          [
            "malattia",
            "contesto",
            "concetto + contesto"
          ],
          [
            "variante",
            "contesto",
            "gene + variante"
          ],
          [
            "intervento",
            "contesto",
            "identità o valore originale"
          ],
          [
            "intervento",
            "nonrisolti",
            "nome non riconosciuto"
          ],
          [
            "nonrisolti",
            "contesto",
            "stato conservato"
          ]
        ],
        "ranks": [
          [
            "malattia",
            "gene",
            "intervento"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Il gene BRAF e la variante V600K restano due informazioni distinte. Un collegamento riferito soltanto a BRAF non diventa automaticamente specifico per V600K.",
      "technicalNumber": "4",
      "explanation": "L’Entity Resolution prepara il confronto tra le parole del caso e le entità del Knowledge Graph. Non è una nuova lettura clinica: collega i nomi a identità riconosciute, conserva il contesto e rende espliciti i nomi che non riesce a risolvere.",
      "how": [
        "La proiezione passa alla ricerca soltanto menzioni accettate dai controlli precedenti. I valori scartati dal parser non vengono reinseriti nella domanda.",
        "Per la malattia si separano concetto riconosciuto e contesto residuo: riconoscere melanoma non autorizza a cancellare “metastatico”.",
        "Il gene viene risolto prima della variante; la variante è interpretata nel contesto del suo gene. Per gli interventi si cercano nomi e alias nel vocabolario.",
        "L’uscita conserva valore originale, identità trovata e stato di risoluzione. Un nome non riconosciuto resta visibile: non viene trasformato in un’identità inventata."
      ],
      "workedExample": [
        {
          "name": "«melanoma metastatico»",
          "description": "Concetto melanoma: DOID:1909. “metastatico” è conservato come contesto separato (metastatic), non eliminato."
        },
        {
          "name": "«BRAF»",
          "description": "Identità del gene riconosciuta: NCBIGene:673."
        },
        {
          "name": "«V600K» associata a BRAF",
          "description": "Variante riconosciuta nel contesto del gene: CIViCVariant:563. Il legame BRAF–V600K rimane esplicito."
        },
        {
          "name": "«dabrafenib e trametinib»",
          "description": "Nell’esempio documentato la stringa combinata è UNMAPPED: non è risolta come identità unica. Il valore originale rimane disponibile per la ricerca."
        }
      ]
    },
    {
      "id": "retrieval",
      "number": "7",
      "title": "Trovare le associazioni pertinenti",
      "group": "recupero",
      "stageIds": [
        "stage_5_kg_retrieval"
      ],
      "type": "codice",
      "summary": "Il recupero confronta il contesto del caso con le relazioni candidate del grafo. La compatibilità decide quali relazioni ammettere; la specificità ordina soltanto quelle già ammesse.",
      "component": "Ricerca delle associazioni candidate",
      "input": [
        {
          "name": "Contesto del caso",
          "description": "Malattia, elementi molecolari e interesse della ricerca."
        },
        {
          "name": "Associazioni candidate",
          "description": "Collegamenti del Knowledge Graph con la loro origine."
        }
      ],
      "output": [
        {
          "name": "Associazioni da approfondire",
          "description": "Risultati ordinati per pertinenza e specificità."
        },
        {
          "name": "Tipo di fonte",
          "description": "Pubblicazione, registro di uno studio o sola origine nel Knowledge Graph."
        }
      ],
      "controls": [
        "Controllare la compatibilità delle informazioni applicabili.",
        "Privilegiare le corrispondenze più specifiche, senza perdere collegamenti equivalenti.",
        "Riconoscere quale fonte è realmente associata al risultato."
      ],
      "failures": [
        "Se non trova collegamenti pertinenti, il sistema lo rende esplicito.",
        "Un riferimento ambiguo non viene inviato automaticamente a più percorsi."
      ],
      "design": "L’ordine dei risultati indica che cosa esaminare prima. Non è una graduatoria di appropriatezza dei trattamenti.",
      "refs": [
        {
          "file": "backend/research_pipeline/retrieval/kg_retrieval.py",
          "symbol": "_retrieve"
        },
        {
          "file": "backend/research_pipeline/retrieval/kg_retrieval.py",
          "symbol": "_specificity_order_key"
        },
        {
          "file": "backend/research_pipeline/retrieval/relation_family.py",
          "symbol": "classify_relation_family"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "caso",
            "title": "Contesto del caso\nIdentità, coppie molecolari e valori originali",
            "kind": "dato",
            "detail": "Contesto del caso\nIdentità, coppie molecolari e valori originali",
            "shape": "box"
          },
          {
            "id": "gca",
            "title": "Corpus GCA\nRelazioni con argomenti e provenienza",
            "kind": "dato",
            "detail": "Corpus GCA\nRelazioni con argomenti e provenienza",
            "shape": "box"
          },
          {
            "id": "filtri",
            "title": "Filtrare per compatibilità\nRegole specifiche della famiglia",
            "kind": "controllo",
            "detail": "Filtrare per compatibilità\nRegole specifiche della famiglia",
            "shape": "box"
          },
          {
            "id": "escluse",
            "title": "Relazioni non compatibili\nEscluse con il motivo del confronto",
            "kind": "limite",
            "detail": "Relazioni non compatibili\nEscluse con il motivo del confronto",
            "shape": "box"
          },
          {
            "id": "ordine",
            "title": "Ordinare le relazioni compatibili\nSpecificità lessicografica",
            "kind": "codice",
            "detail": "Ordinare le relazioni compatibili\nSpecificità lessicografica",
            "shape": "box"
          },
          {
            "id": "gruppi",
            "title": "Raggruppare record equivalenti\nApplicare i limiti per famiglia",
            "kind": "codice",
            "detail": "Raggruppare record equivalenti\nApplicare i limiti per famiglia",
            "shape": "box"
          },
          {
            "id": "fonti",
            "title": "Relazioni da approfondire\nPubblicazione · registro · solo grafo",
            "kind": "risultato",
            "detail": "Relazioni da approfondire\nPubblicazione · registro · solo grafo",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "caso",
            "filtri",
            "domanda"
          ],
          [
            "gca",
            "filtri",
            "relazioni"
          ],
          [
            "filtri",
            "escluse",
            "incompatibili"
          ],
          [
            "filtri",
            "ordine",
            "compatibili"
          ],
          [
            "ordine",
            "gruppi",
            "ordine di specificità"
          ],
          [
            "gruppi",
            "fonti",
            "relazioni selezionate"
          ]
        ],
        "ranks": [
          [
            "caso",
            "gca"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Nell’analisi registrata risultano 26 associazioni: 9 collegate a pubblicazioni, una a un registro di studio e 16 con sola provenienza nel Knowledge Graph. Non sono 26 conferme documentali.",
      "technicalNumber": "5",
      "explanation": "Il recupero confronta il contesto del caso con le relazioni candidate del grafo. La compatibilità decide quali relazioni ammettere; la specificità ordina soltanto quelle già ammesse.",
      "how": [
        "I filtri dipendono dalla famiglia della relazione e dalle identità disponibili: non applicano indistintamente gli stessi requisiti a pubblicazioni, studi e test.",
        "L’ordinamento lessicografico considera le caratteristiche di specificità, mantenendo la differenza tra gene, variante e contesto. Non è un punteggio di efficacia.",
        "Dopo raggruppamento e limiti per famiglia, ogni relazione mantiene la propria fonte: riferimento documentale oppure sola provenienza nel grafo."
      ]
    },
    {
      "id": "risoluzione",
      "number": "8",
      "title": "Raggiungere la fonte indicata",
      "group": "fonti",
      "stageIds": [
        "stage_6_document_resolution"
      ],
      "type": "codice",
      "summary": "La relazione del grafo può indicare una pubblicazione o uno studio, ma il riferimento non è ancora testo leggibile. Il resolver cerca il contenuto associato e registra esattamente quale fonte è disponibile.",
      "component": "Ricerca della fonte originale",
      "input": [
        {
          "name": "Riferimento della fonte",
          "description": "Pubblicazione o studio indicato dall’associazione."
        },
        {
          "name": "Documenti già disponibili",
          "description": "Copie che il sistema può riutilizzare."
        }
      ],
      "output": [
        {
          "name": "Fonte consultabile",
          "description": "Testo completo, riassunto o informazioni del registro."
        },
        {
          "name": "Limiti di disponibilità",
          "description": "Indicazione di ciò che non è stato possibile leggere."
        }
      ],
      "controls": [
        "Usare la fonte effettivamente collegata all’associazione.",
        "Preferire il testo completo quando disponibile e coerente con il riferimento.",
        "Mantenere il legame tra riferimento richiesto e documento trovato."
      ],
      "failures": [
        "Se il testo completo manca, può essere usato il riassunto disponibile.",
        "Una fonte assente non viene sostituita con un’altra scelta liberamente."
      ],
      "design": "Il sistema approfondisce la provenienza dell’associazione, anziché cercare soltanto un testo che sembri confermarla.",
      "refs": [
        {
          "file": "backend/research_pipeline/documents/live_resolution.py",
          "symbol": "resolve_live_documents"
        },
        {
          "file": "backend/research_pipeline/documents/authorized_cache.py",
          "symbol": "resolve_live_identifier"
        },
        {
          "file": "backend/research_pipeline/documents/live_resolution.py",
          "symbol": "ResolvedDocument"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "id",
            "title": "Riferimento nell’associazione\nPubMed, PMC o registro NCT",
            "kind": "dato",
            "detail": "Riferimento nell’associazione\nPubMed, PMC o registro NCT",
            "shape": "box"
          },
          {
            "id": "cache",
            "title": "Esiste una copia utilizzabile?",
            "kind": "controllo",
            "detail": "Prima si consulta il contenuto locale disponibile.",
            "shape": "diamond"
          },
          {
            "id": "copia",
            "title": "Caricare la copia della fonte",
            "kind": "codice",
            "detail": "Caricare la copia della fonte",
            "shape": "box"
          },
          {
            "id": "remoto",
            "title": "Tentare il recupero autorizzato\nSolo se la copia manca",
            "kind": "codice",
            "detail": "Tentare il recupero autorizzato\nSolo se la copia manca",
            "shape": "box"
          },
          {
            "id": "contenuto",
            "title": "Contenuto con identità della fonte\nTesto completo · abstract · registro",
            "kind": "risultato",
            "detail": "Contenuto con identità della fonte\nTesto completo · abstract · registro",
            "shape": "box"
          },
          {
            "id": "indisponibile",
            "title": "Contenuto non disponibile\nIl riferimento non diventa prova letta",
            "kind": "limite",
            "detail": "Contenuto non disponibile\nIl riferimento non diventa prova letta",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "id",
            "cache",
            "riferimento"
          ],
          [
            "cache",
            "copia",
            "sì"
          ],
          [
            "cache",
            "remoto",
            "no"
          ],
          [
            "copia",
            "contenuto",
            "contenuto disponibile"
          ],
          [
            "remoto",
            "contenuto",
            "fonte raggiunta"
          ],
          [
            "remoto",
            "indisponibile",
            "recupero fallito"
          ]
        ],
        "ranks": [
          [
            "copia",
            "remoto"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Per l’associazione BRAF V600K dell’esempio viene consultato il riassunto della pubblicazione 28891408. La registrazione distingue questa disponibilità dal testo completo.",
      "technicalNumber": "6",
      "explanation": "La relazione del grafo può indicare una pubblicazione o uno studio, ma il riferimento non è ancora testo leggibile. Il resolver cerca il contenuto associato e registra esattamente quale fonte è disponibile.",
      "how": [
        "Il sistema prova prima la copia disponibile localmente; se manca, il percorso autorizzato tenta il recupero attraverso la sorgente prevista.",
        "La disponibilità distingue testo completo, abstract, registro e contenuto non disponibile. Un identificatore bibliografico non viene presentato come se fosse un testo letto.",
        "Le relazioni senza documento seguono il percorso del solo grafo: non si inventa un articolo per farle attraversare il Reader."
      ]
    },
    {
      "id": "unita",
      "number": "9",
      "title": "Dividere la fonte in passaggi leggibili",
      "group": "fonti",
      "stageIds": [
        "stage_7_source_units"
      ],
      "type": "codice",
      "summary": "Il contenuto della fonte viene suddiviso in unità citabili, mantenendo il legame con il documento e la posizione. Il Reader potrà citare un passaggio identificabile, non una frase senza origine.",
      "component": "Preparazione dei passaggi della fonte",
      "input": [
        {
          "name": "Contenuto disponibile",
          "description": "Testo della pubblicazione o informazioni del registro."
        }
      ],
      "output": [
        {
          "name": "Passaggi della fonte",
          "description": "Frasi, parti di testo, elementi di tabelle o didascalie."
        },
        {
          "name": "Posizione e origine",
          "description": "Indicazioni che consentono di ritrovare ciascun passaggio."
        }
      ],
      "controls": [
        "Conservare il documento di origine.",
        "Mantenere testo e posizione quando disponibili.",
        "Distinguere passaggi uguali che compaiono in punti diversi."
      ],
      "failures": [
        "Un contenuto non leggibile non viene trattato come testo disponibile.",
        "La divisione in parti non garantisce che ogni dettaglio del documento sia stato conservato perfettamente."
      ],
      "design": "Una citazione controllabile richiede un passaggio riconoscibile, non soltanto il titolo di un articolo.",
      "refs": [
        {
          "file": "backend/research_pipeline/documents/models.py",
          "symbol": "SourceUnit"
        },
        {
          "file": "backend/research_pipeline/documents/live_resolution.py",
          "symbol": "load_source_units"
        },
        {
          "file": "backend/research_pipeline/documents/authorized_cache.py",
          "symbol": "finalize_source_unit_occurrence_ids"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "documento",
            "title": "Contenuto risolto + formato\nArticolo, abstract, PDF o registro",
            "kind": "dato",
            "detail": "Contenuto risolto + formato\nArticolo, abstract, PDF o registro",
            "shape": "box"
          },
          {
            "id": "parsing",
            "title": "Interpretare la struttura del documento",
            "kind": "codice",
            "detail": "Interpretare la struttura del documento",
            "shape": "box"
          },
          {
            "id": "segmenti",
            "title": "Estrarre unità della fonte\nFrasi · paragrafi · tabelle · didascalie",
            "kind": "codice",
            "detail": "Estrarre unità della fonte\nFrasi · paragrafi · tabelle · didascalie",
            "shape": "box"
          },
          {
            "id": "posizioni",
            "title": "Associare documento e posizione\nSezione, frase o pagina disponibili",
            "kind": "codice",
            "detail": "Associare documento e posizione\nSezione, frase o pagina disponibili",
            "shape": "box"
          },
          {
            "id": "occorrenze",
            "title": "Distinguere le occorrenze\nTesto uguale non implica stessa posizione",
            "kind": "codice",
            "detail": "Distinguere le occorrenze\nTesto uguale non implica stessa posizione",
            "shape": "box"
          },
          {
            "id": "unita",
            "title": "Unità selezionabili e citabili\nTesto + fonte + posizione",
            "kind": "risultato",
            "detail": "Unità selezionabili e citabili\nTesto + fonte + posizione",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "documento",
            "parsing",
            "formato"
          ],
          [
            "parsing",
            "segmenti",
            "struttura"
          ],
          [
            "segmenti",
            "posizioni",
            "testo"
          ],
          [
            "posizioni",
            "occorrenze",
            "origine"
          ],
          [
            "occorrenze",
            "unita",
            "unità identificabili"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "Nell’esempio il passaggio citato appartiene al riassunto della pubblicazione. L’osservazione conserva il legame con quel passaggio e con la fonte.",
      "technicalNumber": "7",
      "explanation": "Il contenuto della fonte viene suddiviso in unità citabili, mantenendo il legame con il documento e la posizione. Il Reader potrà citare un passaggio identificabile, non una frase senza origine.",
      "how": [
        "Il caricatore interpreta il formato disponibile: testo di abstract, struttura dell’articolo, PDF locale o parti del registro.",
        "Ogni unità conserva testo, documento, tipo e localizzatore, quando ricostruibile: sezione, paragrafo, frase o pagina.",
        "Gli identificatori distinguono le occorrenze: due passaggi con testo uguale in punti diversi non devono perdere la propria posizione."
      ]
    },
    {
      "id": "selezione",
      "number": "10",
      "title": "Scegliere che cosa leggere",
      "group": "fonti",
      "stageIds": [
        "stage_8_paper_selection"
      ],
      "type": "codice",
      "summary": "La selezione cerca, dentro ciascun documento, i passaggi più pertinenti alla relazione da approfondire. Il percorso predefinito combina una classifica lessicale strutturale e una classifica semantica mediante RRF.",
      "component": "Selezione dei passaggi e dei documenti",
      "input": [
        {
          "name": "Passaggi disponibili",
          "description": "Contenuti delle fonti trovate."
        },
        {
          "name": "Associazione e domanda",
          "description": "Gli elementi da cercare senza confonderne l’origine."
        }
      ],
      "output": [
        {
          "name": "Materiale da leggere",
          "description": "Documenti e passaggi scelti per l’approfondimento."
        },
        {
          "name": "Esclusioni esplicite",
          "description": "Materiale non letto o rinviato a causa dei limiti."
        }
      ],
      "controls": [
        "Considerare le incompatibilità riconosciute prima della scelta finale.",
        "Affiancare corrispondenze di parole e somiglianza di significato.",
        "Evitare ripetizioni e rispettare i limiti del materiale leggibile."
      ],
      "failures": [
        "Se un criterio non è disponibile, il sistema registra quello effettivamente usato.",
        "I limiti possono lasciare fuori materiale pertinente: la selezione non è esaustiva."
      ],
      "design": "Il percorso predefinito fonde BM25 strutturale e MedCPT con RRF; se MedCPT non e disponibile, usa BM25 strutturale. La pianificazione preventiva dei documenti appartiene al profilo opzionale focused-v1.",
      "refs": [
        {
          "file": "backend/research_pipeline/retrieval/live_sourceunit_selection.py",
          "symbol": "select_live_papers_for_association"
        },
        {
          "file": "backend/research_pipeline/retrieval/canonical_rrf.py",
          "symbol": "select_rrf"
        },
        {
          "file": "backend/research_pipeline/retrieval/document_plan.py",
          "symbol": "plan_documents"
        },
        {
          "file": "backend/research_pipeline/retrieval/selection_intent.py",
          "symbol": "build_selection_intent"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "domanda",
            "title": "Relazione cercata + unità del documento",
            "kind": "dato",
            "detail": "Relazione cercata + unità del documento",
            "shape": "box"
          },
          {
            "id": "filtri",
            "title": "Escludere unità non ammissibili\nPrima della fusione",
            "kind": "controllo",
            "detail": "Escludere unità non ammissibili\nPrima della fusione",
            "shape": "box"
          },
          {
            "id": "bm25",
            "title": "BM25 strutturale\nParole × prior e fattore di sezione",
            "kind": "codice",
            "detail": "BM25 strutturale\nParole × prior e fattore di sezione",
            "shape": "box"
          },
          {
            "id": "dense",
            "title": "MedCPT\nPertinenza semantica",
            "kind": "encoder",
            "detail": "MedCPT\nPertinenza semantica",
            "shape": "box"
          },
          {
            "id": "rrf",
            "title": "Reciprocal Rank Fusion\nSomma di 1 / (60 + rango)",
            "kind": "codice",
            "detail": "Reciprocal Rank Fusion\nSomma di 1 / (60 + rango)",
            "shape": "box"
          },
          {
            "id": "top",
            "title": "Selezionare fino a top-k passaggi\nApplicare vincoli di sovrapposizione",
            "kind": "codice",
            "detail": "Selezionare fino a top-k passaggi\nApplicare vincoli di sovrapposizione",
            "shape": "box"
          },
          {
            "id": "reader",
            "title": "Unità autorizzate per il Reader",
            "kind": "risultato",
            "detail": "Unità autorizzate per il Reader",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "domanda",
            "filtri",
            "unità e relazione"
          ],
          [
            "filtri",
            "bm25",
            "unità ammissibili"
          ],
          [
            "filtri",
            "dense",
            "unità ammissibili"
          ],
          [
            "bm25",
            "rrf",
            "posizioni nella classifica"
          ],
          [
            "dense",
            "rrf",
            "posizioni nella classifica"
          ],
          [
            "rrf",
            "top",
            "ordine fuso"
          ],
          [
            "bm25",
            "top",
            "ripiego se MedCPT non disponibile",
            "dashed"
          ],
          [
            "top",
            "reader",
            "passaggi selezionati"
          ]
        ],
        "ranks": [
          [
            "bm25",
            "dense"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Per la pubblicazione 28891408 l’analisi registrata seleziona cinque passaggi. Questo numero descrive il materiale scelto, non cinque prove indipendenti.",
      "technicalNumber": "8",
      "explanation": "La selezione cerca, dentro ciascun documento, i passaggi più pertinenti alla relazione da approfondire. Il percorso predefinito combina una classifica lessicale strutturale e una classifica semantica mediante RRF.",
      "how": [
        "BM25 strutturale pesa la corrispondenza lessicale con prior e fattore di sezione. MedCPT ordina i passaggi per pertinenza semantica.",
        "I filtri di ammissibilità precedono la fusione. RRF somma 1/(60+rango), con ranghi da uno e fino a 25 risultati per classifica; non confronta direttamente i punteggi delle due scale.",
        "La selezione finale applica top-k e vincoli di sovrapposizione. Se MedCPT non è disponibile, si ripiega su BM25 strutturale. focused-v1 aggiunge pianificazione dei documenti e regole dedicate al materiale da leggere."
      ]
    },
    {
      "id": "reader",
      "number": "11",
      "title": "Leggere la fonte e descrivere ciò che dice",
      "group": "verifica",
      "stageIds": [
        "stage_9_paper_context_enricher"
      ],
      "type": "modello",
      "summary": "Il Reader produce una relazione osservata nella fonte e una citazione che la accompagna. L’osservazione è distinta dalla relazione cercata nel grafo: deve descrivere ciò che il testo permette di dire, oppure astenersi.",
      "component": "Lettura delle fonti",
      "input": [
        {
          "name": "Passaggi scelti",
          "description": "Il materiale autorizzato a sostenere una citazione."
        },
        {
          "name": "Contesto vicino",
          "description": "Passaggi aggiuntivi utilizzabili soltanto per chiarire i riferimenti."
        }
      ],
      "output": [
        {
          "name": "Osservazione con citazione",
          "description": "Ciò che il testo permette di descrivere."
        },
        {
          "name": "Astensione",
          "description": "Esito esplicito quando non c’è un’osservazione utilizzabile."
        }
      ],
      "controls": [
        "Descrivere la fonte senza trasformare l’associazione iniziale in una verità.",
        "Separare i passaggi citabili dal contesto che aiuta a interpretarli.",
        "Per i registri di studio, riutilizzare le informazioni strutturate dello stesso contenuto."
      ],
      "failures": [
        "Se il testo non basta, l’assistente si astiene.",
        "Il contesto di supporto non può diventare una citazione sostitutiva."
      ],
      "design": "Il percorso documentale predefinito usa il Reader anche per i registri. Solo focused-v1 usa fatti strutturati per i registri risolti senza lettura generativa. Il solo grafo non produce citazioni.",
      "refs": [
        {
          "file": "backend/research_pipeline/enrichment/prompt_v3.py",
          "symbol": "render_request"
        },
        {
          "file": "backend/research_pipeline/enrichment/context_reader.py",
          "symbol": "read_with_context_policy"
        },
        {
          "file": "backend/research_pipeline/documents/trial_facts.py",
          "symbol": "extract_trial_facts"
        },
        {
          "file": "backend/research_pipeline/documents/trial_facts.py",
          "symbol": "bind_trial_relation"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "evidenza",
            "title": "Passaggi selezionati\nAutorizzati alla citazione",
            "kind": "dato",
            "detail": "Passaggi selezionati\nAutorizzati alla citazione",
            "shape": "box"
          },
          {
            "id": "contesto",
            "title": "Contesto adiacente, quando necessario\nSolo per chiarire riferimenti locali",
            "kind": "dato",
            "detail": "Contesto adiacente, quando necessario\nSolo per chiarire riferimenti locali",
            "shape": "box"
          },
          {
            "id": "lettore",
            "title": "Reader · modello linguistico\nDescrivere relazione e contesto della fonte",
            "kind": "modello",
            "detail": "Reader · modello linguistico\nDescrivere relazione e contesto della fonte",
            "shape": "box"
          },
          {
            "id": "osservazione",
            "title": "Osservazione + citazione\nSoggetti, intervento, contesto e direzione",
            "kind": "risultato",
            "detail": "Osservazione + citazione\nSoggetti, intervento, contesto e direzione",
            "shape": "box"
          },
          {
            "id": "astensione",
            "title": "Astensione\nIl testo non consente un’osservazione",
            "kind": "limite",
            "detail": "Astensione\nIl testo non consente un’osservazione",
            "shape": "box"
          },
          {
            "id": "registro",
            "title": "Registro risolto",
            "kind": "dato",
            "detail": "Registro risolto",
            "shape": "box"
          },
          {
            "id": "organizzare",
            "title": "Solo focused-v1\nEstrarre e collegare fatti del registro",
            "kind": "codice",
            "detail": "Solo focused-v1\nEstrarre e collegare fatti del registro",
            "shape": "box"
          },
          {
            "id": "solo-grafo",
            "title": "Relazione senza documento",
            "kind": "dato",
            "detail": "Relazione senza documento",
            "shape": "box"
          },
          {
            "id": "origine",
            "title": "Solo Knowledge Graph\nConservare la relazione senza citazione",
            "kind": "risultato",
            "detail": "Solo Knowledge Graph\nConservare la relazione senza citazione",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "evidenza",
            "lettore",
            "testo citabile"
          ],
          [
            "contesto",
            "lettore",
            "contesto separato",
            "dashed"
          ],
          [
            "lettore",
            "osservazione",
            "osservazione proposta"
          ],
          [
            "lettore",
            "astensione",
            "evidenza insufficiente"
          ],
          [
            "registro",
            "evidenza",
            "percorso predefinito"
          ],
          [
            "registro",
            "organizzare",
            "opzione focused-v1",
            "dashed"
          ],
          [
            "organizzare",
            "osservazione",
            "informazioni di registro",
            "dashed"
          ],
          [
            "solo-grafo",
            "origine",
            "nessun documento da leggere"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "La fonte osservata parla di melanoma di stadio III, trattamento adiuvante e varianti V600E oppure V600K. Il sistema conserva questa descrizione senza riscriverla come melanoma metastatico.",
      "technicalNumber": "9",
      "explanation": "Il Reader produce una relazione osservata nella fonte e una citazione che la accompagna. L’osservazione è distinta dalla relazione cercata nel grafo: deve descrivere ciò che il testo permette di dire, oppure astenersi.",
      "how": [
        "La richiesta contiene la relazione da esaminare e i passaggi selezionati. Il modello restituisce soggetti, intervento, contesto e citazione, oppure un’astensione.",
        "Il contesto adiacente può chiarire riferimenti locali, ma rimane separato dai passaggi autorizzati alla citazione.",
        "Il predefinito tratta anche il registro attraverso selezione e Reader. focused-v1 usa invece fatti strutturati per i registri risolti. Le relazioni del solo grafo non producono citazioni."
      ]
    },
    {
      "id": "validazione",
      "number": "12",
      "title": "Verificare citazione e significato",
      "group": "verifica",
      "stageIds": [
        "stage_10_enrichment_validation"
      ],
      "type": "misto",
      "summary": "Le verifiche rispondono a domande diverse: la citazione è autentica? L’osservazione è coerente con il testo? La fonte sostiene la relazione cercata? Superare il primo controllo non implica superare gli altri.",
      "component": "Controllo delle osservazioni",
      "input": [
        {
          "name": "Osservazione proposta",
          "description": "Descrizione e citazione ricavate dalla lettura."
        },
        {
          "name": "Associazione e fonte",
          "description": "Il collegamento da esaminare e il testo disponibile."
        }
      ],
      "output": [
        {
          "name": "Controlli distinti",
          "description": "Citazione presente, contenuto riconosciuto e supporto attribuito."
        },
        {
          "name": "Esiti espliciti",
          "description": "Controlli superati, non richiesti o non eseguiti."
        }
      ],
      "controls": [
        "Verificare che la citazione sia davvero nel passaggio dichiarato.",
        "Controllare identità e informazioni centrali per il tipo di associazione.",
        "Quando previsto, confrontare anche contesto e forza dell’affermazione con un lettore distinto."
      ],
      "failures": [
        "Una citazione corretta non equivale automaticamente a una relazione confermata.",
        "Un controllo non richiesto o non eseguito non è un controllo superato.",
        "Problemi tecnici, assenza di supporto e contraddizioni rimangono distinguibili."
      ],
      "design": "Autenticità della citazione, corrispondenza alla relazione e ammissione del supporto rispondono a domande diverse.",
      "refs": [
        {
          "file": "backend/research_pipeline/enrichment/validator_v3.py",
          "symbol": "validate_enrichment_v3"
        },
        {
          "file": "backend/research_pipeline/enrichment/document_verification.py",
          "symbol": "structural_verify"
        },
        {
          "file": "backend/research_pipeline/enrichment/document_verification.py",
          "symbol": "admit"
        },
        {
          "file": "backend/research_pipeline/enrichment/verification_policy.py",
          "symbol": "policy_for"
        },
        {
          "file": "backend/research_pipeline/orchestrator.py",
          "symbol": "run_case",
          "anchor": "semantic_attempts"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "citazione",
            "title": "Citazione + unità selezionata + documento",
            "kind": "dato",
            "detail": "Citazione + unità selezionata + documento",
            "shape": "box"
          },
          {
            "id": "letterale",
            "title": "Autenticare la citazione\nTesto letterale nella fonte corretta",
            "kind": "controllo",
            "detail": "Autenticare la citazione\nTesto letterale nella fonte corretta",
            "shape": "box"
          },
          {
            "id": "osservazione",
            "title": "Verificare gli argomenti osservati\nSoggetti e intervento presenti nel testo",
            "kind": "controllo",
            "detail": "Verificare gli argomenti osservati\nSoggetti e intervento presenti nel testo",
            "shape": "box"
          },
          {
            "id": "famiglia",
            "title": "Quale famiglia di relazione?",
            "kind": "controllo",
            "detail": "La policy di supporto dipende dalla famiglia.",
            "shape": "diamond"
          },
          {
            "id": "altri",
            "title": "Altre famiglie\nValutare campi e relazione secondo policy",
            "kind": "codice",
            "detail": "Altre famiglie\nValutare campi e relazione secondo policy",
            "shape": "box"
          },
          {
            "id": "struttura",
            "title": "EVIDENCE_DRUG\nIdentità, provenienza e legami strutturali",
            "kind": "controllo",
            "detail": "EVIDENCE_DRUG\nIdentità, provenienza e legami strutturali",
            "shape": "box"
          },
          {
            "id": "semantica",
            "title": "Solo con struttura PASS\nConfronto semantico relazione ↔ fonte",
            "kind": "modello",
            "detail": "Solo con struttura PASS\nConfronto semantico relazione ↔ fonte",
            "shape": "box"
          },
          {
            "id": "fermo",
            "title": "Struttura incompatibile o non risolta\nSemantica non eseguita",
            "kind": "limite",
            "detail": "Struttura incompatibile o non risolta\nSemantica non eseguita",
            "shape": "box"
          },
          {
            "id": "ammissione",
            "title": "Applicare la regola di ammissione\nSupporto pieno/parziale · contraddizione\nNessun supporto · insufficiente/non verificabile",
            "kind": "risultato",
            "detail": "Applicare la regola di ammissione\nSupporto pieno/parziale · contraddizione\nNessun supporto · insufficiente/non verificabile",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "citazione",
            "letterale",
            "testo e origine"
          ],
          [
            "letterale",
            "osservazione",
            "citazione autentica"
          ],
          [
            "osservazione",
            "famiglia",
            "osservazione ammessa"
          ],
          [
            "famiglia",
            "altri",
            "altra famiglia"
          ],
          [
            "famiglia",
            "struttura",
            "EVIDENCE_DRUG"
          ],
          [
            "struttura",
            "semantica",
            "PASS"
          ],
          [
            "struttura",
            "fermo",
            "incompatibile o incerta"
          ],
          [
            "altri",
            "ammissione",
            "valutazione"
          ],
          [
            "semantica",
            "ammissione",
            "confronto + regole"
          ]
        ],
        "ranks": [
          [
            "altri",
            "struttura"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Nell’esempio la citazione è autenticata, ma nell’analisi registrata il supporto non è attribuito alla relazione conservata. Stadio III e melanoma metastatico sono contesti da confrontare, senza attribuire al sistema motivazioni non registrate.",
      "technicalNumber": "10",
      "explanation": "Le verifiche rispondono a domande diverse: la citazione è autentica? L’osservazione è coerente con il testo? La fonte sostiene la relazione cercata? Superare il primo controllo non implica superare gli altri.",
      "how": [
        "Il validatore ritrova la citazione letterale nell’unità selezionata e ne controlla l’appartenenza al documento; verifica inoltre gli argomenti dell’osservazione.",
        "Per EVIDENCE_DRUG si verificano provenienza autorizzata, identità di gene, variante e intervento e legami nella proposizione. Struttura incompatibile e struttura non risolta fermano il confronto semantico.",
        "Il confronto semantico aggiuntivo parte solo con osservazione ammessa e struttura PASS. Le altre famiglie usano il proprio validatore. Supporto, contraddizione, assenza di supporto e incertezza non vengono fusi in un solo sì/no."
      ]
    },
    {
      "id": "gates",
      "number": "13",
      "title": "Applicare le regole di valutazione",
      "group": "verifica",
      "stageIds": [
        "stage_11_deterministic_gates"
      ],
      "type": "controllo",
      "summary": "Le regole deterministiche non rileggono liberamente le fonti. Ricevono soltanto osservazioni ammesse al gate e valutano la relazione secondo l’intento della domanda e la direzione dell’evidenza.",
      "component": "Valutazione regolata",
      "input": [
        {
          "name": "Associazione candidata",
          "description": "Collegamento e contesto dichiarati."
        },
        {
          "name": "Osservazioni controllate",
          "description": "Solo contenuti ammessi dai controlli precedenti."
        }
      ],
      "output": [
        {
          "name": "Valutazione dell’associazione",
          "description": "Esito accompagnato da avvisi e limiti."
        }
      ],
      "controls": [
        "Non usare come supporto osservazioni respinte o non controllate.",
        "Distinguere la direzione dell’effetto dalla posizione della fonte rispetto alla relazione.",
        "Calcolare gli esiti attraverso regole, senza affidarli alla spiegazione finale."
      ],
      "failures": [
        "L’assenza di un supporto utilizzabile non viene trasformata in una conclusione favorevole.",
        "Una fonte che non sostiene l’affermazione non diventa positiva per il solo linguaggio usato."
      ],
      "design": "La valutazione riassume controlli circoscritti. Non decide il trattamento del singolo paziente.",
      "refs": [
        {
          "file": "backend/research_pipeline/determinism/gates.py",
          "symbol": "evaluate_association"
        },
        {
          "file": "backend/research_pipeline/determinism/direction_semantics.py",
          "symbol": "compare_relation_axes"
        },
        {
          "file": "backend/research_pipeline/orchestrator.py",
          "symbol": "_accepted_for_gates"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "validazioni",
            "title": "Esiti delle osservazioni\nValidazione e supporto alla relazione",
            "kind": "dato",
            "detail": "Esiti delle osservazioni\nValidazione e supporto alla relazione",
            "shape": "box"
          },
          {
            "id": "filtro",
            "title": "Adattatore di ammissione al gate\nEsito accettato + supporto forte/pieno",
            "kind": "controllo",
            "detail": "Adattatore di ammissione al gate\nEsito accettato + supporto forte/pieno",
            "shape": "box"
          },
          {
            "id": "intento",
            "title": "Quale intento della domanda?",
            "kind": "controllo",
            "detail": "Ricerca di interventi o valutazione di un intervento.",
            "shape": "diamond"
          },
          {
            "id": "scoperta",
            "title": "Ricerca di interventi\nClassificare come relazione scoperta",
            "kind": "codice",
            "detail": "Ricerca di interventi\nClassificare come relazione scoperta",
            "shape": "box"
          },
          {
            "id": "valutazione",
            "title": "Valutazione dell’intervento\nConfrontare direzione e osservazioni ammesse",
            "kind": "codice",
            "detail": "Valutazione dell’intervento\nConfrontare direzione e osservazioni ammesse",
            "shape": "box"
          },
          {
            "id": "assenza",
            "title": "Nessuna osservazione ammessa\nDirezione senza segnale documentale",
            "kind": "limite",
            "detail": "Nessuna osservazione ammessa\nDirezione senza segnale documentale",
            "shape": "box"
          },
          {
            "id": "esito",
            "title": "Esito deterministico della relazione\nStato, dimensioni controllate e avvisi",
            "kind": "risultato",
            "detail": "Esito deterministico della relazione\nStato, dimensioni controllate e avvisi",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "validazioni",
            "filtro",
            "esiti originali conservati"
          ],
          [
            "filtro",
            "intento",
            "osservazioni ammesse"
          ],
          [
            "intento",
            "scoperta",
            "ricerca"
          ],
          [
            "intento",
            "valutazione",
            "valutazione"
          ],
          [
            "valutazione",
            "assenza",
            "nessuna osservazione valida"
          ],
          [
            "scoperta",
            "esito",
            "relazione scoperta"
          ],
          [
            "valutazione",
            "esito",
            "concordanza, conflitto o incertezza"
          ],
          [
            "assenza",
            "esito",
            "esito ambiguo"
          ]
        ],
        "ranks": [
          [
            "scoperta",
            "valutazione"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "La presenza di una citazione nell’esempio non è sufficiente per promuovere automaticamente l’associazione a conclusione applicabile al caso.",
      "technicalNumber": "11",
      "explanation": "Le regole deterministiche non rileggono liberamente le fonti. Ricevono soltanto osservazioni ammesse al gate e valutano la relazione secondo l’intento della domanda e la direzione dell’evidenza.",
      "how": [
        "L’adattatore ammette al gate soltanto esiti di validazione accettati con supporto forte/pieno. Un’astensione o un supporto non attribuito non viene promosso a evidenza valida.",
        "La valutazione distingue ricerca di possibili interventi e valutazione di un intervento indicato. Per quest’ultima confronta la direzione della relazione con il segnale documentale ammesso.",
        "Gli esiti del gate e il supporto documentale conservato nel dossier sono informazioni distinte: nell’esempio BRAF il gate è ambiguo per assenza di osservazioni ammesse, mentre la relazione nel dossier ha supporto non attribuito."
      ],
      "workedExample": [
        {
          "name": "Citazione della pubblicazione 28891408",
          "description": "Autentica, ma supporto non attribuito alla relazione: non viene ammessa come segnale positivo al gate."
        },
        {
          "name": "Esito del gate per quella relazione",
          "description": "AMBIGUOUS, con NO_VALIDATED_ENRICHMENT_AVAILABLE e direzione NO_DOCUMENT_SIGNAL. Questo non significa che non esista una citazione."
        }
      ]
    },
    {
      "id": "status",
      "number": "14",
      "title": "Rendere leggibili gli esiti",
      "group": "verifica",
      "stageIds": [
        "stage_12_status"
      ],
      "type": "codice",
      "summary": "Questo passaggio espone gli esiti già calcolati per ogni associazione. Non aggiunge una nuova conferma scientifica e non sostituisce la valutazione documentale della relazione.",
      "component": "Organizzazione degli esiti",
      "input": [
        {
          "name": "Valutazioni disponibili",
          "description": "Risultati dei controlli sulle associazioni."
        }
      ],
      "output": [
        {
          "name": "Esiti consultabili",
          "description": "Classificazioni, avvisi e motivi."
        },
        {
          "name": "Stato dell’analisi",
          "description": "Indicazione dell’avanzamento e delle eventuali interruzioni."
        }
      ],
      "controls": [
        "Tenere separati il completamento dell’analisi e la forza delle informazioni.",
        "Non lasciare che la spiegazione cambi gli esiti.",
        "Distinguere lavoro non eseguito e lavoro eseguito senza trovare supporto."
      ],
      "failures": [
        "Un’analisi completata non dimostra che ogni associazione sia confermata.",
        "Un esito incerto non viene presentato come assenza di evidenza nella letteratura."
      ],
      "design": "Una sola etichetta di successo nasconderebbe differenze importanti. Per questo il percorso e i risultati restano leggibili separatamente.",
      "refs": [
        {
          "file": "backend/research_pipeline/orchestrator.py",
          "symbol": "run_case",
          "anchor": "stage_12_status"
        },
        {
          "file": "backend/research_pipeline/determinism/gates.py",
          "symbol": "STATUS_VALUES"
        },
        {
          "file": "backend/research_pipeline/contracts.py",
          "symbol": "STAGE_TYPES"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "valutazioni",
            "title": "Valutazioni deterministiche\nUna per associazione",
            "kind": "dato",
            "detail": "Valutazioni deterministiche\nUna per associazione",
            "shape": "box"
          },
          {
            "id": "stati",
            "title": "Esporre lo stato della relazione\nDiretta, parziale, contraddetta o ambigua",
            "kind": "codice",
            "detail": "Esporre lo stato della relazione\nDiretta, parziale, contraddetta o ambigua",
            "shape": "box"
          },
          {
            "id": "avvisi",
            "title": "Associare avvisi e motivi\nPer esempio: nessun segnale documentale",
            "kind": "codice",
            "detail": "Associare avvisi e motivi\nPer esempio: nessun segnale documentale",
            "shape": "box"
          },
          {
            "id": "statoanalisi",
            "title": "Stato del lavoro\nCompletato, parziale o interrotto",
            "kind": "dato",
            "detail": "Stato del lavoro\nCompletato, parziale o interrotto",
            "shape": "box"
          },
          {
            "id": "risultati",
            "title": "Risultati consultabili\nRelazione + stato + motivo\nStato del lavoro esposto separatamente",
            "kind": "risultato",
            "detail": "Risultati consultabili\nRelazione + stato + motivo\nStato del lavoro esposto separatamente",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "valutazioni",
            "stati",
            "esiti già calcolati"
          ],
          [
            "stati",
            "avvisi",
            "stato e raggruppamento"
          ],
          [
            "avvisi",
            "risultati",
            "motivi conservati"
          ],
          [
            "statoanalisi",
            "risultati",
            "avanzamento, non supporto scientifico"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "L’analisi dell’esempio è completata, ma conserva associazioni documentali, informazioni di registro e collegamenti senza pubblicazione come tipi di informazione differenti.",
      "technicalNumber": "12",
      "explanation": "Questo passaggio espone gli esiti già calcolati per ogni associazione. Non aggiunge una nuova conferma scientifica e non sostituisce la valutazione documentale della relazione.",
      "how": [
        "L’orchestratore raccoglie, per ciascuna relazione, stato del gate, raggruppamento e avvisi. Il motivo rimane associato al risultato.",
        "Lo stato dell’analisi descrive se il lavoro è stato completato o interrotto; è distinto dal supporto alla singola relazione.",
        "Una relazione non confermata rimane visibile con il proprio motivo: non scompare per lasciare soltanto risultati apparentemente positivi."
      ]
    },
    {
      "id": "dossier",
      "number": "15",
      "title": "Costruire il dossier",
      "group": "risultato",
      "stageIds": [
        "stage_13_dossier"
      ],
      "type": "codice",
      "summary": "Il dossier è la rappresentazione strutturata di ciò che il sistema ha trovato e di come lo ha valutato. Aggrega le osservazioni senza perdere le differenze tra le fonti o nascondere un risultato non favorevole.",
      "component": "Raccolta dei risultati",
      "input": [
        {
          "name": "Risultati dei tre percorsi",
          "description": "Pubblicazioni, registri di studio e collegamenti del Knowledge Graph."
        },
        {
          "name": "Traccia del lavoro",
          "description": "Operazioni eseguite, esclusioni e attività non svolte."
        }
      ],
      "output": [
        {
          "name": "Dossier consultabile",
          "description": "Una rappresentazione coerente del percorso e dei risultati."
        },
        {
          "name": "Controllo di completezza del lavoro",
          "description": "Confronto fra ciò che è stato elaborato e ciò che è stato riportato."
        }
      ],
      "controls": [
        "Conservare la diversa origine delle informazioni.",
        "Non inventare una lettura documentale per collegamenti privi di fonte.",
        "Considerare completa la pubblicazione soltanto se i risultati riportati sono riconciliati con il lavoro eseguito."
      ],
      "failures": [
        "Se gli elementi non si riconciliano, la pubblicazione è incompleta.",
        "Completezza del lavoro previsto non significa completezza di tutta la letteratura."
      ],
      "design": "Il dossier è il riferimento principale. Può essere consultato anche senza una spiegazione generata.",
      "refs": [
        {
          "file": "backend/research_pipeline/dossier/builder.py",
          "symbol": "build_relation_aware_report"
        },
        {
          "file": "backend/research_pipeline/dossier/accounting.py",
          "symbol": "build_pipeline_accounting"
        },
        {
          "file": "backend/research_pipeline/dossier/accounting.py",
          "symbol": "apply_publication_integrity"
        },
        {
          "file": "backend/research_pipeline/dossier/reading.py",
          "symbol": "build_reading_guide"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "paper",
            "title": "Pubblicazioni\nOsservazioni, citazioni e controlli",
            "kind": "dato",
            "detail": "Pubblicazioni\nOsservazioni, citazioni e controlli",
            "shape": "box"
          },
          {
            "id": "registri",
            "title": "Registri di studio\nInformazioni e limiti di eleggibilità",
            "kind": "dato",
            "detail": "Registri di studio\nInformazioni e limiti di eleggibilità",
            "shape": "box"
          },
          {
            "id": "grafo",
            "title": "Solo Knowledge Graph\nRelazioni e provenienza",
            "kind": "dato",
            "detail": "Solo Knowledge Graph\nRelazioni e provenienza",
            "shape": "box"
          },
          {
            "id": "aggregare",
            "title": "Aggregare osservazioni per relazione\nConservare supporto, conflitti e incertezze",
            "kind": "codice",
            "detail": "Aggregare osservazioni per relazione\nConservare supporto, conflitti e incertezze",
            "shape": "box"
          },
          {
            "id": "sezioni",
            "title": "Costruire le sezioni del dossier\nRelazione + fonte + osservazione\nControlli + limiti",
            "kind": "codice",
            "detail": "Costruire le sezioni del dossier\nRelazione + fonte + osservazione\nControlli + limiti",
            "shape": "box"
          },
          {
            "id": "accounting",
            "title": "Confrontare risultati e lavoro svolto\nRendere visibili omissioni e attività non eseguite",
            "kind": "controllo",
            "detail": "Confrontare risultati e lavoro svolto\nRendere visibili omissioni e attività non eseguite",
            "shape": "box"
          },
          {
            "id": "dossier",
            "title": "Dossier di riferimento\nGià disponibile prima della spiegazione",
            "kind": "risultato",
            "detail": "Dossier di riferimento\nGià disponibile prima della spiegazione",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "paper",
            "aggregare",
            "tutte le osservazioni"
          ],
          [
            "aggregare",
            "sezioni",
            "esito documentale della relazione"
          ],
          [
            "registri",
            "sezioni",
            "contesto di studio"
          ],
          [
            "grafo",
            "sezioni",
            "origine nel grafo"
          ],
          [
            "sezioni",
            "accounting",
            "voci del dossier"
          ],
          [
            "accounting",
            "dossier",
            "contenuto riconciliato"
          ]
        ],
        "ranks": [
          [
            "paper",
            "registri",
            "grafo"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Il dossier dell’esempio conserva le 26 associazioni con provenienze differenti, comprese l’osservazione sullo studio adiuvante e il collegamento diagnostico a BRAF.",
      "technicalNumber": "13",
      "explanation": "Il dossier è la rappresentazione strutturata di ciò che il sistema ha trovato e di come lo ha valutato. Aggrega le osservazioni senza perdere le differenze tra le fonti o nascondere un risultato non favorevole.",
      "how": [
        "Le osservazioni di più documenti o passaggi vengono conservate e aggregate per relazione; non si usa soltanto l’ultima osservazione letta.",
        "Pubblicazioni, registri e relazioni del solo grafo rimangono sezioni distinte. Ogni voce mantiene relazione, origine, osservazione, controlli e limiti.",
        "Il confronto con il lavoro svolto verifica che risultati, esclusioni e attività non eseguite siano rappresentati. Non certifica la completezza della letteratura."
      ]
    },
    {
      "id": "narratore",
      "number": "16",
      "title": "Preparare una spiegazione fedele",
      "group": "risultato",
      "stageIds": [
        "stage_14_narrator"
      ],
      "type": "modello",
      "summary": "Il narratore controllato non riceve il compito di decidere nuovamente che cosa sia vero. Il codice ricava dal dossier formulazioni consentite e il modello propone quali varianti usare, mantenendo contenuti e ordine.",
      "component": "Presentazione dei risultati",
      "input": [
        {
          "name": "Contenuti del dossier",
          "description": "Informazioni già raccolte e controllate."
        },
        {
          "name": "Formulazioni consentite",
          "description": "Modi di esporre gli stessi contenuti."
        }
      ],
      "output": [
        {
          "name": "Spiegazione proposta",
          "description": "Testo composto senza aggiungere nuove conclusioni cliniche."
        },
        {
          "name": "Origine della presentazione",
          "description": "Indicazione di come è stata costruita."
        }
      ],
      "controls": [
        "Mantenere tutti i contenuti richiesti e il loro ordine.",
        "Consentire scelte espositive, senza inventare fatti.",
        "Tenere distinta una presentazione alternativa preparata automaticamente."
      ],
      "failures": [
        "Se la scelta espositiva non è valida, può essere usata una presentazione alternativa controllata.",
        "Se non c’è spiegazione, il dossier rimane disponibile."
      ],
      "design": "Rendere il risultato più leggibile non deve aumentarne la forza. La spiegazione non modifica quanto le fonti hanno permesso di osservare.",
      "refs": [
        {
          "file": "backend/research_pipeline/narrative/controlled.py",
          "symbol": "build_catalog"
        },
        {
          "file": "backend/research_pipeline/narrative/controlled.py",
          "symbol": "validate_plan"
        },
        {
          "file": "backend/research_pipeline/narrative/controlled.py",
          "symbol": "render_plan"
        },
        {
          "file": "backend/research_pipeline/narrative/narrator.py",
          "symbol": "call_dossier_narrator"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "dossier",
            "title": "Dossier già costruito",
            "kind": "dato",
            "detail": "Dossier già costruito",
            "shape": "box"
          },
          {
            "id": "catalogo",
            "title": "Proiettare i fatti in un catalogo\nVarianti di testo autorizzate",
            "kind": "codice",
            "detail": "Proiettare i fatti in un catalogo\nVarianti di testo autorizzate",
            "shape": "box"
          },
          {
            "id": "piano",
            "title": "Modello: scegliere le formulazioni\nUn piano, non nuove conclusioni",
            "kind": "modello",
            "detail": "Modello: scegliere le formulazioni\nUn piano, non nuove conclusioni",
            "shape": "box"
          },
          {
            "id": "validare",
            "title": "Validare identità, ordine e copertura\nTutte le scelte appartengono al catalogo?",
            "kind": "controllo",
            "detail": "Validare identità, ordine e copertura\nTutte le scelte appartengono al catalogo?",
            "shape": "box"
          },
          {
            "id": "comporre",
            "title": "Comporre il testo dal piano valido",
            "kind": "codice",
            "detail": "Comporre il testo dal piano valido",
            "shape": "box"
          },
          {
            "id": "alternativa",
            "title": "Piano inutilizzabile\nUsare il piano deterministico alternativo",
            "kind": "codice",
            "detail": "Piano inutilizzabile\nUsare il piano deterministico alternativo",
            "shape": "box"
          },
          {
            "id": "testo",
            "title": "Testo proposto per la verifica finale",
            "kind": "risultato",
            "detail": "Testo proposto per la verifica finale",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "dossier",
            "catalogo",
            "fatti e limiti"
          ],
          [
            "catalogo",
            "piano",
            "varianti disponibili"
          ],
          [
            "piano",
            "validare",
            "scelte"
          ],
          [
            "validare",
            "comporre",
            "piano valido"
          ],
          [
            "validare",
            "alternativa",
            "piano non valido"
          ],
          [
            "comporre",
            "testo",
            "testo realizzato"
          ],
          [
            "alternativa",
            "testo",
            "alternativa realizzata"
          ]
        ],
        "ranks": [
          [
            "comporre",
            "alternativa"
          ]
        ],
        "direction": "TB"
      },
      "lesson": "Una spiegazione fedele mantiene sia il caso metastatico sia il contesto adiuvante della fonte; non elimina questa differenza per rendere il racconto più semplice.",
      "technicalNumber": "14",
      "explanation": "Il narratore controllato non riceve il compito di decidere nuovamente che cosa sia vero. Il codice ricava dal dossier formulazioni consentite e il modello propone quali varianti usare, mantenendo contenuti e ordine.",
      "how": [
        "La proiezione costruisce i fatti da esporre e un catalogo di formulazioni che preservano stati, fonti e limiti del dossier.",
        "Il modello restituisce un piano di scelte. Il validatore controlla identità, ordine e copertura delle voci; il codice compone il testo dalle varianti autorizzate.",
        "Se il piano non è utilizzabile, può essere generata un’alternativa deterministica completa, da sottoporre anch’essa alla verifica finale."
      ]
    },
    {
      "id": "fedelta",
      "number": "17",
      "title": "Controllare la spiegazione finale",
      "group": "risultato",
      "stageIds": [
        "stage_15_narrative_verifier"
      ],
      "type": "controllo",
      "summary": "Il verificatore ricostruisce dal dossier il contenuto che la spiegazione è autorizzata a contenere. Il confronto è deterministico e riguarda il testo effettivamente prodotto, non la buona intenzione del narratore.",
      "component": "Confronto tra spiegazione e dossier",
      "input": [
        {
          "name": "Dossier e formulazioni",
          "description": "Il contenuto che può essere esposto."
        },
        {
          "name": "Spiegazione composta",
          "description": "La presentazione da controllare."
        }
      ],
      "output": [
        {
          "name": "Spiegazione verificata",
          "description": "Testo utilizzabile con esito e origine dichiarati."
        },
        {
          "name": "Limiti della presentazione",
          "description": "Indicazione dei problemi riscontrati."
        }
      ],
      "controls": [
        "Controllare testo, ordine e copertura dei contenuti.",
        "Verificare anche le presentazioni alternative.",
        "Non modificare il dossier per far coincidere la spiegazione."
      ],
      "failures": [
        "Un testo che non supera il controllo non viene presentato come spiegazione verificata.",
        "La fedeltà al dossier non certifica applicabilità clinica o completezza delle fonti."
      ],
      "design": "Quest’ultimo controllo riguarda la corrispondenza della presentazione al dossier, non una nuova valutazione scientifica delle fonti.",
      "refs": [
        {
          "file": "backend/research_pipeline/narrative/controlled.py",
          "symbol": "verify_controlled"
        },
        {
          "file": "backend/research_pipeline/narrative/stage_runner.py",
          "symbol": "narrate_and_verify"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "dossier",
            "title": "Dossier di riferimento",
            "kind": "dato",
            "detail": "Dossier di riferimento",
            "shape": "box"
          },
          {
            "id": "ricostruire",
            "title": "Ricostruire catalogo e testo atteso\nIndipendentemente dalla proposta",
            "kind": "codice",
            "detail": "Ricostruire catalogo e testo atteso\nIndipendentemente dalla proposta",
            "shape": "box"
          },
          {
            "id": "proposta",
            "title": "Testo e piano proposti\nDal modello o dall’alternativa",
            "kind": "dato",
            "detail": "Testo e piano proposti\nDal modello o dall’alternativa",
            "shape": "box"
          },
          {
            "id": "piano",
            "title": "Verificare piano, identità e copertura",
            "kind": "controllo",
            "detail": "Verificare piano, identità e copertura",
            "shape": "box"
          },
          {
            "id": "confronto",
            "title": "Confrontare i campi del testo\nContenuto e ordine coincidono?",
            "kind": "controllo",
            "detail": "Il confronto riguarda i campi autorevoli della presentazione.",
            "shape": "diamond"
          },
          {
            "id": "fedele",
            "title": "Spiegazione fedele al dossier\nUtilizzabile con gli stessi limiti",
            "kind": "risultato",
            "detail": "Spiegazione fedele al dossier\nUtilizzabile con gli stessi limiti",
            "shape": "box"
          },
          {
            "id": "rifiuto",
            "title": "Testo non verificato\nIl dossier resta il riferimento",
            "kind": "limite",
            "detail": "Testo non verificato\nIl dossier resta il riferimento",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "dossier",
            "ricostruire",
            "fatti autorevoli"
          ],
          [
            "proposta",
            "piano",
            "piano e testo"
          ],
          [
            "piano",
            "confronto",
            "piano verificato"
          ],
          [
            "ricostruire",
            "confronto",
            "testo atteso"
          ],
          [
            "confronto",
            "fedele",
            "coincidono"
          ],
          [
            "confronto",
            "rifiuto",
            "differiscono"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "Nell’esempio il risultato deve continuare a distinguere una citazione osservata da una conferma per il caso. Anche la presentazione finale deve preservare questa distinzione.",
      "technicalNumber": "15",
      "explanation": "Il verificatore ricostruisce dal dossier il contenuto che la spiegazione è autorizzata a contenere. Il confronto è deterministico e riguarda il testo effettivamente prodotto, non la buona intenzione del narratore.",
      "how": [
        "Si ricostruiscono catalogo e formulazioni attese dal dossier, separatamente dal testo proposto.",
        "Si verificano il piano e i campi autorevoli: contenuto, identità delle voci, ordine e copertura. Aggiunte, omissioni o alterazioni fanno fallire il confronto.",
        "La presentazione alternativa è soggetta allo stesso vincolo. Il fallimento della spiegazione non riscrive il dossier e non ne invalida automaticamente le osservazioni."
      ]
    },
    {
      "id": "runtime",
      "number": "18",
      "title": "Seguire il lavoro e rispettare i limiti",
      "group": "trasversale",
      "stageIds": [],
      "type": "codice",
      "summary": "L’orchestratore accompagna tutti i passaggi: ne gestisce l’ordine, controlla le risorse prima delle chiamate e registra che cosa è stato eseguito. Non è un’ultima elaborazione dopo la spiegazione.",
      "component": "Coordinamento dell’analisi",
      "input": [
        {
          "name": "Impostazioni dell’analisi",
          "description": "Scelte del percorso e risorse disponibili."
        },
        {
          "name": "Avanzamento delle attività",
          "description": "Avvii, conclusioni, problemi e consumo delle risorse."
        }
      ],
      "output": [
        {
          "name": "Traccia dell’analisi",
          "description": "Storia delle operazioni che può essere ricostruita."
        },
        {
          "name": "Risultato consultabile",
          "description": "Esiti accompagnati da ciò che è stato o non è stato svolto."
        }
      ],
      "controls": [
        "Non avviare attività oltre i limiti applicati.",
        "Conservare l’origine delle informazioni e delle operazioni.",
        "Distinguere dati già disponibili, nuovo lavoro e attività rinviate."
      ],
      "failures": [
        "Risorse esaurite: attività interrotte o differite con un motivo.",
        "Un’attività non svolta non diventa un giudizio negativo sul contenuto scientifico."
      ],
      "design": "La tracciabilità permette di capire come si è arrivati al dossier e quali limiti hanno circoscritto il lavoro.",
      "refs": [
        {
          "file": "backend/research_pipeline/run_store.py",
          "symbol": "new_run_budget"
        },
        {
          "file": "backend/research_pipeline/run_store.py",
          "symbol": "RunStore"
        },
        {
          "file": "backend/research_pipeline/budget.py",
          "symbol": "CallBudget"
        },
        {
          "file": "backend/research_pipeline/recording.py",
          "symbol": "RunRecorder"
        },
        {
          "file": "backend/research_pipeline/execution_mode.py",
          "symbol": "classify_run_mode"
        }
      ],
      "flow": {
        "nodes": [
          {
            "id": "orchestratore",
            "title": "Orchestratore\nOrdine e avanzamento dei passaggi",
            "kind": "codice",
            "detail": "Orchestratore\nOrdine e avanzamento dei passaggi",
            "shape": "box"
          },
          {
            "id": "budget",
            "title": "Prima di chiamare un modello\nVerificare il budget disponibile",
            "kind": "controllo",
            "detail": "Prima di chiamare un modello\nVerificare il budget disponibile",
            "shape": "box"
          },
          {
            "id": "chiamata",
            "title": "Eseguire la chiamata consentita\nParser, Reader, confronto o narratore",
            "kind": "modello",
            "detail": "Eseguire la chiamata consentita\nParser, Reader, confronto o narratore",
            "shape": "box"
          },
          {
            "id": "risorse",
            "title": "Budget esaurito o chiamata fallita\nNon inventare l’operazione mancante",
            "kind": "limite",
            "detail": "Budget esaurito o chiamata fallita\nNon inventare l’operazione mancante",
            "shape": "box"
          },
          {
            "id": "eventi",
            "title": "Registrare esiti e lavoro non eseguito\nPreservare l’origine delle operazioni",
            "kind": "codice",
            "detail": "Registrare esiti e lavoro non eseguito\nPreservare l’origine delle operazioni",
            "shape": "box"
          },
          {
            "id": "consultazione",
            "title": "Stato del lavoro consultabile\nSeparato dal supporto scientifico",
            "kind": "risultato",
            "detail": "Stato del lavoro consultabile\nSeparato dal supporto scientifico",
            "shape": "box"
          }
        ],
        "edges": [
          [
            "orchestratore",
            "budget",
            "attività che richiede un modello"
          ],
          [
            "budget",
            "chiamata",
            "risorse disponibili"
          ],
          [
            "budget",
            "risorse",
            "risorse non disponibili"
          ],
          [
            "chiamata",
            "eventi",
            "esito della chiamata"
          ],
          [
            "risorse",
            "eventi",
            "motivo e attività mancanti"
          ],
          [
            "orchestratore",
            "eventi",
            "avanzamento dei passaggi"
          ],
          [
            "eventi",
            "consultazione",
            "lavoro realmente svolto"
          ]
        ],
        "ranks": [],
        "direction": "TB"
      },
      "lesson": "L’esempio viene da un’analisi realmente registrata il 15 ottobre 2026, su un caso sintetico. Questa presentazione riutilizza quei dati: non sta eseguendo una nuova analisi.",
      "technicalNumber": "T",
      "explanation": "L’orchestratore accompagna tutti i passaggi: ne gestisce l’ordine, controlla le risorse prima delle chiamate e registra che cosa è stato eseguito. Non è un’ultima elaborazione dopo la spiegazione.",
      "how": [
        "Ogni attività aggiorna lo stato del lavoro attraverso avvio, conclusione o problema. Le operazioni restano ricostruibili.",
        "Il budget viene controllato prima del trasporto al modello; tentativi e consumi sono distinti dal significato scientifico dei risultati.",
        "Se una risorsa si esaurisce, il lavoro può interrompersi o lasciare attività non eseguite. “Non eseguito” non viene trasformato in “la fonte non sostiene la relazione”."
      ]
    }
  ],
  "graphOnlyFlow": {
    "nodes": [
      {
        "id": "associazione",
        "title": "Associazione nel Knowledge Graph",
        "kind": "dato",
        "detail": "Il collegamento FoundationOne CDx–BRAF è presente nella conoscenza."
      },
      {
        "id": "assenza",
        "title": "Nessun documento associato",
        "kind": "controllo",
        "detail": "Per questo collegamento non sono disponibili riferimenti a una pubblicazione o a uno studio."
      },
      {
        "id": "origine",
        "title": "Origine conservata",
        "kind": "risultato",
        "detail": "Il sistema non simula la lettura di un documento assente."
      },
      {
        "id": "dossier",
        "title": "Informazione nel dossier",
        "kind": "risultato",
        "detail": "L’associazione rimane consultabile con il proprio limite."
      }
    ],
    "edges": [
      [
        "associazione",
        "assenza",
        ""
      ],
      [
        "assenza",
        "origine",
        ""
      ],
      [
        "origine",
        "dossier",
        ""
      ]
    ]
  }
};if(typeof module !== 'undefined' && module.exports) module.exports=data;root.ArchitectureData=data;})(globalThis);
