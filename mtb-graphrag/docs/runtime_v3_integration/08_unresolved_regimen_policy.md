# 08 — Policy sui regimi irrisolti

572 candidate v3 hanno `intervention_structure = MULTI_COMPONENT_UNRESOLVED`:
l'export non distingue combinazione, alternativa e sequenza.

## Regole

| Intento | Trattamento |
|---|---|
| `THERAPY_EVALUATION` con target singolo | `REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH` — nessun exact match da un'unita' irrisolta |
| `THERAPY_DISCOVERY` | `AUDIT_ONLY_UNRESOLVED_REGIMEN` — mostrabile solo come unita' |

In nessun caso la direzione e' attribuita ai singoli componenti, e in nessun caso
la candidate diventa una lista di terapie individualmente supportate.

## Un bug trovato dai test

La prima implementazione valutava l'intento **prima** della struttura: in
discovery un regime irrisolto scivolava nel grounding normale. La struttura e'
ora valutata per prima, e due test lo verificano.

## La presenza di tutti i componenti non conferma nulla

Un caso che nomina tutti i farmaci dell'unita' **non** produce
`COMBINATION_CONFIRMED`: la presenza dei nomi non recupera una semantica assente
dalla sorgente. Il warning `REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT` resta.

## Cosa non e' stato fatto

Nessun LLM per ricostruire il regime, nessun uso del titolo del paper, nessuna
chiamata OncoKB, nessuna regola speciale per farmaci specifici.

```
unresolved_regimen_component_promotions = 0
invented_regimen_semantics              = 0
```
