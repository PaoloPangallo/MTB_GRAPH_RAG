# 12 — Supervisor UI

La route legacy **non e' stata toccata**.

## Nuovo stage visibile

`stage_3b_pre_retrieval_eligibility_gate`, con vista dedicata
(`EligibilityStage.tsx`).

Mostra: stato di eleggibilita' con badge, motivo, ancoraggi di scope, campi
verificati, campi mancanti, menzioni rifiutate con il loro motivo, sintomi
riconosciuti, span di istruzioni di controllo, contraddizioni con severita',
stage downstream saltati e `policy_version`.

## Badge

`ELIGIBLE` `OUT OF SCOPE` `NON ACTIONABLE` `CONTRADICTORY` `CONTROL INPUT`
`INVALID INPUT` `MISSING FIELDS` `INSUFFICIENT CONTEXT` `AMBIGUOUS`

Per le candidate v3, i valori di `CandidateRuntimeAdmission` sono disponibili
nell'associazione (`admission`): `graph_direction`, `source_support_polarity`,
`source_alignment_status`, `alteration_match_status`,
`intervention_match_status`, `admission_status`, `allowed_branches`,
`warning_codes`.

## Nessuna decisione calcolata nel browser

Lo stato, i motivi e gli stage saltati arrivano gia' risolti dal backend. La UI
mappa solo stato a **tono del badge** e a **etichetta leggibile**; uno stato
sconosciuto e' mostrato cosi' com'e' invece di essere reinterpretato — un test
lo verifica.

```
frontend_computes_eligibility = false
```

## `[object Object]`

Un test verifica che nessun ramo lo produca, anche con valori annidati.

## Test

13 test in `EligibilityStage.test.tsx`. Suite frontend completa: 195 test.

**Limite:** la vista delle candidate v3 nel ramo del dossier non e' stata
esercitata end-to-end, perche' il retrieval v3 non e' il default.
