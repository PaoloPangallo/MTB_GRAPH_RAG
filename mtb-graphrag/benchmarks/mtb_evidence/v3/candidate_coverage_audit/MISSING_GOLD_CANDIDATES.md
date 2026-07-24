# Audit dei cinque evidence ID indicati dalla valutazione

La causa di ogni assenza è stata calcolata nel passaggio no-gold. Soltanto dopo
il congelamento degli hash è stato aperto il bundle gold per associare i claim.
Il gold non ha cambiato alcuna classificazione.

| Evidence ID | Statement | Query storica | Presenze | Primo punto di divergenza | Causa | Tipo |
|---|---|---|---|---|---|---|
| `evidence:11219` | `ES-V2-evidence-11219` | EGFR | V2, snapshot, repository, corpus, indici | filtro disease | `disease_normalization_gap` | limite di schema |
| `evidence:11598` | `ES-V2-evidence-11598` | EGFR | V2, snapshot, repository, corpus, indici | filtro disease | `disease_normalization_gap` | limite di schema |
| `evidence:11599` | `ES-V2-evidence-11599` | EGFR | V2, snapshot, repository, corpus, indici | filtro disease | `disease_normalization_gap` | limite di schema |
| `evidence:1867` | `ES-V2-evidence-1867` | EGFR | V2, snapshot, repository, corpus, indici | filtro disease | `disease_normalization_gap` | limite di schema |
| `evidence:8173` | `ES-V2-evidence-8173` | FGFR2 | V2, snapshot, repository, corpus, indici | filtro disease | `V2_traversal_semantics_not_represented` | differenza semantica |

I primi quattro statement usano `Lung Non-small Cell Carcinoma`; la query EGFR
non contiene questa forma fra disease e alias. `evidence:8173` usa
`Cholangiolocellular Carcinoma`, che non viene equiparata a
`Intrahepatic Cholangiocarcinoma`.

Le associazioni tardive al gold sono:

- `evidence:11219` → `C1-C2`;
- `evidence:11598`, `evidence:11599`, `evidence:1867` → `C1-C3`;
- `evidence:8173` → `K1-C1`.

L'associazione è documentale per fonte e intervento. Non è stata usata per
stabilire se la causa fosse un bug né per alterare il retrieval.
