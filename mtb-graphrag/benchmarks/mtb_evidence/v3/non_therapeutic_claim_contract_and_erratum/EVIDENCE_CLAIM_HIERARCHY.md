# Gerarchia degli EvidenceClaim

Versione contratto: `non-therapeutic-claim-contract/1.0`
Stato: dichiarativo, non implementato nel repository shadow.

## La gerarchia

```
GraphEvidenceRecord            (contenitore di provenienza — non è un claim)

EvidenceClaim                  (astratto)
├── TherapeuticClaim           (astratto — porta l'intervento)
│   ├── AtomicInterventionClaim
│   ├── AggregateInterventionClaim
│   └── RegimenClaim
├── DiagnosticClaim
└── PrognosticClaim

UnsupportedAssociation         (auditabile — non è un EvidenceClaim)
UnresolvedAssociation          (auditabile — non è un EvidenceClaim)
```

## Perché diagnostico e prognostico sono fratelli di `TherapeuticClaim`

`TherapeuticClaim` è il nodo che porta l'intervento: è ciò che i suoi tre figli
hanno in comune e che li rende confrontabili fra loro. Mettere `DiagnosticClaim`
sotto quel nodo obbligherebbe a dargli un intervento, e non ne ha uno. Il campo
resterebbe vuoto, e un campo vuoto in una posizione obbligatoria è un invito a
riempirlo — con il primo farmaco nominato nella fonte, che è esattamente il modo
in cui `evidence:275` è finito ad affermare erlotinib.

Il nodo che diagnostico, prognostico e terapeutico condividono davvero è più in
alto: un soggetto, un contesto di malattia, una polarità, una provenienza
documentale. Quello è `EvidenceClaim`, e i tre tipi ne discendono in parallelo.

## Perché `GraphEvidenceRecord` non entra nella gerarchia

Resta quello che era: un contenitore di provenienza. Non afferma nulla, quindi
non è un claim, quindi non è un `EvidenceClaim`. Un parent con zero claim è un
esito legittimo, oggi per tre record.

## Perché le associazioni non entrano nella gerarchia

`UnsupportedAssociation` e `UnresolvedAssociation` non sono claim positivi meno
buoni: sono cose che non affermano. La prima è una conclusione — la fonte non
sostiene l'associazione — la seconda una sospensione. Renderle sottotipi di
`EvidenceClaim` le farebbe entrare in un denominatore in cui non hanno posto e
darebbe loro, per ereditarietà, proprietà che il contratto nega.

## `PredictiveClaim`: valutato, non introdotto

Il caso più vicino è `evidence:347`, la cui fonte è davvero uno studio
predittivo: misura se l'effetto di cetuximab sia modulato dallo stato mutazionale
di EGFR. Non è utilizzabile per due ragioni indipendenti.

**Non è materializzabile.** Il record del grafo non porta alcun intervento.
Costruirci sopra un claim predittivo richiederebbe di attribuirgli cetuximab.

**Il tipo sarebbe ridondante.** Un claim predittivo afferma che un biomarcatore
modula l'effetto di un intervento, e il modello lo scrive già: è un
`TherapeuticClaim` con `direction` `sensitivity` o `resistance`. Un
`PredictiveClaim` fratello darebbe due modi di dire la stessa cosa, e due modi di
dire la stessa cosa diventano prima o poi due denominatori diversi.

`predictive_claim_required: false`. Da riconsiderare quando un record porti un
intervento documentato e la fonte riporti una modificazione dell'effetto per
stato del biomarcatore non esprimibile come direzione di sensibilità o
resistenza.

## Inferenze vietate

Sono i modi in cui un'osservazione diventa silenziosamente qualcosa di più forte.
Il contratto le elenca perché siano verificabili, non perché siano ovvie.

**Diagnostico**

| Vietato | Perché |
|---|---|
| associazione con malattia → utilità diagnostica | dice che l'alterazione si trova in quel tumore, non che serva a diagnosticarlo |
| biomarcatore osservato → test validato | la validazione è un'affermazione sulla performance, che la fonte deve fare |
| assay sperimentale → procedura approvata | il metodo con cui si è misurato non è il metodo con cui si diagnostica |

**Prognostico**

| Vietato | Perché |
|---|---|
| associazione osservazionale → causalità | il disegno che la produce non può stabilirla |
| prognostico → predittivo | il primo descrive come va il paziente, il secondo come risponde alla terapia |
| correlazione → utilità clinica | perché lo diventi serve che cambi una decisione, e che qualcuno lo abbia mostrato |
| esito generico → beneficio di sopravvivenza | l'endpoint va conservato come la fonte lo nomina |

## Tipi di query

Definiti, non implementati operativamente.

| Query | Claim primari ammessi |
|---|---|
| `diagnostic_evidence_query` | solo `diagnostic_claim` |
| `prognostic_evidence_query` | solo `prognostic_claim` |
| `therapeutic_evidence_query` | solo i tre tipi terapeutici |
| `untyped_evidence_query` | tutti, in sezioni separate |

Una query diagnostica che restituisse un claim terapeutico non commetterebbe un
errore di ranking ma un errore di categoria, e gli errori di categoria non si
vedono guardando i punteggi. Per questo la matrice è esplicita e la query senza
tipo tiene i risultati in sezioni che non competono fra loro.

## Scoring e metriche

Un claim non terapeutico non riceve therapy score, non entra nelle metriche
therapy-level, non viene appiattito in `intervention` e non viene confrontato con
regimi o classi di farmaci. Le famiglie di metriche — terapeutica, diagnostica,
prognostica, provenienza, copertura strutturale — hanno denominatori separati, e
nessuna le somma. Nessun peso è assegnato in questa fase e nessuna metrica è
calcolata.
