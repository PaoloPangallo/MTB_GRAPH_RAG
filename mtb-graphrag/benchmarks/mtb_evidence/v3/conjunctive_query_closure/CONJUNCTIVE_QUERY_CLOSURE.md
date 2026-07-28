# Chiusura direzionale delle query congiuntive

Fase: `v3-conjunctive-query-closure/1.0`  
Supera: `v3-retriever-regression-closure/1.0`  
Gate: `qualified_claim_structural_gate/1.2` -> `qualified_claim_structural_gate/1.3`  
Query misurate: 21

## Che cosa era rotto

Il gate 1.2 decideva le congiunzioni con una regola sola: i termini del
claim contenuti in quelli della query bastano. E' vera come implicazione
logica e sbagliata come affermazione clinica. Una query
`EGFR L858R AND EGFR T790M` descrive un paziente co-alterato; un claim su
`EGFR L858R` da solo e' stato misurato su una popolazione che quella
co-alterazione non aveva, e il suo risultato non e' separabile. La regola
lo portava nel bucket primario.

La direzione conta, e conta in tutti e due i versi. Un claim piu' generale
della query e' evidenza indebolita: warning. Un claim piu' specifico della
query parla di un'altra popolazione: respinto. Il secondo verso non e'
simmetrico al primo, e tenerli insieme era il difetto.

## Riclassificazione

`conjunction_satisfied` raggiungeva **50
claim distinti**. Nessuno di loro raggiunge piu' il bucket primario.

| Bucket | prima | dopo |
| --- | --- | --- |
| `audit_only_results` | 8 | 8 |
| `primary_ranked_results` | 29 | 0 |
| `rejected_by_native_constraints` | 3 | 3 |
| `retained_with_warning` | 10 | 39 |

Gli otto in audit e i tre respinti non si muovono: un altro gate li teneva
gia' li', e la direzione del biomarcatore non li solleva. I ventinove che
erano primari sono ora trattenuti con avviso, insieme ai dieci che gia' lo
erano.

Il delta completo — claim, i due match type, i due bucket e i codici — sta
in `conjunctive_directional_delta.jsonl`, 255 righe.

## Che cosa e' cambiato, query per query

| Query | operatore | primary | warning | audit | rejected |
| --- | --- | --- | --- | --- | --- |
| `RC-03-EGFR-L858R-AND-T790M` | `and` | 39 -> 1 | 11 -> 49 | 157 | 104 |
| `RC-04-EGFR-T790M-AND-L858R` | `and` | 39 -> 1 | 11 -> 49 | 157 | 104 |
| `CQ-01-CLAIM-REQUIRES-ADDITIONAL` | `and` | 17 -> 1 | 3 -> 19 | 149 | 142 |
| `CQ-02-PARTIAL-OVERLAP` | `and` | 7 -> 0 | 1 -> 8 | 147 | 156 |
| `CQ-03-DISJUNCTIVE-CLAIM` | `and` | 32 -> 0 | 10 -> 42 | 157 | 112 |

Le altre 16 query non cambiano una sola decisione. Sono tutte e
sole le query che non portano un AND: la correzione riguarda un verso che
solo una query congiuntiva puo' percorrere.

## Endpoint protetti

| Endpoint | Query | Esito | Match |
| --- | --- | --- | --- |
| `evidence:11219` | `RB-01-EGFR-L858R-NSCLC` | primary_ranked_results | disjunct_member |
| `evidence:11219` | `RB-02-EGFR-L858R-LUAD` | retained_with_warning | disjunct_member |
| `evidence:11598` | `RB-01-EGFR-L858R-NSCLC` | rejected_by_native_constraints | incompatible |
| `evidence:11599` | `RB-01-EGFR-L858R-NSCLC` | rejected_by_native_constraints | conjunction_partially_satisfied |
| `evidence:1867` | `RC-01-EGFR-T790M-NSCLC` | primary_ranked_results | exact |
| `evidence:8173` | `RB-04-FGFR2-ICCA` | rejected_by_native_constraints | incompatible |
| `evidence:11219` | `CQ-03-DISJUNCTIVE-CLAIM` | retained_with_warning **cambiato** | result_not_separable_for_coaltered_query |

I cinque endpoint della fase precedente sono invariati su tutte le query
non congiuntive. `evidence:11219` cambia soltanto sotto una query
congiuntiva, dove il suo claim disgiuntivo non e' separabile per il caso
co-alterato: passa da primario a trattenuto con avviso, e non e' una
regressione ma la decisione che questa fase esiste per prendere.

## Che cosa e' rimasto fermo

- Il gate 1.2, il 1.1, il 1.0 e il contratto congelato: byte-identici.
- `biomarker_expression.py`: la semantica booleana non e' stata toccata,
  la direzione vive in un modulo separato.
- Il corpus promosso, il retriever legacy, i pesi di scoring.
- Gli artefatti delle fasi 1.4 e della chiusura delle regressioni:
  **non rigenerati**. Un retriever costruito con `gate=integrated_gates_v11`
  o `gate=integrated_gates_v12` li ricalcola byte per byte.
- Il gold, che questa fase non ha aperto.

## Prontezza del rerun

| Flag | Valore |
| --- | --- |
| `clinical_readiness` | false |
| `conjunctive_queries_measured` | 6 |
| `core_suite_independent_of_external_inputs` | **true** |
| `corpus_parity_unchanged` | **true** |
| `exact_conjunction_semantics_frozen` | **true** |
| `gold_read` | false |
| `isolated_worktree_green` | false |
| `legacy_parity_unchanged` | **true** |
| `non_conjunctive_queries_unchanged` | **true** |
| `operational_retriever_bound_to_v3` | false |
| `partial_conjunction_never_primary` | **true** |
| `reclassified_claims` | 50 |
| `strict_subset_never_primary` | **true** |
| `superseded_rule_leaves_no_primary` | **true** |

## Blocker residui

Nessuno sull'asse del biomarcatore. `clinical_readiness` resta falso e non
e' un blocker di questa fase: nulla e' stato confrontato con il gold.
