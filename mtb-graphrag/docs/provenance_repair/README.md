# V3 provenance repair pilot

Pilota conservativo non-default derivato dal repository `qualified_claim_repository/1.4`.
Il repository 1.4 resta invariato e il retriever operativo non è collegato alla versione 1.5.

## Output

- `provenance_materialization_trace.md`: percorso reale e punto di perdita.
- `safe_propagation_rules.md`: regole di promozione senza fallback dal parent.
- `pilot_claims_before_after.csv`: inventario before/after delle claim pilota.
- `ambiguous_claims.csv`: claim non promosse.
- `provenance_repair_report.md`: conteggi e decisione finale.
- `repository_version_diff.md`: differenza tra 1.4 e overlay 1.5.

Il mapping esterno letto è `benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3/qualification_link_regeneration_plan_v1_3.jsonl`, usato come evidenza già esplicita e non modificato.
