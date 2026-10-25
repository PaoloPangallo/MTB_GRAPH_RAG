# Provenance audit V3

## Baseline e metodo

Audit read-only sul branch audit/v3-provenance, commit iniziale
93fb99707623dac69a4a21be75208fb6a765ef34. La documentazione architetturale
usata come contesto è docs/repository_map/; il contratto claim/UI è
docs/v3_pipeline_ui/claim_data_contract_audit.md.

Sono stati letti i file del repository promosso
backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/ necessari
alla catena e quattro artefatti non ufficiali di source-unit review. Non sono
stati letti gold, ledger SQLite o run ufficiali. Non sono stati eseguiti
retrieval, benchmark, chiamate live o scritture di dati.

## Universo esatto

Il loader runtime legge evidence_claims.jsonl, deprecated_claims.jsonl,
graph_evidence_parents.jsonl, unsupported_associations.jsonl e
unresolved_associations.jsonl. Il backend V3 reidrata tutti questi oggetti.

| Insieme | Conteggio |
|---|---:|
| qualified claim attive | 148 |
| claim deprecate | 4 |
| parent GraphEvidenceRecord/provenance container | 147 |
| technical association record: unsupported + unresolved | 12 |
| technical_records nella response: parent + association + deprecated | 163 |
| candidate runtime complessive | 311 |

Le 311 candidate sono 148 + 4 + 147 + 6 + 6. Le claim attive sono 146
therapeutic e 2 diagnostic. Tra le attive ci sono 140 atomic, 3 aggregate e 3
regimen claim. Non ci sono claim prognostic. Il manifest dichiara 3 parent
senza child claim e 144 parent con almeno una claim; quattro parent hanno due
child claim.

Il numero 148 è quindi confermato dal repository corrente, non assunto dalla
documentazione precedente.

## Risultato principale

| Stato | Claim |
|---|---:|
| VERIFIED_LOCATOR | 17 |
| PARENT_ONLY | 131 |
| PUBLICATION_IDENTIFIER_ONLY | 0 |
| ALTERNATIVE_SOURCE_AVAILABLE | 0 |
| SOURCE_IDENTIFIER_MISSING | 0 |
| SOURCE_NOT_EXPECTED | 0 per le claim attive |
| PROVENANCE_BROKEN | 0 |
| PROVENANCE_UNCERTAIN | 0 |

Le 17 claim con locator hanno un source_id e un passaggio/testo o una
posizione di abstract. Le altre 131 hanno un parent esistente con source_ids
e source_record_ids, ma nella riga qualified claim hanno source_unit_ids vuoto
e locators vuoto. Il parent non viene usato come prova documentale diretta:
per questo lo stato è PARENT_ONLY.

## Catena A–E

- A Claim → Parent: PRESENT per 148/148. Nessun parent_id mancante e nessun
  graph_evidence_id incoerente.
- B Parent → Source Unit: PRESENT per le 17 claim in cui il binding source
  unit è sulla claim e il locator si riconcilia con l'identificatore del
  parent; MISSING per 131. Il parent JSON non espone source_unit_ids.
- C Source Unit → record originale: PRESENT per le 17 claim con source unit,
  locator e source ID esatto; MISSING per 131.
- D Record originale → identificatore: PRESENT per tutti i parent coinvolti:
  ogni parent ha source_record_ids e source_ids.
- E Identificatore → locator/testo: PRESENT per 17 claim; MISSING per 131,
  perché il parent espone identificatori ma non locator o testo nel record
  promosso.

Il dettaglio per riga è in provenance_inventory.csv, con i cinque campi
claim_to_parent, parent_to_source_unit, source_unit_to_original,
original_to_identifier e identifier_to_locator.

## Punto di perdita più probabile

La diagnosi prevalente è DATA_PRESENT_BUT_NOT_PROPAGATED, con
first_missing_link=PARENT_TO_SOURCE_UNIT. Il dato documentale non è assente
dal parent: il parent conserva identificatori PUBMED:* o, in un caso,
DOI: oltre a evidence:*#row-*. La qualified claim però non conserva il
binding source-unit/locator.

L'evidenza osservata localizza la perdita prima del serializer e dell'adapter
API: i campi sono già vuoti in evidence_claims.jsonl, mentre
v3_result.py::build_provenance propaga i campi presenti nel record. Non è
quindi dimostrato che l'adapter abbia eliminato questi identificatori.

La causa precisa tra costruzione GraphEvidenceRecord, trasformazione typed
claim e materializzazione non è dimostrabile dal repository promosso; viene
marcata come FIELD_MAPPING_MISSING da ispezionare, non come fatto già provato.

## Identificatori

A livello diretto della qualified claim:

- PMID: 17 claim;
- DOI: 0;
- NCT: 0;
- URL: 0;
- locator: 17.

Nel parent-context, senza promuoverlo a fonte diretta della claim:

- parent con PMID: 147 claim;
- parent con DOI: 1 claim;
- parent con NCT: 0.

Il parent DOI-only è la claim CLM-6016e0878e055658200e
(FGFR1/pemigatinib). I valori e i conteggi di occorrenza/uniqueness sono in
source_identifier_distribution.csv.

publication_title, source_type, url e graph_node_id non sono campi presenti
nelle righe qualified claim attive. Sono disponibili graph_evidence_id, parent
source_record_ids e source IDs parent. Non è stata costruita alcuna URL, non è
stato recuperato alcun titolo e non è stato convertito un parent ID in
identificatore bibliografico.

## Differenze per dominio e asse

La tabella completa è in domain_provenance_summary.csv. I gruppi sono
intenzionalmente non mutuamente esclusivi quando descrivono un asse.

- therapeutic: 146 claim, 15 con PMID diretto, 15 con locator, 131
  parent-only;
- diagnostic: 2 claim, entrambe con PMID e locator diretti;
- resistance: 49 claim, 4 con PMID/locator diretto, 45 parent-only;
- aggregate: 3 claim, tutte con PMID e locator diretti; 2 sono preclinical;
- regimen: 3 claim, tutte con PMID e locator diretti;
- preclinical: 2 claim, entrambe con PMID e locator diretto;
- trial: 0;
- companion diagnostics: 0;
- altri domini: 0.

## Controlli di integrità

- 148/148 claim ID unici;
- 148/148 parent ID esistenti;
- 148/148 graph evidence ID coerenti con il parent;
- 0 child claim riferiti a claim inesistenti;
- 0 claim mancanti dalla lista child del parent;
- 147/147 parent con source_record_ids;
- 147/147 parent con source_ids;
- 0 riferimenti strutturali rotti;
- 17/17 identificatori diretti coerenti con gli identificatori del parent;
- 17 occorrenze dirette su 9 identificatori unici: le ripetizioni sono fonti
  condivise tra claim e non assegnazioni inventate;
- un source-unit ID, SU-26698910-patient-c1156y-crizotinib-first-line, non
  compare negli artefatti ausiliari review usati; non viene dichiarato rotto
  perché non esiste un registro canonico source-unit con cui dimostrarlo;
- nessun identificatore inventato.

Per gli esempi richiesti consultare pilot_claims.md. Le riparazioni non sono
state applicate: recommended_repairs.md è solo progettuale.
