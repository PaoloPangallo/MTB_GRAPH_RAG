(function(root){const examples={
  "date": "15 ottobre 2026",
  "description": "Associazioni presenti nel Knowledge Graph in uso, collegate a un’analisi registrata su un caso sintetico. Non sono dati di un paziente reale e non è stata eseguita una nuova analisi.",
  "caseSummary": [
    [
      "Malattia",
      "melanoma metastatico"
    ],
    [
      "Gene",
      "BRAF"
    ],
    [
      "Variante",
      "V600K"
    ],
    [
      "Interesse della ricerca",
      "dabrafenib e trametinib"
    ]
  ],
  "caseText": "Caso sintetico per ricerca, non paziente reale. Diagnosi dichiarata: melanoma metastatico. Profilo molecolare dichiarato: BRAF V600K. Intervento oggetto della ricerca: dabrafenib e trametinib. Nessun esito del paziente per questo intervento e disponibile. Organizzare informazioni di registro dei trial, senza affermare eleggibilita individuale. Non formulare raccomandazioni terapeutiche.",
  "counts": {
    "associations": 26,
    "publications": 9,
    "trials": 1,
    "graphOnly": 16
  },
  "items": [
    {
      "id": "melanoma",
      "label": "Melanoma e BRAF V600K",
      "title": "Una pubblicazione da confrontare con il caso",
      "lead": "Il Knowledge Graph collega BRAF V600K alla descrizione di uno studio e alla pubblicazione 28891408. Due ulteriori collegamenti, riferiti alla stessa descrizione, indicano dabrafenib e trametinib.",
      "path": [
        "BRAF V600K",
        "Descrizione dello studio",
        "Pubblicazione 28891408"
      ],
      "facts": [
        [
          "Nel caso",
          "Melanoma metastatico; BRAF V600K."
        ],
        [
          "Nella fonte osservata",
          "Melanoma di stadio III; trattamento adiuvante; varianti V600E oppure V600K."
        ],
        [
          "Passaggi scelti",
          "5 per la pubblicazione nell’analisi registrata."
        ],
        [
          "Esito registrato",
          "Citazione autenticata; supporto non attribuito alla relazione conservata."
        ]
      ],
      "quote": "Adjuvant use of combination therapy with dabrafenib plus trametinib resulted in a significantly lower risk of recurrence in patients with stage III melanoma…",
      "limitation": "La citazione non dimostra che il risultato sia trasferibile al caso metastatico o che riguardi separatamente la sola variante V600K. Le differenze di contesto restano da esaminare; non sono presentate come la causa accertata dell’esito registrato.",
      "sourceLabel": "Pubblicazione PubMed 28891408",
      "sourceUrl": "https://pubmed.ncbi.nlm.nih.gov/28891408/",
      "provenance": "Tre associazioni effettivamente presenti nel Knowledge Graph; osservazione e citazione conservate nell’analisi del 15 ottobre 2026.",
      "kind": "Pubblicazione scientifica"
    },
    {
      "id": "studio",
      "label": "Uno studio sul sangue",
      "title": "Un collegamento a uno studio, non una prova di efficacia",
      "lead": "Tra le associazioni del caso compare uno studio che valuta la genotipizzazione del plasma nel tumore del polmone e nel melanoma. Il collegamento riguarda BRAF.",
      "path": [
        "BRAF",
        "Studio sul plasma",
        "Informazioni del registro"
      ],
      "facts": [
        [
          "Studio",
          "NCT02279004"
        ],
        [
          "Titolo registrato",
          "A Prospective Study of Plasma Genotyping as a Noninvasive Biomarker for Genotype-directed Cancer Care"
        ],
        [
          "Condizioni registrate",
          "Carcinoma polmonare non a piccole cellule; Melanoma"
        ],
        [
          "Eleggibilità personale",
          "Non valutata. Il collegamento non stabilisce che il caso possa partecipare."
        ]
      ],
      "limitation": "Il registro descrive uno studio e i suoi obiettivi. Questa associazione non è una prova di efficacia di dabrafenib o trametinib. Le informazioni appartengono alla copia consultata allora, non a una verifica attuale del reclutamento.",
      "sourceLabel": "Registro dello studio NCT02279004",
      "sourceUrl": "https://clinicaltrials.gov/study/NCT02279004",
      "provenance": "Associazione tra lo studio e BRAF presente nel Knowledge Graph; informazioni del registro conservate nell’analisi del 15 ottobre 2026.",
      "kind": "Registro di uno studio"
    },
    {
      "id": "diagnostica",
      "label": "Un collegamento diagnostico",
      "title": "Un’informazione utile anche senza pubblicazione associata",
      "lead": "Il Knowledge Graph collega FoundationOne CDx al gene BRAF. In questa associazione non sono presenti riferimenti a una pubblicazione o a uno studio clinico.",
      "path": [
        "FoundationOne CDx",
        "Collegamento diagnostico",
        "BRAF",
        "Provenienza nel Knowledge Graph"
      ],
      "facts": [
        [
          "Test indicato nel grafo",
          "FoundationOne CDx  (Foundation Medicine, Inc.)"
        ],
        [
          "Gene collegato",
          "BRAF"
        ],
        [
          "Pubblicazione associata",
          "Non presente in questa associazione."
        ],
        [
          "Livello del collegamento",
          "Riferito al gene BRAF; non viene reso specifico per V600K."
        ]
      ],
      "limitation": "Il sistema conserva il collegamento e la sua origine. Non simula una lettura della letteratura e non inventa una citazione per rafforzarlo.",
      "sourceLabel": "Associazione diagnostica nel Knowledge Graph",
      "sourceUrl": null,
      "provenance": "Associazione effettivamente presente nel Knowledge Graph e conservata nel dossier del 15 ottobre 2026.",
      "kind": "Sola provenienza nel Knowledge Graph"
    }
  ]
};if(typeof module!=="undefined"&&module.exports)module.exports=examples;root.ArchitectureExamples=examples;})(globalThis);
