# Readiness della politica disease

Fase `disease-hierarchy-policy/1.0`.

## Stato

| voce | stato |
|---|---|
| `corpus_promotion_ready` | no |
| `current_retriever_compatibility_audited` | si |
| `directional_relation_contract_frozen` | si |
| `explicit_hierarchy_relations_frozen` | si |
| `full_exploratory_rerun_ready` | no |
| `generic_scope_policy_frozen` | si |
| `ontology_warning_policy_frozen` | si |
| `operational_retriever_migration_ready` | no |
| `primary_bucket_identical_across_modes` | si |
| `shadow_disease_gate_update_ready` | si |
| `sibling_policy_frozen` | si |
| `strict_policy_frozen` | si |
| `terminology_shadow_update_ready` | si |
| `verified_alias_policy_frozen` | si |

Le tre voci finali restano chiuse per la stessa ragione di sempre: il
contratto e' definito e simulato, non applicato. Promuovere il corpus o
migrare il retriever sono decisioni successive, che questa fase prepara
e non prende.

## Audit del matcher operativo

### comportamento gia' compatibile

Il matcher operativo esclude gia' tutto cio' che non e' identita' verificata, e il retriever applica quell'esito come vincolo nativo prima di qualunque punteggio. La precedenza del gate sullo scoring non va introdotta: va nominata.

| elemento | oggi | contratto | riferimento |
|---|---|---|---|
| `HARD_MATCH_TYPES` | exact_string, normalized_exact, verified_alias | coincide con il primary bucket di strict_verified | `backend/pipeline/evidence/qualified_disease_matching.py::HARD_MATCH_TYPES` |
| `precedenza del gate` | hard_match_allowed e' un vincolo nativo valutato prima dello scoring | invariante esplicito DISEASE_GATE_PRECEDES_SCORING | `backend/pipeline/evidence/qualified_retriever.py::_native_constraints` |
| `parent, child e sibling` | riconosciuti e mai hard match | invariato quanto all'esclusione dal primario | `backend/pipeline/evidence/qualified_disease_matching.py::_relation_type` |

### vocabolario da rinominare

I nomi attuali non dicono la direzione, che e' esattamente cio' che il caso K1 chiede di preservare. Sono rinomine, non cambi di comportamento.

| elemento | oggi | contratto | riferimento |
|---|---|---|---|
| `explicit_child` | explicit_child | claim_is_child_of_query | `backend/pipeline/evidence/qualified_disease_matching.py::MATCH_EXPLICIT_CHILD` |
| `explicit_parent` | explicit_parent | claim_is_parent_of_query | `backend/pipeline/evidence/qualified_disease_matching.py::MATCH_EXPLICIT_PARENT` |
| `explicit_sibling` | explicit_sibling | disease_sibling | `backend/pipeline/evidence/qualified_disease_matching.py::MATCH_EXPLICIT_SIBLING` |
| `pan_cancer_or_unspecified` | pan_cancer_or_unspecified | generic_cancer_scope | `backend/pipeline/evidence/qualified_disease_matching.py::MATCH_PAN_CANCER_OR_UNSPECIFIED` |

### nuove categorie richieste

Oggi cross-disease, relazione irrisolta e disease mancante cadono tutte in unresolved. Sono tre situazioni diverse e portano a spiegazioni diverse.

| elemento | oggi | contratto | riferimento |
|---|---|---|---|
| `cross_disease` | collassato in unresolved | categoria propria, rejected_by_native_constraints | `backend/pipeline/evidence/qualified_disease_matching.py::_relation_type ramo finale` |
| `unresolved_disease_relation` | raccoglie anche cross-disease e disease mancanti | riservato ai casi senza alcun termine registrato | `backend/pipeline/evidence/qualified_disease_matching.py::MATCH_UNRESOLVED` |
| `relation_direction` | assente da DiseaseMatchResult | campo obbligatorio, calcolato dalle tabelle congelate | `backend/pipeline/evidence/qualified_disease_matching.py::DiseaseMatchResult` |
| `retained_with_warning` | il bucket non e' raggiungibile dall'asse disease | parent e child vi ricadono in tutte le modalita' | `benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/candidate_bucket_contract.json` |

### generic scope mancanti

Il registro operativo degli scope generici e' piu' stretto di quello del contratto, e il reason code che emette e' lo stesso di unresolved: a valle i due casi diventano indistinguibili.

| elemento | oggi | contratto | riferimento |
|---|---|---|---|
| `solid tumor` | assente da _PAN_CANCER_KEYS | presente in generic_scope_keys | `backend/pipeline/evidence/qualified_disease_matching.py::_PAN_CANCER_KEYS` |
| `unspecified tumor` | assente da _PAN_CANCER_KEYS | presente in generic_scope_keys | `backend/pipeline/evidence/qualified_disease_matching.py::_PAN_CANCER_KEYS` |
| `reason code dello scope generico` | DISEASE_RELATION_UNRESOLVED | GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC | `backend/pipeline/evidence/qualified_disease_matching.py::_REASON_BY_MATCH_TYPE` |

### missing disease oggi collassati in unresolved

Un core vuoto produce unresolved senza dire quale dei due lati manchi. Non sapere che cosa chiede la query e non sapere su che cosa vale il claim sono difetti diversi, e vanno riparati altrove.

| elemento | oggi | contratto | riferimento |
|---|---|---|---|
| `missing_query_disease` | unresolved | categoria propria, QUERY_DISEASE_MISSING | `backend/pipeline/evidence/qualified_disease_matching.py::match_disease ramo else finale` |
| `missing_claim_disease` | unresolved | categoria propria, CLAIM_DISEASE_SCOPE_MISSING | `backend/pipeline/evidence/qualified_disease_matching.py::match_disease ramo else finale` |

## Regressioni

| caso | relazione | exact | atteso |
|---|---|---|---|
| `PROBE-MISSING-CLAIM-DISEASE` | `missing_claim_disease` | no | Disease scope del claim assente: distinto da unresolved e da cross-disease. |
| `PROBE-NORMALIZED-EXACT` | `normalized_exact_disease` | si | Il qualificatore di stadio non cambia l'entita': normalized exact primary. |
| `PROBE-SCORE-GATE` | `claim_is_child_of_query` | no | Score massimo e segnali exact non aprono il primario a una relazione child. |
| `PROBE-UNRESOLVED-RELATION` | `unresolved_disease_relation` | no | Nessun termine registrato: relazione non decidibile, non cross-disease. |
| `REG-11219-DQ-01-EGFR-L858R-NSCLC` | `verified_disease_alias` | si | verified alias NSCLC e biomarcatore compatibile: primary |
| `REG-11219-DQ-05-ALK-G1202R-NSCLC` | `verified_disease_alias` | si | verified alias NSCLC ma biomarcatore incompatibile: escluso |
| `REG-11598-DQ-01-EGFR-L858R-NSCLC` | `verified_disease_alias` | si | alias disease compatibile, biomarcatore congiuntivo incompatibile: escluso |
| `REG-11599-DQ-01-EGFR-L858R-NSCLC` | `verified_disease_alias` | si | alias disease compatibile, profilo composto incompatibile: escluso |
| `REG-1846-DQ-03-FGFR2-ICCA` | `exact_disease` | si | exact primary sulla query iCCA |
| `REG-1846-DQ-04-FGFR2-CCA` | `claim_is_child_of_query` | no | child della query: warning, mai exact |
| `REG-1846-DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA` | `exact_disease` | si |  |
| `REG-1847-DQ-03-FGFR2-ICCA` | `exact_disease` | si | exact primary sulla query iCCA |
| `REG-1847-DQ-04-FGFR2-CCA` | `claim_is_child_of_query` | no | child della query: warning, mai exact |
| `REG-1847-DQ-10-DIAGNOSTIC-FGFR2-BICC1-ICCA` | `exact_disease` | si |  |
| `REG-1867-DQ-01-EGFR-L858R-NSCLC` | `verified_disease_alias` | si | alias disease compatibile, T790M incompatibile con L858R: escluso |
| `REG-8173-DQ-03-FGFR2-ICCA` | `disease_sibling` | no | sibling della query iCCA: audit-only, mai exact |
| `REG-8173-DQ-06-SIBLING-CCC` | `exact_disease` | si | exact sulla propria disease, non su iCCA |

## Integrita'

- parita' degli hash operativi: si
- shadow repository modificati: no
- corpus operativo modificato: no
- matcher operativo modificato: no
- riferimento di valutazione deserializzato: no

## Prossimo passo

Aggiornare il gate disease dello shadow repository usando questo
contratto, mantenendo `strict_verified` come modalita' di default. La
migrazione del matcher operativo resta chiusa fino a quando quel
passaggio non e' stato verificato sullo shadow.

