# 02 — ISS-001 · Stop controllato del gate

**P0. CHIUSO.**
Dati: `evaluation/pre_freeze/eligibility_runtime_results.json`.

## Cosa NON è stato toccato

La **policy di eligibility**. L'invariante
`NON_ELIGIBLE → retrieval_called = 0` era già rispettato prima del fix — la
baseline lo conferma: 4 casi su 4, zero chiamate — e resta tale. `gate.py` non è
stato modificato.

Il difetto stava nel **contratto di rappresentazione dello stop**, cioè nella
giunzione fra:

```
eligibility result → orchestrator → stop representation → API response → stage log
```

## La correzione

`backend/research_pipeline/contracts.py`.

```python
ELIGIBILITY_STOP_REASONS = tuple(
    state for state in ELIGIBILITY_STATES if state != ELIGIBLE_FOR_RETRIEVAL
)
```

**Derivato, non riscritto.** Due elenchi paralleli divergerebbero al primo stato
nuovo, e la divergenza tornerebbe a manifestarsi esattamente come prima: un
`ValueError` a runtime. Un test lo verifica (`test_every_non_eligible_state_is_a_stop_reason`).

| | prima | dopo |
|---|---:|---:|
| `STOP_REASONS` | 7 | **15** |
| `CORRECT_STOP_REASONS` | 2 | **10** |
| `FAILURE_STOP_REASONS` | — | **5** (nuovo, esplicito) |

## §6 — La semantica dello stop

`CONTROLLED_STOP` ≠ `PIPELINE_FAILURE`, e la distinzione è ora nel codice:

```python
CORRECT_STOP_REASONS   CASECONTEXT_MISMATCH, RETRIEVAL_NO_MATCH,
                       INVALID_INPUT, OUT_OF_SCOPE, NON_ACTIONABLE_MEDICAL_INPUT,
                       INSUFFICIENT_ONCOLOGY_CONTEXT, MISSING_REQUIRED_FIELDS,
                       CONTRADICTORY_CASE_CONTEXT, ADVERSARIAL_OR_CONTROL_INPUT,
                       AMBIGUOUS_CASE_CONTEXT

FAILURE_STOP_REASONS   PARSER_TRANSPORT_FAILED, CALL_BUDGET_EXCEEDED,
                       DOCUMENT_CACHE_UNAVAILABLE, NO_DOCUMENT_RESOLVED,
                       LIVE_STAGE_FAILED

is_controlled_stop(stopped_at) -> bool
```

I due insiemi **partizionano** `STOP_REASONS`: verificato da un test.

`PARSER_TRANSPORT_FAILED` resta deliberatamente un guasto. Il runtime non sa
distinguere il rifiuto corretto del modello dall'errore di trasporto: ISS-012
(P2) descrive il limite, e trasformarlo in stop controllato lo nasconderebbe.

### Le eccezioni reali continuano a risalire

Il §6 avverte di non nascondere eccezioni dietro gli stop. Un test lo verifica:
`test_software_errors_are_not_disguised_as_controlled_stops` inietta un parser
che solleva `RuntimeError` e si aspetta che l'eccezione **risalga**. Nessun
`except` è stato aggiunto.

## Prima e dopo

| Caso | prima | dopo |
|---|---|---|
| out-of-domain | 💥 `ValueError: … 'OUT_OF_SCOPE'` | `STOPPED / OUT_OF_SCOPE` |
| input vuoto | 💥 `ValueError: … 'INVALID_INPUT'` | `STOPPED / INVALID_INPUT` |
| non actionable | 💥 `ValueError: … 'NON_ACTIONABLE_MEDICAL_INPUT'` | `STOPPED / NON_ACTIONABLE_MEDICAL_INPUT` |
| prompt injection | 💥 `ValueError: … 'OUT_OF_SCOPE'` | `STOPPED / OUT_OF_SCOPE` |

```
controlled_stops_failed        4  ->  0
noneligible_retrieval_calls    0  ->  0     (mai violato)
```

## §7-8 — RQ4 attraverso il runtime canonico

`evaluation/run_rq4_canonical_runtime.py` esegue i **35 casi congelati**
attraverso `orchestrator.run_case`, con il parser rigiocato dagli output
registrati (nessuna chiamata al modello) e le chiamate a valle **contate**, non
dedotte.

```
casi                                35
non eleggibili                      27
controlled_stops_ok                 18
noneligible_retrieval_calls          0
forbidden_downstream_calls           0
expected_controlled_stops_failed     0
runtime_exceptions                   0
path_disagreements                   0
parser_transport_failures            9   (ISS-012, contati a parte)
```

**`path_disagreements = 0`**: sui 35 casi, `orchestrator.run_case` e
`casecontext.pipeline.run` producono lo **stesso** `eligibility_status`. Le
metriche storiche non erano sbagliate nel merito — erano misurate su un percorso
che non poteva vedere la giunzione difettosa. Ora i due percorsi sono
confrontabili ed equivalenti, e la differenza è documentata invece che nascosta.

I 18 `controlled_stops_ok` corrispondono ai 18 casi che
`docs/runtime_v3_integration/15_final_report.md` descrive come «si fermerebbero
anche se il modello producesse una tool call perfettamente valida».

Nulla di storico è stato riscritto: l'output va in
`evaluation/rq4_canonical_runtime/`, e `benchmark_sha256 = dd639ed0…` è
verificato prima dell'esecuzione.

## Test

`backend/research_pipeline/tests/test_eligibility_controlled_stop.py` — **15
test, 13 subtest**, tutti attraverso `orchestrator.run_case`.

È la giunzione che né `test_casecontext_v2_and_gate` né
`run_runtime_v3_integration` percorrevano: entrambi chiamano
`casecontext.pipeline.run` direttamente. Per questo 3 047 test verdi non
intercettavano il difetto.
