# Inventario degli asset ontologici locali

| Dominio | Asset locale | Evidenza disponibile | Limite |
|---|---|---|---|
| Disease | `verified_alias_registry_snapshot.json` | 4 gruppi di alias: CCA, iCCA, lung adenocarcinoma, NSCLC | nessun CURIE esterno; chiavi locali soltanto |
| Disease | `explicit_hierarchy_relations.jsonl` | 6 archi parent/child verificati, inclusi lung adenocarcinoma → NSCLC e iCCA → CCA | relazione direzionale, non equivalenza clinica |
| Disease | `disease_relation_definitions.json` e policy locali | exact, alias, parent/child, sibling, incompatibile | gerarchia limitata agli asset presenti |
| Intervention | `pilot/audit_lib/aliases.py::DRUG_ALIASES` | 14 alias locali verificati verso pemigatinib, futibatinib, lorlatinib, osimertinib | nessuna copertura generale di sale/classi |
| Intervention | `v3/terminology_mapping_closure/canonicalization_contract.json` | contratto e mapping locali, incluso il caso BGJ398/infigratinib quando eleggibile | mapping pending/prototype non promosso |
| Diagnostic | `v3/non_therapeutic_source_closure/diagnostic_claim_reviews.jsonl` | FGFR2::BICC1 Fusion e FGFR2::AHCYL1 Fusion | nessun ontology ID o companion-diagnostic ontology |
| Case model | `schemas/case_graph.schema.json` | campi `ontology`, `ontology_id`, `parent_concept`, `specificity` per disease e finding | non costituisce una registry completa |
| Qualified claims | `qualified_claim_repository_1_4` | 146 therapeutic + 2 diagnostic non-deprecated | non modificato |
| Parent context | `graph_evidence_parents.jsonl` | contesto disease, biomarker e interventi parent | contesto parent non è prova di supporto claim-specifico |

Il Knowledge Graph è stato documentato come asset locale/frozen source nei file del repository, ma non è stato interrogato né arricchito. Non è stata trovata una tabella locale completa di CURIE per i 148 record.
