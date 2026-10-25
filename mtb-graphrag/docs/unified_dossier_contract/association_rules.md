# Association rules

Consentito:

- `claim_extensions` → `core_result.claims` tramite exact `claim_id`.
- diagnostic records → `diagnostic_context.records` tramite graph identifiers.

Vietato usare gene, malattia, farmaco, PMID, titolo o similarità testuale come
join. Gli extension records senza claim corrispondente diventano
`association_diagnostics.orphan_records`; non vengono agganciati
euristicamente.
