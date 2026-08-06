# 06 — CandidateRuntimeAdmission

Il repository v3 rende visibili **1 034** candidate che v2 nascondeva
(873 `SOURCE_DOES_NOT_SUPPORT` + 161 `SOURCE_NEUTRAL`). Renderle visibili non
era averle gestite: questo e' il punto in cui il runtime decide che farne.

## Oggetto

`candidate_id`, `admission_status`, `source_alignment_status`,
`alteration_match_status`, `intervention_match_status`, `direction_status`,
`reason_codes`, `allowed_branches`, `warning_codes`, `source_stage`,
`policy_version`, `producer`.

## Stati

| Stato | Ramo |
|---|---|
| `ADMITTED_NORMAL_GROUNDING` | positivo |
| `ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN` | positivo + polarita' ignota |
| `ADMITTED_NEGATIVE_AUDIT_BRANCH` | negativo/audit |
| `ADMITTED_NEUTRAL_AUDIT_BRANCH` | neutro/audit |
| `ADMITTED_CONTRADICTION_AUDIT_BRANCH` | contraddizione/audit |
| `AUDIT_ONLY_UNRESOLVED_REGIMEN` | regime irrisolto |
| `AUDIT_ONLY_UNSUPPORTED_EXPRESSION` | alterazione non analizzabile |
| `REJECTED_SOURCE_DOES_NOT_SUPPORT_POSITIVE_USE` | escluso |
| `REJECTED_ALTERATION_MISMATCH` | escluso |
| `REJECTED_ALTERATION_INSUFFICIENT` | escluso |
| `REJECTED_INTERVENTION_MISMATCH` | escluso |
| `REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH` | escluso dall'exact match |

## Tre decisioni indipendenti

Non collassate in un booleano: **polarita' della fonte**, **alterazione**,
**intervento**. Una candidate puo' essere allineata e nondimeno esclusa perche'
l'alterazione non corrisponde.

## Verifica sull'intero repository

Un test scorre tutte le 46 142 candidate v3 e verifica che **nessuna**
`SOURCE_DOES_NOT_SUPPORT` entri nel ramo positivo.

```
source_does_not_support_positive_promotions = 0
source_neutral_positive_promotions          = 0
```
