# ESCAT presence audit

Audit locale, read-only, eseguito senza interrogare servizi esterni e senza
modificare il pilota companion diagnostic.

## Esito

Nel Knowledge Graph locale non è presente un campo ESCAT sui nodi, sugli
archi, sui GraphEvidenceRecord o sulle source unit attive. Lo schema del nodo
Evidence contiene evidence_level, ma il suo vocabolario reale è generico e
misto: nei dati locali compaiono A, B, C, D e valori LEVEL_*; il codice
adapter li tratta rispettivamente come CIViC o OncoKB. Nessuno di questi valori
è stato riclassificato come ESCAT.

Il contratto EvidenceStatement contiene un enum system che ammette escat, ma
questa è una capacità dello schema, non un'annotazione presente nei record
attivi. Le 148 qualified claim attive non contengono escat, escat_tier,
actionability_level, evidence_tier o clinical_actionability.

Il campo escat_tier esiste nel runtime legacy come output calcolato dal
variant_interpreter e presentato da API/frontend legacy. Non è un attributo
del Knowledge Graph e non entra nell'endpoint V3 qualificato.

Raccomandazione: **E. ESCAT non realmente presente nei dati attivi**.

## Scope e provenienza

- Snapshot locale: graph_snapshot_manifest.json, timestamp 2026-07-21,
  commit snapshot c295e1d.
- Schema locale: schema_inventory.json.
- Repository attivo: qualified_claim_repository/1.4, 146 claim terapeutiche
  e 2 diagnostiche.
- Audit raw locale: 1.525 record nei quattro raw_records.jsonl presenti nei
  casi di audit.

Il manifest segnala che il grafo è stato caricato da CSV in più ondate e non
ha un release ID o checksum ufficiale del provider. Questa limitazione vale
anche per qualunque futuro tentativo di propagazione del livello.

## File

- [Inventario del grafo](escat_graph_inventory.md)
- [Trace runtime](escat_runtime_trace.md)
- [Valori](escat_values.csv)
- [Copertura claim](escat_claim_coverage.csv)
- [Mismatch di contesto](escat_context_mismatches.csv)
- [Summary](escat_summary.json)
- [Raccomandazione](recommended_integration.md)
