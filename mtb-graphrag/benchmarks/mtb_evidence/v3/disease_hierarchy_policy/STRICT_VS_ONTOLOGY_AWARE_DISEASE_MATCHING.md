# Strict, ontology-aware e audit

Contratto `directional-disease-match-contract/1.0`.

## Che cosa cambia, e che cosa no

Il bucket primario e' **identico nelle tre modalita'**: exact, normalized
exact e verified alias soltanto. Non esiste una modalita' broad, e non deve
esistere: una modalita' che riportasse parent o child nel primario direbbe
al lettore che quel claim risponde alla domanda posta, che e' esattamente
cio' che la relazione nega.

Cio' che cambia fra le modalita' e' che cosa si fa di una relazione che non
e' identita', non se lo diventa.


### `exact_disease`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `primary_ranked_results` | si | si | si |
| `ontology_aware_warning` | `primary_ranked_results` | si | si | si |
| `audit_all` | `primary_ranked_results` | si | si | si |

### `normalized_exact_disease`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `primary_ranked_results` | si | si | si |
| `ontology_aware_warning` | `primary_ranked_results` | si | si | si |
| `audit_all` | `primary_ranked_results` | si | si | si |

### `verified_disease_alias`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `primary_ranked_results` | si | si | si |
| `ontology_aware_warning` | `primary_ranked_results` | si | si | si |
| `audit_all` | `primary_ranked_results` | si | si | si |

### `claim_is_child_of_query`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `retained_with_warning` | no | no | no |
| `ontology_aware_warning` | `retained_with_warning` | no | no | si |
| `audit_all` | `retained_with_warning` | no | no | si |

### `claim_is_parent_of_query`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `retained_with_warning` | no | no | no |
| `ontology_aware_warning` | `retained_with_warning` | no | no | si |
| `audit_all` | `retained_with_warning` | no | no | si |

### `disease_sibling`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `audit_only_results` | no | no | no |
| `ontology_aware_warning` | `audit_only_results` | no | no | no |
| `audit_all` | `audit_only_results` | no | no | no |

### `generic_cancer_scope`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `audit_only_results` | no | no | no |
| `ontology_aware_warning` | `retained_with_warning` | no | no | si |
| `audit_all` | `retained_with_warning` | no | no | si |

### `cross_disease`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `rejected_by_native_constraints` | no | no | no |
| `ontology_aware_warning` | `rejected_by_native_constraints` | no | no | no |
| `audit_all` | `rejected_by_native_constraints` | no | no | no |

### `unresolved_disease_relation`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `audit_only_results` | no | no | no |
| `ontology_aware_warning` | `audit_only_results` | no | no | no |
| `audit_all` | `audit_only_results` | no | no | no |

### `missing_query_disease`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `audit_only_results` | no | no | no |
| `ontology_aware_warning` | `audit_only_results` | no | no | no |
| `audit_all` | `audit_only_results` | no | no | no |

### `missing_claim_disease`

| modalita' | bucket | primary | score strutturale | score qualificato |
|---|---|---|---|---|
| `strict_verified` | `audit_only_results` | no | no | no |
| `ontology_aware_warning` | `audit_only_results` | no | no | no |
| `audit_all` | `audit_only_results` | no | no | no |

## Parent e child

Restano visibili in tutte e tre le modalita', nel bucket
`retained_with_warning`. Il claim e' pertinente e nasconderlo perderebbe
informazione; presentarlo nel primario direbbe una cosa falsa. In
`strict_verified` non ricevono alcun punteggio. In
`ontology_aware_warning` e in `audit_all` possono essere ordinati
fra loro: il punteggio qualificato serve a ordinare dentro il bucket
warning, non a competere con il primario.

## Il gate precede lo score

Lo score strutturale e' riservato alle sole relazioni di identita'
(exact_disease, normalized_exact_disease, verified_disease_alias). Nessun segnale successivo —
biomarcatore exact, intervento exact, qualita' della fonte,
qualificazione, provenance, punteggio arbitrariamente elevato — puo'
cambiare il bucket assegnato dal gate disease. Il caso `PROBE-SCORE-GATE`
lo verifica iniettando tutti quei segnali insieme su una relazione child.

## Per query e modalita'

| query | modalita' | primary | warning | audit | rejected |
|---|---|---|---|---|---|
| `DQ-01-EGFR-L858R-NSCLC` | `audit_all` | 78 | 30 | 0 | 40 |
| `DQ-01-EGFR-L858R-NSCLC` | `ontology_aware_warning` | 78 | 30 | 0 | 40 |
| `DQ-01-EGFR-L858R-NSCLC` | `strict_verified` | 78 | 22 | 8 | 40 |
| `DQ-02-EGFR-L858R-LUAD` | `audit_all` | 22 | 89 | 0 | 37 |
| `DQ-02-EGFR-L858R-LUAD` | `ontology_aware_warning` | 22 | 89 | 0 | 37 |
| `DQ-02-EGFR-L858R-LUAD` | `strict_verified` | 22 | 81 | 8 | 37 |
| `DQ-03-FGFR2-ICCA` | `audit_all` | 3 | 18 | 1 | 126 |
| `DQ-03-FGFR2-ICCA` | `ontology_aware_warning` | 3 | 18 | 1 | 126 |
| `DQ-03-FGFR2-ICCA` | `strict_verified` | 3 | 10 | 9 | 126 |
| `DQ-04-FGFR2-CCA` | `audit_all` | 10 | 12 | 0 | 126 |
| `DQ-04-FGFR2-CCA` | `ontology_aware_warning` | 10 | 12 | 0 | 126 |
| `DQ-04-FGFR2-CCA` | `strict_verified` | 10 | 4 | 8 | 126 |
| `DQ-05-ALK-G1202R-NSCLC` | `audit_all` | 80 | 30 | 0 | 38 |
| `DQ-05-ALK-G1202R-NSCLC` | `ontology_aware_warning` | 80 | 30 | 0 | 38 |
| `DQ-05-ALK-G1202R-NSCLC` | `strict_verified` | 80 | 22 | 8 | 38 |
| `DQ-06-SIBLING-CCC` | `audit_all` | 1 | 18 | 3 | 126 |
| `DQ-06-SIBLING-CCC` | `ontology_aware_warning` | 1 | 18 | 3 | 126 |
| `DQ-06-SIBLING-CCC` | `strict_verified` | 1 | 10 | 11 | 126 |
| `DQ-07-GENERIC-CANCER` | `audit_all` | 8 | 140 | 0 | 0 |
| `DQ-07-GENERIC-CANCER` | `ontology_aware_warning` | 8 | 140 | 0 | 0 |
| `DQ-07-GENERIC-CANCER` | `strict_verified` | 8 | 0 | 140 | 0 |
| `DQ-08-MISSING-DISEASE` | `audit_all` | 0 | 0 | 148 | 0 |
| `DQ-08-MISSING-DISEASE` | `ontology_aware_warning` | 0 | 0 | 148 | 0 |
| `DQ-08-MISSING-DISEASE` | `strict_verified` | 0 | 0 | 148 | 0 |
| `DQ-09-CROSS-DISEASE` | `audit_all` | 4 | 8 | 19 | 117 |
| `DQ-09-CROSS-DISEASE` | `ontology_aware_warning` | 4 | 8 | 19 | 117 |
| `DQ-09-CROSS-DISEASE` | `strict_verified` | 4 | 0 | 27 | 117 |
| `DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA` | `audit_all` | 3 | 18 | 1 | 126 |
| `DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA` | `ontology_aware_warning` | 3 | 18 | 1 | 126 |
| `DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA` | `strict_verified` | 3 | 10 | 9 | 126 |

La colonna primary non cambia mai fra le tre righe di una stessa query.
E' l'invariante che rende la modalita' una scelta di presentazione e non
una scelta di verita'.

