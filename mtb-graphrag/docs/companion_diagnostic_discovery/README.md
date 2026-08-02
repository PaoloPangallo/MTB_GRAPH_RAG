# Companion diagnostic discovery — read-only pilot

Questo documento congela l'esito di un pilota locale di scoperta e modellazione
dei dati diagnostici del Knowledge Graph. Il pilota parte dal commit d9b2a7f e
non implementa il dominio companion diagnostic nel runtime V3.

## Esito sintetico

Lo snapshot locale contiene 166 nodi CompanionDiagnostic e 150 archi
HAS_COMPANION_DIAGNOSTIC. I nodi espongono device, farmaco associato, gene,
piattaforma e tipo di campione. Il grafo consente quindi una visualizzazione
letterale di alcune associazioni test--gene--farmaco, ma non contiene una
provenance claim-safe completa, un collegamento diagnostico esplicito alla
malattia o una relazione normativa/clinica che permetta di classificare in modo
affidabile un record come companion diagnostic.

Le due claim diagnostiche attive V3 sono record diagnostici di tipo
subtype-defining/biomarker diagnostic evidence. Nessuna delle due è promossa
come companion diagnostic.

Raccomandazione: B. SOLO VISUALIZZAZIONE. Conservare i dati diagnostici in una
superficie esplorativa separata, senza materializzazione di claim e senza
riuso automatico dei gate terapeutici.

## Fonti locali utilizzate

- benchmarks/mtb_evidence/pilot/audit/graph_snapshot_manifest.json
- benchmarks/mtb_evidence/pilot/audit/schema_inventory.json
- backend/pipeline/cypher.py
- backend/api/subgraph.py
- backend/pipeline/agents/target_identifier.py
- backend/pipeline/evidence/v2_adapter.py
- backend/pipeline/evidence/shadow/
- backend/pipeline/evidence/corpus/
- benchmarks/mtb_evidence/evaluation/data/non_therapeutic_audit_v1.jsonl
- docs/pmid_pilot/claim_document_alignment.csv

Non sono stati interrogati servizi esterni e non è stato eseguito alcun
traversal live del database. I conteggi provengono dallo snapshot locale.

## Confini

Il pilota non modifica Knowledge Graph, repository qualified claims,
provenance overlay, gate, score, bucket, endpoint V3, frontend, ledger, gold,
benchmark, PMID pilot o ontology shadow MVP.
