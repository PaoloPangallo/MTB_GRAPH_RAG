# Valutazione di retrieval

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `dataset.jsonl`, `retrieval_metrics.json`, `selector_rankings.jsonl`,
`topk_analysis.json`, `failure_cases.csv`.

## 1. Dataset

| Voce | Valore |
|---|---:|
| Bundle valutabili | **25** (tutti, nessun campionamento) |
| Documenti distinti | 25 |
| Candidate distinte | 16 |
| SourceUnit nei documenti | 2246 |
| SourceUnit gold | **76** |
| Gold per bundle | 1→3 casi, 2→4, 3→7, 4→11 |

## 2. Come si usa il gold senza barare

I `bundle["source_unit_ids"]` vengono letti **dopo** che il selector ha prodotto
il ranking. Il modulo non li può raggiungere: non importa nulla che cominci per
`backend.`, e un test di inferenza sostituisce le funzioni di `data_access` con
trappole che sollevano — il selector produce comunque il risultato, con zero
accessi.

Le metriche usano i primi K del **ranking**, non della selezione soglia: le
baseline non hanno soglia, e confrontarle con una selezione filtrata le
penalizzerebbe per una scelta che non hanno fatto.

## 3. Risultati

| Metrica | first-k | BM25 | **feature selector** |
|---|---:|---:|---:|
| HitRate@3 | 0.800 | 0.880 | **1.000** |
| HitRate@5 | 0.800 | 0.920 | **1.000** |
| HitRate@10 | 0.880 | 1.000 | **1.000** |
| Recall@3 | 0.527 | 0.673 | **0.790** |
| Recall@5 | 0.627 | 0.827 | **0.920** |
| Recall@10 | 0.753 | 0.900 | **0.943** |
| copertura completa@5 | 0.360 | 0.720 | **0.800** |
| copertura completa@10 | 0.560 | 0.840 | **0.880** |
| MRR | 0.604 | 0.817 | **0.913** |
| rank medio primo gold | 7.92 | 1.92 | **1.20** |
| casi senza gold recuperato | 3 | 0 | **0** |

La distinzione richiesta da §11 — «almeno una gold» contro «tutte le gold» — è la
differenza fra `HitRate` e `copertura completa`. Il selector trova sempre almeno
una gold nei primi tre, e trova *tutte* le gold nei primi cinque in quattro casi
su cinque.

Il rank medio della prima gold è **1.20**: quasi sempre la prima unità proposta è
già una di quelle che il pilot aveva scelto.

## 4. I mancati, e cosa sono davvero

A K=5 restano fuori **7 gold su 76**. Di questi, **3 hanno testo che coincide con
un'unità selezionata** — stesso contenuto, taglio diverso: il selector ha scelto
la frase, il pilot il paragrafo che la contiene, o viceversa.

```
missed_gold_total                = 7
missed_but_text_overlapping      = 3
granularity_recovery_rate        = 0.43
```

I mancati di contenuto reale sono quindi **4 su 76**. Il resto è disaccordo sulla
granularità, non sulla rilevanza — ed è esattamente l'artefatto che ci si
attende misurando contro un gold costruito con una preferenza di taglio propria.

`failure_cases.csv` è vuoto: non esiste alcun bundle in cui il selector non porti
almeno una gold nei primi cinque.

## 5. Budget di prompt (§27)

| K | token medi | p95 | max |
|---:|---:|---:|---:|
| 3 | 454 | 663 | 671 |
| 5 | 653 | 920 | 927 |
| 10 | 902 | 1756 | 1994 |

Nessun rischio di consegnare l'articolo intero: il documento più grande contiene
243 unità, e a K=10 il massimo osservato resta sotto i 2000 token.

## 6. Un limite che i numeri non mostrano

Venticinque bundle sono pochi, e provengono dallo stesso corpus da cui il gold è
stato definito. Nessuna divisione train/test è possibile con questa numerosità.
I pesi e il prior sono stati scelti su argomenti strutturali, ma **dopo** aver
guardato le statistiche del corpus: un adattamento implicito non si può
escludere, solo dichiarare.
