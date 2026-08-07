# 07 — Limiti che restano

Elenco completo: `evaluation/pre_freeze/remaining_issues.csv`.

```
P0 rimasti                  0
P1 bloccanti rimasti        0
P1 non bloccanti rimasti    1   (ISS-007)
P2 rimasti                  8
P3 rimasti                  6
nuovi P0 emersi             0
```

## ISS-007 — P1, non bloccante

Il denominatore `46 864` compare nelle metriche RQ1/RQ2 senza il denominatore
end-to-end (**16** candidate raggiungibili, perché il retrieval è ristretto a
quelle con un EvidenceBundle). È una correzione di **presentazione nelle tabelle
della tesi**, non di codice, e `blocks_freeze = FALSE`.

Va fatto prima della consegna della tesi, non del freeze del codice.

## P2 — otto, tutti documentabili

| ID | Limite |
|---|---|
| ISS-008 | `kg_retrieval_v3.py`: 147 righe con **zero riferimenti** nel repository |
| ISS-009 | Un mismatch letterale viene riportato come `OUT_OF_SCOPE` invece che con uno stato dedicato |
| ISS-010 | Il rilevatore avversariale è una lista chiusa di 22 pattern: copre le forme del benchmark, non la prompt injection in generale |
| ISS-011 | Il campione manuale v3 a 70 record non è annotato: la fedeltà v3 è verificata sui metadati, non contro un giudizio esperto |
| ISS-012 | Il parser fallisce il trasporto nel ~26-28 % delle run: **confermato** dai 9 casi su 35 del benchmark canonico |
| ISS-013 | Il docstring dell'orchestratore descrive un test di parità che non esiste |
| ISS-014 | 13 artifact sperimentali untracked |
| ISS-015 | Tre assi di versionamento condividono la stringa «v3» |

## P3 — sei

`ISS-016` `describe_availability` incoerente · `ISS-017` gli script RQ non
onorano `OUT` · `ISS-018` percorsi assoluti dell'autore in 7 artifact ·
`ISS-019` il farmaco può stare nell'unità invece che nella quote ·
`ISS-020` narrator e narrative verifier non implementati ·
`ISS-021` `endpoint_configuration` stale.

## Limiti che questa fase NON ha corretto per scelta

Vanno dichiarati nella tesi perché restano proprietà del runtime:

**Il contratto 2.0 non rappresenta le alterazioni composte né i regimi.**
`kg_retrieval._match_candidate` accetta ancora `A AND B` per un caso che
menziona solo `A`, e `_term_matches` fa corrispondere `KRAS G12D` a `KRAS G12C`.
Correggerlo significherebbe migrare il runtime a GCA v3, che il §13 vieta
esplicitamente a questa fase. Le proprietà v3 restano dimostrate **nella
materializzazione**, non nel runtime — vedi `06_rq_impact.md`.

**LIVE resta non eseguibile senza `data_cache/`.** `POST /runs` risponde 503,
che è il comportamento corretto. La validazione delle quote end-to-end resta
dimostrabile solo a livello di componente, e in REPLAY la validazione è
rigiocata anziché rieseguita (`replay.py:117-132`).

**Solo 16 candidate su 46 864 sono raggiungibili end-to-end.** È la dimensione
reale del pilot documentale, non un difetto, ed è il denominatore onesto di ogni
claim end-to-end.

## Una nota sul metodo

Il §15 vietava di correggere P2/P3 salvo necessità per un P0/P1. Non è mai
stato necessario: i tre P0 e i tre P1 bloccanti sono stati chiusi toccando
**sette file applicativi**, e nessuno dei P2/P3 è stato modificato di
conseguenza.

Il file `documents/authorized_cache.py:162-163` contiene la stessa forma di test
per sottostringa che ha causato ISS-002, ma **non decide supporto**: etichetta
gli strati del campionamento del corpus pilota. Modificarlo cambierebbe la
selezione e quindi artifact storici. È stato deliberatamente lasciato invariato
e registrato qui.
