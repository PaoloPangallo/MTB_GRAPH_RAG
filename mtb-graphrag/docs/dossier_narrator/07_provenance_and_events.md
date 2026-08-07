# 07 — Provenance ed eventi

## Stage osservabili

```
stage_13_dossier               DETERMINISTIC   DOSSIER_BUILT       ← stato canonico
stage_14_narrator              LLM             NARRATION_GENERATED ← vista
stage_15_narrative_verifier    DETERMINISTIC   NARRATION_VERIFIED
                                               NARRATION_REJECTED
                                               STRUCTURED_FALLBACK_USED
```

I tre stage sono distinti nel contratto e nella sequenza. `DOSSIER_BUILT`
precede sempre `NARRATION_GENERATED`: è verificato da un test sull'ordine degli
stage, sulla sequenza dichiarata e sull'ordine degli eventi nel ledger.

`PRESENTATION_STAGE_IDS` dichiara che 14 e 15 producono una vista: un loro
fallimento non invalida il dossier.

## Provenance registrata

Tutto aggiunto **localmente**, mai prodotto dall'LLM:

| Campo | Dove |
|---|---|
| `run_id`, `case_id` | ledger, `PipelineRun` |
| `model`, `prompt_version`, `transport_version` | `StageProducer` dello stage 14 |
| `narrator_input_hash` | preview dello stage 14 e 15 |
| `narrative_hash`, `narrative_id` | `narrator.call_narrator`, localmente |
| `verifier_version`, `lexicon_version` | esito dello stage 15 |
| `verification result`, `reason_codes` | esito dello stage 15 |
| `timestamp` | `verified_at`, `narrative.timestamp` |
| `presentation_mode` | preview dello stage 15 |
| `artifact_origin` | `GENERATED_NOW` in LIVE, `RECORDED_REAL_RUN` in REPLAY |

## Il ledger

Ogni evento passa da `stage_payload`, quindi porta `stage_id` e `stage_type` nel
payload, che è nel preimage dell'hash della catena.

Questa proprietà è stata **violata e corretta** durante lo sviluppo: la prima
versione dell'evento `STRUCTURED_FALLBACK_USED` chiamava direttamente `_emit`
con un payload privo di `stage_id`, e un test di integrità del ledger
preesistente l'ha intercettata. È stato aggiunto `RunRecorder.emit_domain_event`,
che rende impossibile emettere un evento di dominio senza identità di stage.

Il test che l'ha trovata non era stato scritto per questa fase: proteggeva già
il ledger, e ha fatto il proprio lavoro su codice nuovo.

## LIVE e REPLAY

| | LIVE | REPLAY |
|---|---|---|
| Narrator | `live_providers.narrator_fn` — chiamata reale | `replay.narrator_fn` — artifact congelato |
| `artifact_origin` | `GENERATED_NOW` | `RECORDED_REAL_RUN` |
| effetto sulla run | resta `LIVE` | declassa a `HYBRID` se avviata LIVE |

La chiave del replay è `(case_id, narrator_input_hash)`: **una narrativa
registrata per un dossier diverso non viene rigiocata al suo posto**. Se il
dossier cambia, la narrativa congelata smette di applicarsi, ed è corretto che
sia così.

Se non esiste una narrativa congelata per quella projection, `replay.narrator_fn`
restituisce `narrative = None` con reason code
`NO_FROZEN_NARRATIVE_FOR_THIS_DOSSIER`, e il sistema usa il fallback. Non è un
errore: è l'assenza dichiarata.

Il budget di chiamate LLM **non** viene speso dal Narrator: `CallBudget` protegge
le chiamate che partecipano alla costruzione dell'evidenza, e la narrazione
avviene dopo, su un dossier già chiuso.
