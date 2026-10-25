# 10 — Shadow v2 vs v3

Il **backend** produce il confronto. Il frontend non calcola differenze.

```
frontend_computes_differences = false
```

## Risultati sui 35 casi del benchmark

| Metrica | Valore |
|---|---|
| Casi | 35 |
| Retrieval eseguito in **v2** | 35 — sempre |
| Retrieval eseguito in **v3** | **8** |
| Chiamate downstream evitate dal gate | **27** |
| Candidate corrispondenti v2 (totale) | 4 |
| Candidate **positive** v3 | **16** |
| Candidate **audit-only** v3 | **1** |
| Candidate **rifiutate** v3 | **111** |
| Candidate con EvidenceBundle, v2 | 16 |
| Candidate con EvidenceBundle, v3 | 16 |

## Il ponte dei bundle

Gli EvidenceBundle congelati sono chiavizzati sugli id **v2**. Senza un ponte,
nessuna candidate v3 avrebbe documenti e il retrieval v3 non troverebbe mai
nulla: il confronto avrebbe misurato l'assenza del ponte, non la differenza fra
i due contratti. È esattamente ciò che la prima esecuzione ha mostrato
(`v3_positive_total = 0`).

Il ponte usa `v2_mapping.jsonl`, artefatto di primo livello del repository v3.
Tutti e 16 i candidate con bundle sono mappabili. Un bundle di una candidate
confluita in un'unità di regime viene associato all'unità: è la stessa
relazione, rappresentata diversamente.

## Differenza qualitativa

v2 esegue il retrieval per **ogni** caso, incluso «Che tempo fa domani?».
v3 lo esegue solo per gli 8 casi eleggibili.

La differenza più importante non è nel numero di candidate: è che v3 distingue
**positive**, **audit-only** e **rifiutate**, mentre v2 aveva un solo insieme.
Le 111 rifiutate non spariscono — sono elencate con il proprio reason code.

## Casi eseguiti

I casi del benchmark congelato coprono le categorie richieste. Le condizioni
specificamente richieste dal §21 sono verificate nei casi end-to-end A–L
(`end_to_end_results.jsonl`), che includono compound alteration full e partial
match, `SOURCE_DOES_NOT_SUPPORT`, `SOURCE_NEUTRAL` e multi-component unresolved.

## Cosa questo confronto non dimostra

* Non dimostra che i dossier prodotti da v3 siano migliori: il confronto si
  ferma all'ammissione delle candidate, prima del document grounding.
* Non copre casi con più di un ancoraggio oncologico o con alterazioni composte
  reali nel testo del paziente: il benchmark congelato non ne contiene.
* I 111 rifiutati sono in larga parte esclusioni per alterazione non
  corrispondente, cioè il comportamento atteso di un filtro più stretto — non
  una perdita di copertura dimostrata.
