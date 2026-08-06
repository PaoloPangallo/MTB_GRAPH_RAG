# 15 — Report finale

## Le otto domande

### 1. Un input vuoto, fuori dominio, non azionabile o contraddittorio può ancora raggiungere il Knowledge Graph?

**No.**

```
empty_casecontext_retrieval  = 0
out_of_scope_retrieval       = 0
non_actionable_retrieval     = 0
contradictory_case_retrieval = 0
```

27 dei 35 casi del benchmark si fermano al gate. Di questi, **18 si fermerebbero
anche se il modello producesse una tool call perfettamente valida**: prima si
fermavano solo perché il modello rifiutava di produrla. La fermata è ora una
proprietà dell'architettura.

### 2. Una mention presente nel testo ma semanticamente incompatibile con lo slot può ancora popolare il CaseContext canonico?

**No.**

```
symptom_copied_into_disease_field = 0
```

Il verifier semantico aggiunge compatibilità di tipo, ruolo e asserzione al
verifier testuale, che non è indebolito e conserva il potere di veto. `SYMPTOM`
non è ammesso in `disease`, e lo slot `disease` richiede un ancoraggio
oncologico. Le menzioni rifiutate restano visibili con il proprio motivo.

### 3. Le istruzioni avversariali possono ancora contaminare disease, biomarker o target intervention?

**Non nelle forme del benchmark congelato.**

```
injected_drug_extracted_as_target = 0
control_instruction_execution     = 0
```

Il rilevatore è una lista di pattern, conservativa e ancorata a verbi imperativi.
**Non risolve universalmente la prompt injection** e questo lavoro non lo
afferma: copre le forme del benchmark e impedisce la contaminazione dei campi.
Una formulazione nuova potrebbe non essere riconosciuta.

Quando un'istruzione convive con un caso clinico valido, le menzioni contenute
negli span di controllo sono rimosse e solo il contenuto clinico indipendente è
valutato (`G5`).

### 4. Il runtime distingue SOURCE_ALIGNED, SOURCE_DOES_NOT_SUPPORT, SOURCE_NEUTRAL e SOURCE_ALIGNMENT_NOT_AVAILABLE?

**Sì**, con quattro trattamenti distinti: grounding normale, ramo negativo/audit,
ramo neutro, ammissione con warning `SOURCE_POLARITY_UNAVAILABLE` e
`DOCUMENT_GROUNDING_STILL_REQUIRED`.

### 5. Una candidate Does Not Support o Neutral può ancora entrare nel ramo positivo?

**No.**

```
source_does_not_support_positive_promotions = 0
source_neutral_positive_promotions          = 0
```

Verificato da un test che scorre **tutte** le 46 142 candidate v3, non su
fixture. `graph_direction` è preservata e non invertita.

### 6. Le alterazioni composte rispettano realmente AND e OR durante il matching?

**Sì.** `A AND B` richiede entrambi, `A OR B` almeno uno, e `PARTIAL_MATCH` non
è mai promosso a `FULL_MATCH`. Le menzioni negate o contenute in istruzioni di
controllo non contribuiscono, perché il matching usa solo i campi verificati dal
gate.

```
compound_partial_promoted_to_full = 0
compound_terms_lost               = 0
```

### 7. Un regime multi-component unresolved può ancora produrre supporto per un singolo farmaco?

**No.**

```
unresolved_regimen_component_promotions = 0
invented_regimen_semantics              = 0
```

`REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH` in evaluation,
`AUDIT_ONLY_UNRESOLVED_REGIMEN` in discovery. La presenza di tutti i nomi non
produce `COMBINATION_CONFIRMED`.

### 8. La Verifiable Research Pipeline è pronta a usare graph_candidate_repository/3.0 come default?

**No.** I criteri formali del §24 sono soddisfatti, ma tre condizioni sostanziali
non lo sono:

1. il **ponte dei bundle** (id v2 → id v3) non è validato caso per caso;
2. il **campione manuale v3** a 70 record non è annotato;
3. il percorso **end-to-end fino al dossier** non è stato eseguito con v3: la
   separazione dei rami è definita e testata all'ammissione, non esercitata su
   dati reali.

```
research_runtime_default_repository = "2.0"
runtime_default_changed_to_v3       = false
```

L'eligibility gate è però attivo **su entrambe le versioni**: i difetti 4–10
dell'audit sono corretti già con il default `2.0`. Il beneficio maggiore non
dipendeva da v3, ed è la ragione per cui il gate è stato integrato separatamente
dal cambio di default.

---

## Conferme

```
ollama_default_endpoint_fixed                = true
casecontext_contract_extended                = true
typed_mentions_available                     = true
semantic_verifier_enabled                    = true
contradiction_detector_enabled               = true
pre_retrieval_eligibility_gate_enabled       = true
empty_casecontext_retrieval                  = 0
out_of_scope_retrieval                       = 0
non_actionable_retrieval                     = 0
contradictory_case_retrieval                 = 0
symptom_copied_into_disease_field            = 0
injected_drug_extracted_as_target            = 0
forbidden_downstream_calls                   = 0
control_instruction_execution                = 0
repository_v2_unchanged                      = true
repository_v3_loaded                         = true
research_runtime_default_repository          = "2.0"
legacy_runtime_repository                    = "1.4"
source_does_not_support_positive_promotions  = 0
source_neutral_positive_promotions           = 0
source_polarity_unknown_handled_with_warning = true
compound_full_match_correct                  = true
compound_partial_promoted_to_full            = 0
compound_terms_lost                          = 0
unresolved_regimen_component_promotions      = 0
audit_only_branch_enabled                    = true
negative_branch_enabled                      = true
neutral_branch_enabled                       = true
v2_v3_shadow_completed                       = true
frozen_rq4_benchmark_modified                = false
oncokb_called                                = false
validator_weakened                           = false
drug_synonym_hardcoding_added                = false
runtime_tests_passed                         = true
evaluation_tests_passed                      = true
frontend_tests_passed                        = true
end_to_end_tests_passed                      = true
push_executed                                = false
merge_executed                               = false
```

## Casi end-to-end

| Caso | Atteso | Esito |
|---|---|---|
| A — complete therapy evaluation | `ELIGIBLE_FOR_RETRIEVAL` | ✅ |
| B — therapy discovery | `ELIGIBLE_FOR_RETRIEVAL`, intervento `NOT_APPLICABLE` | ✅ |
| C — empty input | `INVALID_INPUT` | ✅ |
| D — out of scope | `OUT_OF_SCOPE` | ✅ |
| E — non-actionable | `NON_ACTIONABLE_MEDICAL_INPUT`, disease null | ✅ |
| F — contradictory | `CONTRADICTORY_CASE_CONTEXT` | ✅ |
| G — adversarial | `ADVERSARIAL_OR_CONTROL_INPUT`, farmaco non accettato | ✅ |
| H — compound full match | `FULL_MATCH` | ✅ |
| I — compound partial match | `PARTIAL_MATCH`, mai `FULL_MATCH` | ✅ |
| J — source does not support | ramo negativo/audit | ✅ |
| K — source neutral | ramo neutro | ✅ |
| L — multi-component unresolved | rejection dell'exact match | ✅ |

12 su 12.

## Test

| Suite | Esito |
|---|---|
| Backend runtime | **3 047 passed**, 17 skipped, 36 860 subtest |
| Frontend | **195 passed** (13 nuovi) |
| Evaluation | **91 passed** |

La suite frontend ha una **flakiness preesistente** in esecuzione parallela
completa (2–3 fallimenti non deterministici, prima e dopo queste modifiche); con
`--no-file-parallelism` passano tutti e 195.

## Hard stop

Nessuno.

## Prossimo checkpoint

OncoKB, come previsto: solo dopo che il caso è dichiarato eleggibile, la
GraphCandidateAssertion è semanticamente utilizzabile, le chiavi
disease/gene/alteration sono sufficienti e non esiste un identificatore
documentale utilizzabile. Le prime due condizioni sono ora verificabili dal
runtime; la terza resta il limite documentato in RQ3, che v3 non ha cambiato.
