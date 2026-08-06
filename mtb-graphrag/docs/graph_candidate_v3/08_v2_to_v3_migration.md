# 08 — Migrazione v2 → v3

## Principio

**Non si converte v2 in v3.** v3 è rimaterializzata dai CSV; il mapping è
prodotto *a posteriori*, accoppiando le due versioni sui **path sorgente** che
entrambe dichiarano.

`graph_candidate_repository/2.0` resta immutato come baseline sperimentale
storica. Nessun record storico è cancellato.

## Risultato

| `relation_type` | Righe | Significato |
|---|---|---|
| `ONE_TO_ONE` | 45 570 | il path v2 corrisponde a una sola candidate v3 |
| `MANY_TO_ONE` | **1 294** | più path v2 (uno per farmaco) confluiscono in una candidate di regime |
| `REMOVED_UNSUPPORTED` | 0 | nessuna candidate rimossa per fonte non sostenuta |
| `REMOVED_UNRESOLVED_REGIMEN` | 0 | nessuna rimossa: i regimi irrisolti sono **conservati** |
| `NEWLY_RECOVERED_COMPOUND` | 0 | vedi sotto |
| `UNMAPPED` | 0 | ogni candidate v2 è mappata |
| **Totale** | **46 864** | = candidate v2 |

`reason_code` per le `MANY_TO_ONE`: `REGIMEN_UNIT_MERGED`.

## Perché `NEWLY_RECOVERED_COMPOUND = 0`

Le alterazioni composte **non generano nuove candidate**: arricchiscono quelle
esistenti. Il profilo `EGFR T790M AND Exon 19 Del AND C797S` produceva una
candidate in v2 (con la sola `T790M`) e ne produce una in v3 (con tutti e tre i
termini e l'AST). Il recupero è di **contenuto**, non di cardinalità.

Questo è il motivo per cui la differenza di conteggio (−722) è interamente
spiegata dai regimi e non dalle alterazioni.

## Le 1 294 → 572

| | |
|---|---|
| Archi farmaco su record multi-farmaco (v2) | 1 294 |
| Record Evidence multi-farmaco | 572 |
| Candidate v3 di regime prodotte | 572 |

Ogni candidate v2 rimossa dal percorso positivo è raggiungibile: il suo id
compare nel mapping con il `v3_candidate_id` dell'unità che la contiene, e i
componenti sono elencati in `intervention_components`.

## Artefatti

| File | Contenuto |
|---|---|
| `graph_candidate_repository/3.0/v2_mapping.jsonl` | mapping completo, una riga per relazione |
| `evaluation/gca_v3/v2_to_v3_mapping.csv` | stesso contenuto in CSV |

Campi: `v2_candidate_id`, `v3_candidate_id`, `relation_type`, `reason_code`,
`notes`.

## Verifica

Un test (`test_v2_to_v3_mapping_covers_every_v2_candidate`) verifica che il
mapping copra tutte e 46 864 le candidate v2 e che le `MANY_TO_ONE` siano
esattamente 1 294 con `reason_code = REGIMEN_UNIT_MERGED`.

Un secondo test (`test_v2_repository_is_unchanged`) verifica lo SHA-256 di v2.
