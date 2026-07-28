# Chiusura dei blocker del rerun esplorativo

Fase: `v3-retriever-regression-closure/1.0`  
Supera: `v3-retriever-binding/1.4`  
Gate: `qualified_claim_structural_gate/1.1` -> `qualified_claim_structural_gate/1.2`  
Query misurate: 18

## Che cosa era rotto

Il gate del biomarcatore confrontava le espressioni per uguaglianza di
stringa normalizzata. Su un corpus in cui 64 claim su 148 portano
un'espressione booleana, quel confronto non distingue la congiunzione dalla
disgiunzione: le tratta come due stringhe opache, identiche nel modo in cui
falliscono. `evidence:11219` porta `EGFR L858R OR EGFR Exon 19 Deletion` e
veniva respinto su una query `EGFR L858R` — dove il letterale chiesto e' uno
dei due disgiunti — con lo stesso codice con cui veniva respinto un claim
congiuntivo soddisfatto a meta'.

## Che cosa e' cambiato

| Query | primary | warning | audit | rejected |
| --- | --- | --- | --- | --- |
| `RB-01-EGFR-L858R-NSCLC` | 22 -> 32 | 9 -> 10 | 155 -> 157 | 125 -> 112 |
| `RB-02-EGFR-L858R-LUAD` | 9 -> 10 | 22 -> 32 | 155 -> 157 | 125 -> 112 |
| `RB-12-UNKNOWN-DRUG-CODE` | 0 | 0 | 153 -> 155 | 158 -> 156 |
| `RB-13-UNKNOWN-DISEASE` | 0 | 0 | 157 -> 159 | 154 -> 152 |
| `RC-02-EGFR-EXON19-NSCLC` | 0 -> 10 | 0 -> 1 | 147 -> 149 | 164 -> 151 |
| `RC-03-EGFR-L858R-AND-T790M` | 1 -> 39 | 0 -> 11 | 147 -> 157 | 163 -> 104 |
| `RC-04-EGFR-T790M-AND-L858R` | 0 -> 39 | 0 -> 11 | 147 -> 157 | 164 -> 104 |

Le altre 11 query non cambiano una sola decisione: il loro
`bucket_assignment_digest` e' identico prima e dopo. Nessuna query FGFR2 o
ALK si muove — la correzione tocca solo le espressioni booleane di cui la
query soddisfa un membro.

## Endpoint protetti

| Endpoint | Esito | Deciso da |
| --- | --- | --- |
| `evidence:11219` su `RB-01-EGFR-L858R-NSCLC` | primary_ranked_results (disjunct_member) | claim_status — il disgiunto chiesto e' soddisfatto |
| `evidence:11219` su `RB-02-EGFR-L858R-LUAD` | retained_with_warning (disjunct_member) | disease — la malattia governa: LUAD e' figlia di NSCLC |
| `evidence:11598` su `RB-01-EGFR-L858R-NSCLC` | rejected_by_native_constraints (incompatible) | biomarker — congiunzione che la query non soddisfa |
| `evidence:11599` su `RB-01-EGFR-L858R-NSCLC` | rejected_by_native_constraints (conjunction_partially_satisfied) | biomarker — congiunzione soddisfatta a meta' |
| `evidence:1867` su `RC-01-EGFR-T790M-NSCLC` | primary_ranked_results (exact) | claim_status — identita' letterale |
| `evidence:8173` su `RB-04-FGFR2-ICCA` | rejected_by_native_constraints (incompatible) | biomarker — nessun disgiunto e' la fusione chiesta |

`evidence:1846` e `evidence:1847` non si muovono in nessuna delle
18 query: le loro espressioni non sono booleane.

## Che cosa e' rimasto fermo

- Il corpus promosso, verificato contro il proprio manifest.
- Il retriever legacy e la sua parita': il percorso non e' stato sfiorato.
- Il gate 1.1, il gate 1.0 e il contratto congelato: byte-identici.
- Gli artefatti della fase 1.4: **non rigenerati**. Un retriever costruito
  con `gate=integrated_gates_v11` ne ricalcola i quattordici digest byte
  per byte, ed e' cosi' che quella fase resta riproducibile invece che
  riscritta.
- I pesi di scoring, riletti dalla stessa configurazione operativa.
- Il gold, che questa fase non ha aperto.

## Prontezza del rerun

| Flag | Valore |
| --- | --- |
| `and_semantics_preserved` | **true** |
| `clinical_readiness` | false |
| `corpus_unchanged` | **true** |
| `diagnostic_endpoints_unchanged` | **true** |
| `evidence_11219_consistent_with_the_contract` | **true** |
| `evidence_8173_dominant_gate_is_the_biomarker` | **true** |
| `gold_read` | false |
| `operational_retriever_bound_to_v3` | false |
| `prior_phase_reproducible_under_gate_1_1` | **true** |
| `queries_measured` | 18 |
| `queries_with_changed_decisions` | 7 |

## Blocker residui

Nessuno. Le quattro discrepanze aperte sono chiuse, e ognuna e'
registrata in `finding_resolution.json` con lo stato prima e dopo.

`clinical_readiness` resta falso e non e' un blocker di questa fase:
nulla qui e' stato confrontato con il gold, e una idoneita' clinica non
si deduce da un retriever che decide meglio. Resta falso anche
`operational_retriever_bound_to_v3`: il default della pipeline non e'
stato spostato.

## Prossimo passo

Il rerun esplorativo comparativo. Le metriche contro il gold restano fuori
da questa fase, come dalla precedente.
