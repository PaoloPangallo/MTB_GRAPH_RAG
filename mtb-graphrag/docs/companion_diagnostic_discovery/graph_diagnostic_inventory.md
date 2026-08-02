# Inventario diagnostico del grafo

## Snapshot

Il riferimento è graph_snapshot_manifest.json, snapshot locale del 2026-07-21.
Il manifest registra 43.003 nodi e 61.185 relazioni; l'origine è un caricamento
CSV incrementale descritto da import.cypher. Non è stato interrogato il
database indicato nel manifest.

### Etichette e conteggi

| label | count |
|---|---:|
| CompanionDiagnostic | 166 |
| Disease | 334 |
| Drug | 24.502 |
| Evidence | 4.860 |
| Gene | 1.437 |
| MolecularProfile | 1.937 |
| Publication | 2.222 |
| Variant | 1.975 |
| ClinicalTrial | 5.570 |

### Relazioni presenti nello snapshot

| relationship | count | rilevanza diagnostica |
|---|---:|---|
| HAS_COMPANION_DIAGNOSTIC | 150 | collegamento Drug -> CompanionDiagnostic |
| DIAGNOSES_GENE | 163 | collegamento diagnostico verso Gene |
| TESTS_DRUG | 8.018 | relazione farmacologica, non dimostra CDx |
| HAS_DISEASE | 4.684 | relazione generale del grafo |
| HAS_EVIDENCE | 4.860 | relazione Evidence |
| CITED_IN | 4.840 | relazione verso Publication |
| ASSOCIATED_GENE | 5.501 | associazione molecolare generale |
| HAS_VARIANT | 1.727 | associazione a variante |
| IN_MOLECULAR_PROFILE | 2.281 | appartenenza a profilo |
| TARGETS_DRUG | 3.372 | relazione di target |
| INTERACTS_WITH | 25.589 | relazione di interazione |

Non risultano nello schema snapshot archi nominati per
DIAGNOSTIC_USES_TECHNOLOGY, DIAGNOSTIC_REQUIRES_SPECIMEN,
THERAPY_REQUIRES_DIAGNOSTIC o DIAGNOSTIC_APPROVED_FOR_DISEASE.

## Proprietà realmente presenti

I nodi CompanionDiagnostic hanno:

- device_id
- device_name
- associated_drug
- gene_symbol
- platform_type
- specimen_types

Un esempio reale nello schema locale è il device Abbott RealTime IDH1
associato a Ivosidenib o Olutasidenib, gene IDH1, piattaforma PCR e campioni
Bone marrow, Peripheral Blood. È un esempio di struttura dati, non una prova
di approvazione regolatoria o di efficacia.

I nodi Disease hanno disease_id, doid, doid_uri, name. I nodi Publication hanno
pmid, pubmed_url, citation_text, source_type, year. I nodi Evidence hanno
statement, tipo, direzione, livello, disease testuale e citation_id.

## Risposte alle domande di inventario

- Tipo esplicito di nodo diagnostico: CompanionDiagnostic.
- Companion diagnostic espliciti: sì, come label/nodo e come nome della
  relazione HAS_COMPANION_DIAGNOSTIC; non come classificazione regolatoria
  documentata per ogni record.
- Test--biomarcatore: parzialmente, tramite gene_symbol e il grafo
  DIAGNOSES_GENE; non è presente un assay-level statement per variante,
  sensibilità o specificità.
- Test--malattia: non è presente una proprietà/relazione CDx-specifica nello
  schema inventariato.
- Test--terapia: sì, il nodo è raggiungibile da Drug tramite
  HAS_COMPANION_DIAGNOSTIC e contiene associated_drug; questo non equivale a
  therapy requires diagnostic.
- Test--tecnologia: presente come platform_type.
- Test--campione: presente come specimen_types.
- Test--fonte/versione/stato regolatorio: non risultano proprietà CDx
  corrispondenti nello schema locale.

Il grafo contiene quindi un vocabolario strutturale minimo per la
visualizzazione, ma dati insufficienti per distinguere in modo claim-safe
diagnostica generica, companion, complementary, screening e conferma.
