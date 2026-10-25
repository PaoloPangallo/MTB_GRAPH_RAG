# Decisione

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## Decisione

```
SOURCEUNIT_SELECTOR_PROMISING_NEEDS_REFINEMENT
```

## I criteri formali di §41 sono tutti soddisfatti

| Criterio per `READY_FOR_INTEGRATION` | Misurato |
|---|---|
| `deterministic = true` | ✅ `ranking_drift = 0` su 10 ripetizioni, 4 permutazioni, NFC/NFD, case, punteggiatura |
| `gold_access = 0` | ✅ nessun import `backend.*`; trappole su `data_access` mai scattate |
| `invented SourceUnit = 0` | ✅ `unauthorized_source_unit_rate = 0.000` |
| retrieval competitivo | ✅ HitRate@3 1.000, Recall@10 0.943, MRR 0.913 |
| Gemma e validatore non peggiorano | ✅ 8/8 accordo, tassi identici, 0 quote errate |
| ≥3 casi live-fetch | ✅ 3 su 3 completati |
| nessuna modifica runtime | ✅ 0 file del runtime toccati |

## Perché comunque non `READY_FOR_INTEGRATION`

La checklist è soddisfatta; l'evidenza no. Tre ragioni, in ordine di peso:

1. **I documenti «live» non sono nuovi.** Sono stati riscaricati dal closed set.
   La generalizzazione ad articoli mai visti — che è l'intero scopo del
   componente — non è stata testata, e non poteva esserlo: su un articolo nuovo
   non esiste gold con cui confrontarsi.

2. **Il gold è la scelta del pilot su questo stesso corpus.** Riprodurlo misura
   in parte l'aderenza a una preferenza di granularità. I *near miss* lo
   mostrano: 3 dei 7 gold mancati sono lo stesso testo tagliato diversamente.

3. **25 bundle, nessun set di controllo.** Pesi e prior sono argomentati
   strutturalmente ma scelti dopo aver visto le statistiche del corpus. Un
   adattamento implicito non si può escludere.

`READY_FOR_INTEGRATION` autorizzerebbe a modificare il runtime canonico. Su
questa base non è una raccomandazione difendibile.

## Invarianti

```
selector_uses_llm                = false
gold_access_during_inference     = 0
invented_source_units            = 0
runtime_code_modified            = false
orchestrator_modified            = false
paper_selection_modified         = false
historical_artifacts_modified    = false
selector_integrated_into_runtime = false
push_executed                    = false
merge_executed                   = false
```

## Nessun hard stop di §36 è scattato

| Condizione | Verificata |
|---|---|
| il selector necessita del gold | no |
| BM25/lessicale non recupera le unità rilevanti | no — HitRate@3 = 1.000 |
| alterazioni specifiche perse sistematicamente | no; e il gene non viene scambiato per la variante |
| ranking instabile | no — drift 0 |
| servirebbe un LLM | no |
| Gemma riceve sezioni irrilevanti | no — 0 quote errate, 0 unità non autorizzate |
| validazione peggiorata | no — tassi identici al gold |
| il selector cambia semanticamente la GCA | no — la legge, non la riscrive |
| artefatti storici modificati | no |

## Cosa servirebbe per arrivare a `READY_FOR_INTEGRATION`

1. Un corpus annotato **indipendente** dal pilot, per misurare senza riprodurne
   la granularità.
2. Almeno una decina di articoli mai visti, valutati su rilevanza a livello di
   passaggio.
3. Un campione Gemma più ampio, per dare un intervallo alle differenze oggi
   misurate come nulle.
4. Una decisione progettuale su come il selector convive con i bundle quando
   entrambi esistono.

## Cosa questa fase autorizza

A considerare chiuso il problema *tecnico*: il componente mancante esiste, è
semplice, deterministico e spiegabile, e sui dati disponibili non degrada nulla
a valle.

Non autorizza alcuna modifica del runtime canonico, che resta invariato.
