# Il selector feature-aware

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Formula

```
score(unit) = ( BM25(query_GCA, unit) + bonus_clinico * context_factor ) * section_prior

bonus_clinico  = 3.0 * n_alterazioni + 2.0 * n_geni + 2.0 * n_farmaci + 0.5 * n_malattie
context_factor = min(1, len(text) / 80)
section_prior  = prior strutturale del tipo di unità
```

Ogni componente è registrato separatamente, così la somma si ricostruisce a
mano e si può contestare un addendo alla volta.

## 2. Un esempio reale

`PMC248481`, 243 unità, candidate `GCA-0000980ba01970f893f8e4d7`
(ABL1 V299L, leucemia mieloide cronica). Le prime tre posizioni:

| # | tipo | prior | BM25 | score | gold |
|---|---|---:|---:|---:|---|
| 1 | `FULLTEXT_SENTENCE` | 0.60 | 12.06 | 7.54 | sì |
| 2 | `FULLTEXT_PARAGRAPH` | 0.95 | 4.14 | 4.41 | sì |
| 3 | `FULLTEXT_SENTENCE` | 0.60 | 3.82 | 2.29 | sì |

Tutte e tre le unità gold sono ai primi tre posti, su 243.

Da notare: `matched_alteration` è vuoto per tutte. `V299L` e `ABL1` **non
compaiono nel documento** — coerente con il bundle congelato, che registra
`core_support_mask.biomarker: UNSUPPORTED`. Il ranking ha funzionato sulla
malattia e sull'affinità lessicale, e il modello ha poi correttamente astenuto.

## 3. Determinismo (§20, §35)

Artefatto: `robustness_tests.json`.

| Prova | Esito |
|---|---|
| 10 esecuzioni ripetute | `ranking_hash` identico |
| 4 permutazioni dell'ordine di input | `ranking_hash` identico |
| NFC contro NFD | `ranking_hash` identico |
| maiuscole/minuscole | `ranking_hash` identico |
| punteggiatura e spazi | `ranking_hash` identico |
| unità duplicate | entrambe presenti, ordinate per `source_unit_id` |
| documento vuoto | `NO_RELEVANT_SOURCE_UNIT` |
| documento senza segnale | `NO_RELEVANT_SOURCE_UNIT` |
| **`ranking_drift`** | **0** |

Il tie-break è `source_unit_id`: due unità con lo stesso punteggio si ordinano
allo stesso modo comunque siano arrivate. Senza di esso permutare l'input
cambierebbe la selezione, e il determinismo sarebbe apparente.

## 4. Soglia (§25)

Distribuzione dei punteggi su 2246 unità:

| | n | min | mediana | p95 | max | frazione a zero |
|---|---:|---:|---:|---:|---:|---:|
| gold | 76 | 0.73 | 4.00 | 10.47 | 17.25 | **0.00** |
| non gold | 2170 | 0.00 | 0.00 | 2.97 | 11.17 | **0.74** |

**Nessuna unità gold ha punteggio zero, e il 74% delle non-gold ce l'ha.** La
regola `score > 0` è quindi una separazione che emerge dai dati, non una soglia
scelta per far quadrare le metriche.

Oltre lo zero le code si sovrappongono: il minimo delle gold è 0.73, il p95
delle non-gold è 2.97. Alzare la soglia comincerebbe a perdere gold. Per questo
**non viene introdotta alcuna soglia tarata**: resta `score > 0`.

Con questa regola e `top_k = 4`: 3.68 unità selezionate in media, 63 gold su 76
mantenute, zero casi di `NO_RELEVANT_SOURCE_UNIT` sui bundle reali.

## 5. Scelta di K (§8)

| K | Recall | copertura completa del gold | token medi | p95 | max |
|---:|---:|---:|---:|---:|---:|
| 3 | 0.790 | 0.48 | 454 | 663 | 671 |
| 5 | 0.920 | 0.80 | 653 | 920 | 927 |
| 10 | 0.943 | 0.88 | 902 | 1756 | 1994 |

Da 3 a 5 il recall guadagna 13 punti e la copertura completa 32; da 5 a 10 il
recall guadagna 2.3 punti mentre il p95 dei token quasi raddoppia. Il ginocchio
è a K=5, vicino al valore che il runtime già usa
(`MAX_SOURCE_UNITS_PER_DOCUMENT = 4`).

Nessun rischio di *full-paper dumping*: anche a K=10 il massimo osservato è
sotto i 2000 token, contro le 243 unità del documento più grande.
