# 06 — Identità e deduplicazione

## Chiave canonica v3

`candidate_id = "GCA3-" + sha256(payload)[:24]`, dove il payload include, in
ordine fisso (`contract.PAYLOAD_FIELDS`):

| Gruppo | Campi |
|---|---|
| Relazione | `materialization_rule_id`, `subject`, `predicate`, `object`, `disease` |
| Polarità | `graph_direction`, `source_support_polarity`, `source_supported_direction`, `source_alignment_status` |
| Alterazione | `alteration_expression_raw`, `alteration_expression_ast`, `alteration_parse_status` |
| Intervento | `intervention_expression_raw`, `intervention_components`, `intervention_structure`, `regimen_semantics_status`, `regimen_id` |
| Provenance | `biomarkers`, `evidence_scope`, `diagnostic_scope`, `graph_path`, `node_ids`, `edge_ids`, `evidence_record_ids`, `document_identifiers`, `source_properties` |

## Cosa la chiave distingue, e che v2 non distingueva

| Coppia | Distinta? | Perché |
|---|---|---|
| `SUPPORTS` vs `DOES_NOT_SUPPORT` | **sì** | `source_support_polarity` è nel payload |
| sensitivity vs resistance | **sì** | `graph_direction` è nel payload |
| `A AND B` vs `A OR B` | **sì** | l'AST è nel payload e i due hanno hash diversi |
| monoterapia vs combinazione | **sì** | `intervention_structure` + `intervention_components` |
| combinazione vs componenti individuali | **sì** | il `regimen_id` e la lista dei componenti differiscono |
| provenance diversa su path semanticamente distinti | **sì** | `node_ids`, `edge_ids`, `source_properties` |

In v2 le prime due coppie collassavano: `direction` derivava dalla sola
`significance`, quindi due candidate con polarità opposta avevano lo stesso
contenuto salvo `source_properties`.

## Deduplicazione osservata

| Metrica | Valore |
|---|---|
| `candidate_id` ripetuti | **0** |
| `duplicate_rate` | **0.0** |
| `payload_reproducibility` | **1.0** |

Nessuna deduplicazione arbitraria è applicata: due candidate che affermano la
stessa cosa da path diversi restano due candidate, come in v2.

## Relazione fra identificatori

Il repository pubblica due direzioni:

```
candidate_v2_id  →  candidate_v3_id[]      v2_mapping.jsonl · v2_to_v3_mapping.csv
candidate_v3_id  →  source_path_id[]       lineage_index.jsonl · campo source_path_ids
```

| `relation_type` | Righe |
|---|---|
| `ONE_TO_ONE` | 45 570 |
| `MANY_TO_ONE` — `REGIMEN_UNIT_MERGED` | 1 294 |
| **Totale** | **46 864** = candidate v2 |

Il mapping è ricavato dai **path sorgente**, non convertendo i record v2: ogni
candidate di entrambe le versioni dichiara i path da cui deriva, e i due insiemi
si accoppiano su quelli.

## Invariante di determinismo

`INV6` verifica che `candidate_id` e `payload_hash` siano ricalcolabili dal
payload serializzato. Violazioni su 46 142 candidate: **0**.
