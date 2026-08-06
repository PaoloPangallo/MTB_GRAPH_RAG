# 14 — Decisione finale

## Le cinque domande

### 1. La nuova GraphCandidateAssertion conserva esplicitamente la differenza fra direzione del grafo e posizione della fonte?

**Sì.** Sono quattro campi distinti di primo livello:

```json
{
  "graph_direction": "RESISTANCE",
  "source_support_polarity": "DOES_NOT_SUPPORT_ASSERTION",
  "source_supported_direction": null,
  "source_alignment_status": "SOURCE_DOES_NOT_SUPPORT"
}
```

`graph_direction` copre i 18 valori di `significance` osservati, nessuno
collassato; `source_support_polarity` deriva da `evidence_direction`, che in v2
non entrava nel contratto. `source_polarity_lost = 0`.

### 2. Una fonte «Does Not Support» può ancora produrre una candidate presentata come positivamente supportata?

**No.**

```
unsupported_candidates_promoted_as_supported = 0
automatic_direction_inversions               = 0
```

873 candidate hanno `SOURCE_DOES_NOT_SUPPORT` e **nessuna** è `SOURCE_ALIGNED`.
L'invariante `INV2` lo rende impossibile a livello di contratto, `INV2B` impedisce
di dichiarare una direzione sostenuta senza supporto, e un test verifica
sull'intero repository che nessuna candidate violi la regola.

`DOES_NOT_SUPPORT` non è convertito nella direzione opposta:
`source_supported_direction` resta `null`, perché «non sostiene una resistenza»
non significa «sostiene una sensibilità».

### 3. Tutti i termini e gli operatori delle alterazioni composte sono preservati, oppure i casi non parsabili sono dichiarati esplicitamente?

**Sì, tutti preservati** — e non ci sono casi non parsabili.

```
compound_alteration_terms_lost     = 0
compound_operator_lost             = 0
compound_expression_parse_failures = 0
compound_alterations_preserved     = 1010
```

Su tutti e 1 939 i profili molecolari: 0 fallimenti. `AND`, `OR`, `NOT`,
parentesi di raggruppamento e annidamento sono conservati nell'AST, con hash
diversi per `AND` e `OR`. Il meccanismo per dichiarare l'indecidibilità esiste
(`MALFORMED_EXPRESSION`, `UNSUPPORTED_EXPRESSION`, `AMBIGUOUS_OPERATOR`) ed è
coperto da test, ma su questo corpus non viene mai attivato.

### 4. I regimi multi-farmaco sono mantenuti come unità o marcati come semanticamente irrisolti, senza attribuire arbitrariamente l'effetto ai singoli componenti?

**Sì, entrambe le cose.**

```
unresolved_regimens_split_into_positive_components = 0
invented_regimen_semantics                         = 0
unresolved_regimen_count                           = 572
confirmed_regimen_count                            = 0
```

I 572 record multi-farmaco producono 572 candidate a livello di unità, marcate
`MULTI_COMPONENT_UNRESOLVED` / `SEMANTICS_UNAVAILABLE_IN_SOURCE`, con tutti i
componenti conservati, nessun ruolo inventato e nessun farmaco principale scelto.
Non sono eleggibili al match esatto sull'intervento.

`confirmed_regimen_count = 0` non è una lacuna: l'export non consente di
confermare nessuna combinazione, e `INV5` impedisce di affermarla.

In v2 gli stessi record producevano **1 294** candidate positive indipendenti.

### 5. La materializzazione v3 è strutturalmente completa e semanticamente più fedele alla sorgente rispetto alla v2?

**Sì per entrambe, con una qualificazione.**

Strutturalmente: `structural_precision = 1.0`, `structural_recall = 1.0`,
46 864/46 864 path coperti, 0 mancanti, 0 spuri, `payload_reproducibility = 1.0`,
`duplicate_rate = 0.0`, `lineage_integrity = 1.0`, 0 violazioni di invariante.

Semanticamente: i tre difetti misurati su v2 — 486 inversioni, 1 091 alterazioni
perse, 1 294 regimi spezzati, **2 419 candidate (5.16 %)** — sono **0** in v3.

La qualificazione: «più fedele» è dimostrato **per i tre difetti misurati**, non
in generale. v3 potrebbe avere perdite semantiche non ancora individuate, come
v2 le aveva prima dell'audit RQ1. E la fedeltà è ai **metadati** della sorgente,
non alla letteratura: se `evidence_direction` fosse annotato male, v3 lo
riprodurrebbe fedelmente.

---

## Conferme richieste

```
repository_v2_unchanged                            = true
repository_v3_created                              = true
source_export_used                                 = true
neo4j_used                                         = false
llm_used_for_graph_semantics                       = false
oncokb_called                                      = false
source_polarity_preserved                          = true
source_polarity_lost                               = 0
does_not_support_inverted                          = 0
unsupported_candidates_promoted_as_supported       = 0
automatic_direction_inversions                     = 0
compound_alterations_preserved                     = true
compound_alteration_terms_lost                     = 0
compound_operators_lost                            = 0
compound_expression_parse_failures                 = 0
unresolved_regimens_preserved_as_units             = true
unresolved_regimens_split_into_components          = 0
invented_regimen_semantics                         = 0
structural_materialization_precision               = 1.0
structural_materialization_recall                  = 1.0
semantic_source_fidelity_measured                  = true
runtime_default_changed_to_v3                      = false
shadow_comparison_completed                        = true
manual_review_sample_created                       = true   (70 record, non 75)
push_executed                                      = false
merge_executed                                     = false
```

## Decisione

**v3 è pronta per la fase shadow, non per il default del runtime.**

Prima di cambiare `GRAPH_CANDIDATE_REPOSITORY_VERSION` a `3.0`:

1. annotare il campione manuale a 70 record;
2. implementare il Pre-Retrieval Eligibility Gate con test dedicati, applicando
   la policy di `09_runtime_admission_policy.md`;
3. eseguire i test di regressione end-to-end sui cinque casi sintetici con v3;
4. decidere esplicitamente il trattamento delle **1 034** candidate rimosse dal
   percorso positivo (873 `DOES_NOT_SUPPORT` + 161 `SOURCE_NEUTRAL`): oggi sono
   conservate per audit, ma nessun ramo del runtime le consuma.

Il punto 4 è il più importante. v3 rende visibile una popolazione che v2
nascondeva; renderla visibile non è ancora averla gestita.
