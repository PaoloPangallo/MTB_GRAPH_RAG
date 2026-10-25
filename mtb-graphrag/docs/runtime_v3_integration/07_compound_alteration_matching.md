# 07 — Matching delle alterazioni composte

`evaluate_alteration_expression` era gia' implementata e testata in `gca_v3`, ma
**non collegata al runtime**. Ora lo e'.

## Regole

| Espressione | CaseContext verificato | Esito |
|---|---|---|
| `A AND B` | `A` e `B` | `FULL_MATCH` |
| `A AND B` | solo `A` | `PARTIAL_MATCH` — **mai** `FULL_MATCH` |
| `A OR B` | solo `A` | `FULL_MATCH` |
| `A` | nessun biomarcatore | `INSUFFICIENT_CASE_INFORMATION` |
| qualunque | espressione non analizzabile | `EXPRESSION_UNSUPPORTED` |

## Cosa non conta come presente

Il matching usa **solo i campi verificati dal gate**. Non contribuiscono:

* un'alterazione **negata**;
* una menzione dentro uno span di **istruzione di controllo**;
* una menzione rifiutata per tipo o ruolo.

Un'alterazione **incerta** e' accettata come campo ma non produce
automaticamente `FULL_MATCH`: resta soggetta alla stessa regola AND/OR.

## Policy di ammissione

| Esito | Trattamento |
|---|---|
| `FULL_MATCH` | ammissione possibile |
| `PARTIAL_MATCH` | `REJECTED_ALTERATION_INSUFFICIENT`, ramo alterazione parziale |
| `INSUFFICIENT_CASE_INFORMATION` | non promossa, warning |
| `NO_MATCH` | candidate esclusa |
| `EXPRESSION_UNSUPPORTED` | audit-only, mai exact match |

```
compound_full_match_correct       = true
compound_partial_promoted_to_full = 0
compound_terms_lost               = 0
```
