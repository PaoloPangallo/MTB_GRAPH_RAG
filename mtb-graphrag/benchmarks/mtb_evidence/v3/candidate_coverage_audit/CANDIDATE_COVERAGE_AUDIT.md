# Candidate coverage audit V2/V3

Audit version: `candidate-coverage-audit/1.0`.

## Esito

La differenza di candidate coverage non deriva da statement persi durante la
materializzazione: tutti i 122 record V2 storici puntano a uno dei 147
EvidenceStatement e tutti gli statement corrispondenti sono presenti nel corpus
2.0 e negli indici V3.

Le divergenze avvengono dopo la materializzazione:

- 48 graph evidence ID vengono esclusi per la forma di disease
  `Lung Non-small Cell Carcinoma`, non inclusa nelle chiavi esatte della query
  EGFR;
- 36 graph evidence ID vengono esclusi perché i traversal V2 comprendevano
  record ottenuti tramite percorsi per gene, farmaco o fonte che non rispettano
  la disease o il biomarcatore nativo della query V3;
- 23 extra ALK vengono inclusi perché il matcher del biomarcatore accetta
  `gene OR alteration`: `ALK` è sufficiente anche quando l'alterazione non è
  G1202R;
- 11 righe V2 in eccesso sono la serializzazione di graph evidence già contate,
  una volta per ogni farmaco collegato. Il corpus corrente conserva un solo
  intervento per EvidenceStatement.

La diagnosi è stata assegnata prima dell'accesso al gold. Il gold ha soltanto
annotato cinque ID già classificati e non ha modificato cause, filtri o proposte.

## Conteggi

| Query | V2 righe | V2 graph ID | V3 candidate | Overlap graph ID | Missing graph ID | Extra V3 |
|---|---:|---:|---:|---:|---:|---:|
| ALK-G1202R | 13 | 13 | 32 | 9 | 4 | 23 |
| EGFR-L858R | 81 | 73 | 17 | 17 | 56 | 0 |
| FGFR2-iCCA | 28 | 25 | 1 | 1 | 24 | 0 |
| RMI2 | 0 | 0 | 0 | 0 | 0 | 0 |

`v2_compatibility`, `native_only` e `qualified_soft` hanno lo stesso candidate
set congelato per tutte le query. La qualificazione modifica score e warning,
non la candidate generation.

## Root cause per query

### EGFR-L858R

Dei 56 graph ID mancanti:

- 48 hanno disease `Lung Non-small Cell Carcinoma`. Il filtro esatto confronta
  tale valore con `advanced/metastatic nsclc`, `lung adenocarcinoma` e
  `non-small cell lung cancer`. La divergenza primaria è
  `disease_normalization_gap`;
- 8 provengono da semantiche V2 più larghe: disease generica o diversa, oppure
  il record ERBB2 T798I ottenuto da un percorso non limitato al biomarcatore
  L858R. La causa è `V2_traversal_semantics_not_represented`.

Il gap NSCLC è dimostrabile sintatticamente, ma la correzione non è stata
applicata: `cancer` e `carcinoma` non vengono dichiarati sinonimi senza una
mappatura terminologica revisionata.

### FGFR2-iCCA

I 24 graph ID mancanti sono una differenza attesa tra traversal e contratto:

- 20 passano il match largo sul gene ma falliscono la disease;
- 4 sono evidenze FGFR1 recuperate dai traversal V2 per i farmaci attesi e
  falliscono già il biomarcatore.

La normalizzazione storica dichiara esplicitamente che
`intrahepatic cholangiocarcinoma` non equivale automaticamente a
`cholangiocarcinoma`. Il filtro non è stato allargato.

### ALK-G1202R

Quattro record V2 G1202R falliscono la disease nativa (`Cancer`,
`Lung Adenocarcinoma`, `Malignant Pleural Mesothelioma`). I 23 extra V3 hanno
invece `gene_match=true`, `alteration_match=false` e
`combined_native_biomarker_match=true`. Sono classificati tutti
`normalization_overreach`, non evidenza aggiuntiva validata.

### RMI2

Il caso resta `true_no_evidence_in_snapshot`: zero record e zero candidati in
tutte le modalità. Nessuna query, mappatura o fonte è stata ampliata.

## Coverage per identità in qualified_soft

| Query | Livello | V2 | V3 | Overlap | Coverage V2 |
|---|---|---:|---:|---:|---:|
| ALK | graph ID / statement | 13 | 32 | 9 | 69,23% |
| ALK | source | 16 | 23 | 15 | 93,75% |
| ALK | terapia | 7 | 8 | 7 | 100% |
| ALK | biomarcatore-intervento-direzione | 12 | 28 | 9 | 75% |
| EGFR | graph ID / statement | 73 | 17 | 17 | 23,29% |
| EGFR | source | 55 | 15 | 15 | 27,27% |
| EGFR | terapia | 15 | 5 | 5 | 33,33% |
| EGFR | biomarcatore-intervento-direzione | 35 | 10 | 10 | 28,57% |
| FGFR2 | graph ID / statement | 25 | 1 | 1 | 4% |
| FGFR2 | source | 17 | 1 | 1 | 5,88% |
| FGFR2 | terapia | 10 | 1 | 1 | 10% |
| FGFR2 | biomarcatore-intervento-direzione | 24 | 1 | 1 | 4,17% |

Queste sono metriche descrittive di rappresentazione. Non misurano efficacia,
applicabilità o qualità clinica.

## Deduplicazione e conversione

V2 serializza 11 righe oltre i graph ID unici:

- EGFR: 8 righe aggiuntive su sette graph evidence;
- FGFR2: 3 righe aggiuntive su tre graph evidence;
- ALK e RMI2: nessuna.

Ogni duplicato corrisponde a un diverso `TARGETS_DRUG` dello stesso record.
L'adapter ha materializzato un solo EvidenceStatement e un solo intervento.
Questo è `adapter_conversion_loss` a livello record/intervento, ma non una
perdita del graph evidence ID.

## Integrità e determinismo

L'harness valida prima di leggere gli input:

- corpus fingerprint
  `99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd`;
- frozen KG fingerprint
  `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`;
- scoring config hash
  `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`;
- corpus, retriever, 70 packet, author approval, output V2 e precedente
  esplorazione tramite hash aggregati registrati nel manifest.

Due esecuzioni e l'inversione dell'ordine degli input producono gli stessi byte
per gli artefatti causali. Non sono stati usati servizi esterni.
