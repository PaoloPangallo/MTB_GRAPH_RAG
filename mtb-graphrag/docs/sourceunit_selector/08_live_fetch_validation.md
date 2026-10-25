# Validazione su documenti appena recuperati

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `live_fetch_cases.json`.

## 1. Il percorso

Nessuna SourceUnit proviene dalla cache canonica. Per ogni caso:

```
GCA -> identificatore dalla provenance
    -> API ufficiale (E-utilities / PMC OAI) in directory temporanea
    -> parser -> SourceUnit fresche
    -> selector -> top-K
    -> Gemma -> validatore
```

È il percorso che un'architettura cache-miss percorrerebbe davvero.

## 2. Risultati

| Documento | unità fresche | stato selector | sovrapposizione col gold | decisione | quote validata |
|---|---:|---|---:|---|---|
| `pmid:28363909` | 17 | `SELECTED` | 3 | QUOTE | **sì** |
| `pmid:24658966` | 9 | `SELECTED` | 3 | QUOTE | **sì** |
| `pmcid:PMC248481` | 243 | `SELECTED` | 3 | ABSTAIN | — (astensione corretta) |

**Tutte le unità selezionate provengono dal documento appena scaricato**:
verificato confrontando gli id proposti con quelli prodotti dal parser sul
payload temporaneo. Zero unità inventate, zero SourceUnit non autorizzate.

Tre casi su tre completano il percorso. Due producono una citazione verificata
dal validatore deterministico; il terzo astiene, com'era corretto.

## 3. Il dettaglio che conta

Su `PMC248481` il selector ha lavorato su **243 unità appena parsate**, senza
alcun bundle, e ha portato in cima le stesse tre unità che il pilot aveva scelto
mesi prima. Gli identificatori coincidono perché il testo estratto è
byte-identico — la stessa proprietà verificata durante la ricostruzione della
cache.

## 4. Un limite da nominare

Questi tre documenti appartengono al closed set: sono stati **riscaricati**, non
scoperti. «Funziona su documenti freschi» qui significa «funziona su versioni
appena riscaricate di documenti noti», non «funziona su articoli mai visti».

La differenza non è pedante. Su un articolo nuovo non esisterebbe alcun gold con
cui confrontarsi, e non si potrebbe dire se la selezione sia buona — si potrebbe
solo osservare se il modello riesce a citarne un passaggio. È il limite
principale di questa fase e la ragione per cui la decisione finale non è
`READY_FOR_INTEGRATION`.
