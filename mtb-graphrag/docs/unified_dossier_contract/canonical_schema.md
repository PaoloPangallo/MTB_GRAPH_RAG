# Canonical schema

Il dossier contiene:

- `dossier_version`, `run`, `case_context`, `generated_at`;
- `core_result`: risultato V3 congelato, inclusi claims, bucket, score, gate,
  evidenze, reason codes, abstention e technical records;
- `claim_extensions[claim_id]`: provenance, document support, ontology
  alignment e clinical actionability senza duplicare la claim;
- `diagnostic_context`: record diagnostici strutturali, anche senza
  `claim_id`;
- `module_status`: maturità, modalità, stato, scope e limitazioni;
- `association_diagnostics`: orphan records e riferimenti mancanti;
- `limitations`.

`run.core_snapshot_integrity` conserva `before_hash`, `after_hash` e
`unchanged`.
