# Recupero degli 8 bundle falliti

| Bundle | Esito originale | Esito forced-tool | Validator outcome | Status finale |
|---|---|---|---|---|
| EB-003e4bcab4a57d2a1c80cb5c | TEXT_RESPONSE | FORCED_TOOL_VALID | ABSTAINED | AMBIGUOUS |
| EB-278efe96eecccc226c82aa2d | TEXT_RESPONSE | FORCED_TOOL_VALID | REJECTED_CONTRADICTION | non calcolato |
| EB-35a15fff70830617392cfa75 | TEXT_RESPONSE | FORCED_TOOL_IGNORED | FORCED_TOOL_IGNORED | non calcolato |
| EB-9403cc6f191fb7d83bc29836 | NO_TOOL_CALL | FORCED_TOOL_VALID | REJECTED_CONTRADICTION | non calcolato |
| EB-9f6ea93de50453d03f8f572c | TEXT_RESPONSE | FORCED_TOOL_VALID | REJECTED_DIRECTION | non calcolato |
| EB-b1f4afc47f51582120ec6384 | NO_TOOL_CALL | FORCED_TOOL_VALID | REJECTED_DIRECTION | non calcolato |
| EB-b6dc7db903abe794a5b18eae | TEXT_RESPONSE | FORCED_TOOL_VALID | ABSTAINED | AMBIGUOUS |
| EB-d14e11e161877b56ac0e66c8 | TEXT_RESPONSE | FORCED_TOOL_VALID | REJECTED_CONTRADICTION | non calcolato |

7/8 recuperati a livello di trasporto (da nessuna tool-call a una tool-call
valida e strutturalmente conforme). Nessuno dei 7 recuperati raggiunge
`ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS`: 2 `ABSTAINED` (nessun campo
proposto), 3 `REJECTED_CONTRADICTION` (negazione nel testo non preservata
dal modello), 2 `REJECTED_DIRECTION` (conflitto di direzione). Questo è
coerente con il comportamento osservato sugli altri bundle nello Stadio 1:
recuperare il trasporto rende le proposte valutabili dal validatore, ma non
cambia il tasso di grounding semantico del modello su casi difficili.

Zero quote inesistenti accettate, zero SourceUnit inventate, zero campi
graph-only accettati, zero CONTRADICTED promosso a positivo, su tutti gli 8
tentativi — il validatore (invariato) ha bloccato correttamente ogni
proposta non grounded, esattamente come nello Stadio 1.
