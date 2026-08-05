# Retrieval deterministico

Nessun LLM coinvolto. Il "KG" interrogato è il repository statico
`GraphCandidateAssertion` (`graph_candidate_repository/2.0/candidates.jsonl`),
già la forma materializzata usata in tutto questo filone di ricerca — vedi
`current_component_audit.md` per la motivazione. Il retrieval è inoltre
limitato ai soli candidate che possiedono già almeno uno dei 25
EvidenceBundle congelati, così da non recuperare mai un documento nuovo.

## Bug reale trovato e corretto

Prima versione: preferiva il campo `gene` sul biomarcatore quando presente,
ignorando `normalized_value`. Per il Caso 3, il parser ha popolato
`gene="microsatellite"` (senza l'abbreviazione "MSI" o il qualificatore
"High" presenti invece in `normalized_value`), causando `NO_MATCH` per un
caso che doveva invece corrispondere (baseline PARTIAL, non assenza di
match). Corretto costruendo l'insieme dei termini di confronto dall'unione
di `gene`, `normalized_value` e `raw_value`, con corrispondenza per
sottostringa o token condiviso significativo (>2 caratteri) invece della
sola sottostringa esatta su un unico campo.

## Risultati finali (5 casi)

| Caso | Esito | Candidate | Motivo |
|---|---|---|---|
| 1 | 1 associazione | GCA-008ae3aad1a64c118318ef79 | DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE, INTERVENTION_COMPATIBLE |
| 2 | 1 associazione | GCA-0031c17c5ff5ae29ff221b1e | DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE, DISCOVERY_NO_INTERVENTION_FILTER |
| 3 | 1 associazione | GCA-02861e174359dd9f4f53df9b | DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE, INTERVENTION_COMPATIBLE |
| 4 | 1 associazione | GCA-0062c0237b990701837a1cc4 | DISEASE_COMPATIBLE, BIOMARKER_COMPATIBLE, INTERVENTION_COMPATIBLE |
| 5 | NO_MATCH | — | gene fabbricato assente da ogni candidate del repository |

Massimo 3 associazioni per caso (limite mai raggiunto: 1 associazione per
caso comparabile), massimo 4 SourceUnit per documento — entrambi rispettati
strutturalmente dal codice, verificati dai test
(`RetrievalTests.test_max_three_associations_per_case`,
`test_max_four_source_units_per_document`).
