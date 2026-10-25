# Provenance materialization trace

```text
qualified_claim_repository/1.4/evidence_claims.jsonl
  -> retrieval/v3_objects.py::claim_object
  -> corpus/materialization.py::promoted_claims
  -> qualified_claim_repository_1_5_provenance_pilot
```

`claim_object()` conserva `source_unit_ids` e `locators` quando sono presenti. `promoted_claims()` copia il record senza risolvere claim -> source unit. L'audit mostra che 131 righe della 1.4 arrivano già con `source_unit_ids=[]` e `locators=[]`; il parent conserva `source_ids` e `source_record_ids`, ma questi non sono prova claim-specifica.

Il materializzatore aggiunge `provenance_repair` solo alle claim pilota. Copia source unit e locator esclusivamente da un mapping claim-specifico già documentato; negli altri casi registra `PARENT_PUBLICATION_AVAILABLE` o `AMBIGUOUS_PARENT_PROVENANCE`. Non modifica testo, campi clinici, gate, score o bucket.

La pipeline V3 e il registry di default non leggono l'overlay 1.5.
