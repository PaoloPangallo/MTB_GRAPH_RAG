# EGFR-L858R disease audit

## Conteggi

- V2: 81 righe, 73 graph evidence ID.
- Biomarker-compatible dopo il fix congiuntivo: 56 righe, 48 graph ID.
- Disease-compatible con il filtro V3 corrente: 17 righe.
- Compatibili con biomarcatore e disease correnti: 10 righe, 10 graph ID.
- Alias disease verificati: 54 righe; `Lung Adenocarcinoma` è classificato separatamente come sottotipo più stretto in 17 righe.
- Biomarker-compatible ma esclusi dalla disease corrente: 46 righe.

Le etichette V2/statement sono: `Lung Non-small Cell Carcinoma` (54),
`Lung Adenocarcinoma` (17), `Cancer` (6), e una riga ciascuna per
`Lung Small Cell Carcinoma`, `High Grade Glioma`,
`Pancreatic Adenocarcinoma` e `Breast Cancer`.

Il caso usa `Advanced/metastatic NSCLC` con valori dichiarati nel contratto:
`Non-Small Cell Lung Cancer` e `Lung Adenocarcinoma`. Solo il primo è verificato
indipendentemente come stesso ente; il secondo è un sottotipo locale. Il filtro
V3 usa entrambi come chiavi exact e non applica questa distinzione. Per questo
38 righe biomarker-compatible con `Lung Non-small Cell Carcinoma` vengono
escluse alla disease, mentre 10 righe L858R con `Lung Adenocarcinoma`
sopravvivono pur non essendo equivalenti a NSCLC.

## Evidence ID richiesti

| Evidence ID | Disease statement | Biomarker post-fix | Relazione disease | Primo filtro | Esito prudente |
|---|---|---:|---|---|---|
| evidence:11219 | Lung Non-small Cell Carcinoma | sì | verified_alias_match | disease | alias fix tecnicamente sicuro; il contesto qualificato resta separato |
| evidence:11598 | Lung Non-small Cell Carcinoma | no | verified_alias_match | biomarker | resta escluso: T790M + exon 19 deletion non è L858R |
| evidence:11599 | Lung Non-small Cell Carcinoma | no | verified_alias_match | biomarker | resta escluso: L858R + T790M compound non è single L858R |
| evidence:1867 | Lung Non-small Cell Carcinoma | no | verified_alias_match | biomarker | resta escluso: T790M non è L858R |

Nessuno degli statement ha un disease ontology ID. `evidence:11219` è stato
recuperato dai traversal source, biomarker e intervention; gli altri tre
dipendono in tutto o in parte da source/intervention-neighborhood ampi.

## Interpretazione

La causa EGFR è mista:

1. un gap locale e verificabile nel trattamento degli alias NSCLC;
2. retrieval V2 intenzionalmente ampio;
3. record generic/cross-disease non risolvibili senza review;
4. record non L858R che il fix congiuntivo deve continuare a escludere.

La review non autorizza a trasformare i qualificatori di stadio o setting in
equivalenza disease, né a recuperare record che falliscono il biomarcatore.
