# FGFR2-iCCA disease audit

## Conteggi

- V2: 28 righe, 25 graph evidence ID.
- Gene V2: FGFR2 in 24 righe, FGFR1 in 4.
- Biomarker-compatible dopo il fix: 17 righe, 14 graph ID.
- Compatibili con disease V3 corrente: 1 riga.
- `Cholangiocarcinoma` parent esplicito di iCCA: 12 righe complessive; dieci
  biomarker-compatible, sette graph ID.
- `Cholangiolocellular Carcinoma` sibling esplicito non equivalente: 1.
- Pan-cancer/unspecified: 1.
- Relazione non disponibile localmente: 13.

Le altre etichette comprendono endometrial, breast, transitional cell,
stomach, head-and-neck squamous, adrenal, pilocytic astrocytoma e myeloid
neoplasm. Senza ID o relazione locale non vengono dichiarate equivalenti né
gerarchicamente correlate.

## Semantica V2

I 30 riferimenti di traversal sono: 17 `biomarker_only`, 8
`gene_neighborhood` e 5 `intervention_neighborhood`. Nessuno applicava la
disease. Le quattro righe FGFR1 e i record recuperati soltanto dal vicinato del
farmaco restano distinti dai gap di normalizzazione disease.

## evidence:8173

- Query disease: `Intrahepatic cholangiocarcinoma`.
- Disease V2/statement: `Cholangiolocellular Carcinoma`.
- Disease ID: assente sia nella query sia nello statement.
- Biomarker: FGFR2 fusion, compatibile dopo il fix.
- Relazione locale: entrambi i termini sono figli espliciti di
  `Cholangiocarcinoma`.
- Classificazione: `same_organ_different_subtype`.
- Primo filtro: disease.
- Traversal: intervention-neighborhood e biomarker-only.
- Correzione sicura: nessuna equivalenza.
- Stato: `domain_review_required`.

Il disease qualificato della profile unit collegata è
`cholangiocarcinoma`, ma è `prototype_only` e non può trasformare il sibling in
un exact match.

## Interpretazione

La perdita FGFR2 è principalmente una scelta di specificità: il filtro corrente
ammette solo iCCA exact, mentre V2 recuperava un pool ampio. La relazione
iCCA → cholangiocarcinoma è esplicita localmente e può sostenere una futura
policy gerarchica con warning; non dimostra equivalenza. I record FGFR1,
cross-disease e drug-neighborhood non devono essere recuperati automaticamente.
