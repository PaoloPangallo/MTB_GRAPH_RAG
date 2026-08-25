# Relation-aware evaluation sample

This sample is frozen from GCA 2.0 metadata only. No parser, reader, provider, document API, or runtime output was used.

- Core commit: `dd010056ae348e42e66a6f0098c9e9eb26890d6b2`
- Selection seed: `20260825`
- Total: **36** (`PAPER_EVIDENCE=16`, `CLINICAL_TRIAL=10`, `KG_ONLY=10`)
- Candidate sample SHA256: `d168027b5e4994109c9cf1975a8d27bddcd214ae7d46a077a0aa4af594cc3233`

## Deterministic selection rules

Strata and counts were fixed before selection. Candidates were classified from actual PMID/NCT identifiers. Within each stratum, stable candidate IDs and deterministic novelty over document, disease, gene, variant, direction, intervention, source database, and graph path metadata were used. Paper and trial documents are unique within the sample. No output-aware criterion was used.

CASE-1 (`GCA-008ae3aad1a64c118318ef79`, PMID 19223544) and every valid 24-character GCA ID explicitly present in the research-pipeline semantic/development tests were excluded. The excluded development-exposure inventory was: `GCA-0031c17c5ff5ae29ff221b1e, GCA-003ca9889b3d8906d4674f37, GCA-008ae3aad1a64c118318ef79, GCA-6cb3e69e2badaaf63cdb75bd, GCA-7891d9f9f7fd9b803ce6e792, GCA-a082283f128c49620273b965, GCA-bd12d81e3b8b2f67728ca364`. Selected development-exposed candidates: 0.

## Frozen strata

| Family | Stratum | N | Snapshot available |
|---|---|---:|---:|
| PAPER_EVIDENCE | predictive_sensitivity_response | 6 | 0 |
| PAPER_EVIDENCE | resistance_reduced_adverse | 4 | 0 |
| PAPER_EVIDENCE | diagnostic | 2 | 0 |
| PAPER_EVIDENCE | prognostic | 2 | 0 |
| PAPER_EVIDENCE | other | 2 | 0 |
| CLINICAL_TRIAL | trial_drug | 5 | 0 |
| CLINICAL_TRIAL | trial_gene | 5 | 0 |
| KG_ONLY | gene_drug_interaction | 6 | 0 |
| KG_ONLY | companion_diagnostic | 4 | 0 |

## Inventory and limitations

- Unique selected PMIDs: 16.
- Unique selected NCTs: 10.
- Unique selected genes: 24.
- Unique selected diseases: 15.
- Development-exposed selected candidates: 0.
- Snapshot availability is an offline inventory only; missing snapshots are not an exclusion criterion for the next phase.
- No gold, expected support, expected quote, or trial outcome was created.
