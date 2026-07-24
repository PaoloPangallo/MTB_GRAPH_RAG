# Disease normalization review V2/V3

## Esito

La review read-only ha classificato tutte le 109 righe V2 nei due casi target:
81 EGFR-L858R (73 graph evidence ID) e 28 FGFR2-iCCA (25 graph evidence ID).
Il retriever, il corpus 2.0, i normalizzatori, gli alias, i mapping, lo scoring,
il gold e gli audit precedenti non sono stati modificati.

La perdita di coverage non ha una sola causa. Il filtro V3 usa un confronto
normalizzato esatto sui valori disease della query; non usa il normalizzatore
disease locale. I traversal V2 congelati erano invece biomarker-, gene-, drug-
o source-neighborhood e nessuno applicava un vincolo disease.

## Inventario sintetico

| Caso | Righe V2 | Graph ID | Biomarker match post-fix | Disease match V3 | Match congiunto |
|---|---:|---:|---:|---:|---:|
| EGFR-L858R | 81 | 73 | 56 | 17 | 10 |
| FGFR2-iCCA | 28 | 25 | 17 | 1 | 1 |

Le classificazioni disease sulle righe V2 sono:

| Classificazione | EGFR | FGFR2 |
|---|---:|---:|
| normalized exact | 0 | 1 |
| verified alias | 54 | 0 |
| broader label con relazione locale esplicita | 0 | 12 |
| narrower label con relazione locale esplicita | 17 | 0 |
| sibling esplicito, non equivalente | 0 | 1 |
| pan-cancer/unspecified | 6 | 1 |
| relazione non disponibile localmente | 4 | 13 |

Non sono stati assegnati `different_disease` sulla sola base del nome. In
assenza di identificatori o relazioni locali esplicite, il valore è
`unresolved_without_external_or_document_review`.

## Traversal V2

| Caso | Semantica | Occorrenze |
|---|---|---:|
| EGFR | biomarker_only | 57 |
| EGFR | intervention_neighborhood | 28 |
| EGFR | source_neighborhood | 4 |
| FGFR2 | biomarker_only | 17 |
| FGFR2 | gene_neighborhood | 8 |
| FGFR2 | intervention_neighborhood | 5 |

Una riga può avere più origini. Tutte le 119 occorrenze di traversal hanno
`disease_constraint_applied=false`.

## Root cause

Per EGFR, 38 righe biomarker-compatible (32 graph ID) con disease
`Lung Non-small Cell Carcinoma` falliscono il filtro V3, benché
`Non-Small Cell Lung Cancer` sia già un alias della query e il normalizzatore
locale rappresenti le due etichette come stesso ente. È un gap di allineamento
tra contratto alias e filtro, dimostrabile localmente. Dieci righe
biomarker-compatible con `Lung Adenocarcinoma` sopravvivono al filtro corrente
perché il valore è dichiarato come alias nella query, ma la relazione locale lo
classifica come sottotipo più stretto, non come equivalenza. Altre otto righe
biomarker-compatible sono generiche o senza relazione locale verificabile.

Per FGFR2, una riga è un exact iCCA. Dieci righe biomarker-compatible (sette
graph ID) usano `Cholangiocarcinoma`, parent esplicito locale di iCCA; non sono
equivalenti e richiedono una policy gerarchica. `evidence:8173` usa
`Cholangiolocellular Carcinoma`, sottotipo fratello esplicito: resta non
equivalente e richiede domain review. Cinque righe biomarker-compatible hanno
contesto generico o relazione non rappresentata.

## Unità di conteggio e multi-intervento

Quindici righe EGFR (sette graph ID) e sei righe FGFR2 (tre graph ID)
appartengono a gruppi multi-intervento. La review conserva separatamente i flag
`disease_mismatch`, `biomarker_mismatch` e `multi_intervention`; non attribuisce
alla disease le differenze prodotte dalla serializzazione di più interventi.

## Limiti

La review usa soltanto output congelati, record strutturati, corpus,
normalizzatori e audit locali. Non legge PMID, non consulta ontologie esterne e
non usa il gold per classificare le relazioni. Non misura precision, recall,
applicabilità clinica o qualità finale del retrieval.
