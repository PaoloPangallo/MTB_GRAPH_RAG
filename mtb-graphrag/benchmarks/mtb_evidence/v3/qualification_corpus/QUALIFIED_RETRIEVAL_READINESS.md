# Readiness per il QualifiedEvidenceRetriever

```
ready_for_qualified_retrieval = false
```

La readiness e' **dimension-specific**: il corpus e' pronto per alcuni filtri e
non per altri, e un giudizio unico nasconderebbe proprio la distinzione che
serve a decidere che cosa implementare.

---

## Le quindici domande

| # | Domanda | Risposta |
| ---: | --- | --- |
| 1 | Quante fonti uniche esistono | **102** |
| 2 | Quante sono nello scope | **102** (censimento) |
| 3 | Quante hanno un profilo | **6** con qualificatori clinici; 54 con solo `evidence_design` |
| 4 | Quante hanno piu' unita' | **0** oggi; **16** sospette multi-coorte, non risolte |
| 5 | Quanti statement sono qualificabili | **9** con qualificatori clinici; 70 con `evidence_design` |
| 6 | Quanti statement restano unknown | **138** sulle dimensioni cliniche |
| 7 | Quante ambiguita' esistono | **16** unita' non propagabili |
| 8 | Quanti conflitti esistono | **3** su 2 link |
| 9 | Dimensioni sufficientemente coperte | malattia, intervento (native negli statement) |
| 10 | Dimensioni non ancora usabili come filtri | setting, stadio, linea, popolazione, terapie precedenti, requisiti di biomarcatore, regime, criteri, resezione, comparator |
| 11 | Precision/recall del linker | **non valutabili**, gold assente |
| 12 | Il corpus e' pronto per V3-A | **no** sulle dimensioni cliniche |
| 13 | Cosa manca per il freeze | seconda revisione su 161 coppie |
| 14 | Rischio di bias del corpus | basso per selezione, alto per annotazione |
| 15 | Categorie ancora scoperte | fonti precliniche, trial identifier, comparator, resezione |

---

## Readiness per dimensione

| Dimensione | Copertura | Origine | Verdetto |
| --- | ---: | --- | --- |
| `disease` | 147/147 | statement V2 | **ready** |
| `intervention` | 147/147 | statement V2 | **ready** |
| `direction` / `assertion_polarity` | 147/147 | statement V2 | **ready** |
| `evidence_design` | 70/147 | registro | **partial** — usabile per stratificare, non per escludere |
| `setting` | 9/147 | profili revisionati | not ready |
| `stage` | 9/147 | profili revisionati | not ready |
| `therapy_line` | 9/147 | profili revisionati | not ready |
| `population` | 9/147 | profili revisionati | not ready |
| `prior_therapies` | 9/147 | profili revisionati | not ready |
| `biomarker_requirements` | 9/147 | profili revisionati | not ready |
| `regimen` | 9/147 | profili revisionati | not ready |
| `inclusion_criteria` | 9/147 | profili revisionati | not ready |
| `exclusion_criteria` | ~6/147 | profili revisionati | not ready |
| `comparator` | 0/147 | — | not ready |
| `resection_status` | 0/147 | — | **not ready** — nessuna fonte lo afferma, non viene inventato |

Un filtro su `setting` costruito su 9 statement su 147 non filtrerebbe: lascerebbe
passare 138 statement come «non valutabili» e ne discriminerebbe 9. Il risultato
somiglierebbe a V2 con rumore in piu'.

---

## Verifica dei criteri raccomandati

| Criterio | Esito |
| --- | --- |
| `qualifier_provenance_completeness` = 1.000 | **sì** — 1.0000 |
| nessun qualificatore ambiguo propagato | **sì** — 16 unita' `is_propagatable=False` |
| nessun conflitto sovrascritto | **sì** — 3 conflitti conservati, 0 promozioni |
| tutte le fonti nello scope hanno uno stato esplicito | **sì** — 102/102 |
| gold dei link disponibile per il sottoinsieme valutato | **no** — 0 record valutabili |
| linking precision misurata o marcata non valutabile | **sì** — marcata `not_evaluable` |
| fonti rumorose incluse | **sì** — 31 resistenza, 4 polarita' negativa, 49 scope non terapeutico |
| corpus non costruito solo sulle fonti attese | **sì** — censimento, clinical gold non usato |
| snapshot e hash congelati | **sì** — fingerprint e `statement_repository_hash` verificati |
| dimensioni del futuro retriever con copertura sufficiente | **no** — 6 unita' su 102 |

Due criteri su dieci non sono soddisfatti, ed entrambi hanno la stessa causa: il
corpus e' annotato al 6%.

---

## Rischio di bias

**Selezione: basso.** Il censimento elimina la discrezionalita'. Il clinical gold
non entra nella selezione, e lo strato che avrebbe potuto reintrodurlo
(`unsupported_report_citation`) e' calcolato dal retrieval del pilot invece che
dal gold.

**Annotazione: alto, e va dichiarato.** Le sei unita' annotate non sono un
campione casuale delle 102: sono i profili scritti a mano per i tre casi
positivi del pilot, quindi fonti centrali e ben documentate. Qualunque metrica
calcolata su di esse sovrastima cio' che si otterrebbe sulle 96 restanti, che
includono case report, lettere e studi in cui setting e linea non sono
dichiarati affatto.

Per questo il corpus **non** va usato per stimare la qualita' della
qualificazione prima che l'annotazione prosegua.

**Copertura: una categoria manca del tutto.** Le fonti precliniche non sono
identificabili dai metadati disponibili — l'assenza di un tipo di pubblicazione
clinico non prova che uno studio sia preclinico. Lo strato resta scoperto ed e'
dichiarato tale invece di essere approssimato con un'euristica.

---

## Cosa manca per il freeze

Un solo blocker: **la seconda revisione su tutte e 161 le coppie**.

Non ci sono difetti strutturali. Provenance completa, nessun identificatore
irrisolto, hash coincidenti, nessun disagreement pendente, nessuna unita' con
valori clinici privi di fonte. Il corpus e' sano e non finito, ed e' per questo
che lo stato e' `awaiting_second_review` e non `blocked`.

---

## Percorso consigliato

L'ordine conta, e non e' quello dei numeri piu' grandi.

1. **Annotare le 16 unita' a coorte irrisolta.** Sono il rischio piu' concreto:
   se una di esse venisse propagata per errore, propagherebbe il setting del
   braccio sbagliato.
2. **Annotare le fonti multi-statement** (29). Una annotazione qualifica piu'
   statement: e' il miglior rapporto fra lavoro umano e copertura.
3. **Produrre la seconda revisione** sulle unita' gia' annotate e misurare
   l'accordo. Finche' non esiste, nessuna metrica di linking e' difendibile.
4. Solo dopo, riconsiderare il confronto V2 vs V3-A.

Con l'annotazione ferma a 9 statement su 147, quel confronto misurerebbe la
differenza di **rappresentazione** fra V2 e V3-A, non il contributo della
qualificazione clinica. E' un risultato legittimo, ma va chiamato con il suo
nome.
