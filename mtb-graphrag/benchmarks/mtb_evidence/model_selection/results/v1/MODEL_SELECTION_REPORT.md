# Selezione del modello — risultati

- **Generato:** 2026-07-22T09:48:09.592076+00:00
- **Stato:** `qualified`
- **Casi development:** 4 (il test set non e' stato usato)
- **Seed:** [20240517, 13, 991] · **num_ctx:** 16384 · **temperature:** 0
- **Modelli valutati:** ['gemma4:31b-cloud', 'gpt-oss:20b-cloud', 'qwen3.5:397b-cloud']

La selezione usa soltanto i quattro casi development. Il modello scelto non e'
quindi valutato in modo indipendente: questi casi dicono quale modello e'
preferibile fra i candidati, non quanto sara' bravo.

## Modelli valutati

| Modello | Endpoint | Modalita' output | Digest | Quantizzazione |
| --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | cloud | prompt_validated | `221b330d11a8` | BF16 |
| `gpt-oss:20b-cloud` | cloud | prompt_validated | `05afbac4bad6` | MXFP4 |
| `qwen3.5:397b-cloud` | cloud | prompt_validated | `b909ca2f1b7f` | BF16 |

## Metriche per ruolo

### planner

| Modello | conditional_step_accuracy | fallback_rate | median_latency_ms | planner_failure_rate | required_tool_recall | run_to_run_agreement | stop_condition_accuracy | task_completion | unnecessary_tool_rate | valid_action_rate | valid_output_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | 1.000 | 0.000 | 2677.055 | 0.000 | 0.939 | 0.833 | 1.000 | 0.833 | 0.000 | 1.000 | 1.000 |
| `gpt-oss:20b-cloud` | 1.000 | 0.000 | 4912.975 | 0.000 | 0.939 | 0.833 | 1.000 | 0.833 | 0.128 | 1.000 | 1.000 |

## Ammissibilita'

- `gpt-oss:20b-cloud` / planner: ammesso
- `gemma4:31b-cloud` / planner: ammesso

## Classifiche

**planner**
1. `gemma4:31b-cloud` — 0.9212
2. `gpt-oss:20b-cloud` — 0.9020

## Modello unico

gemma4:31b-cloud — perdita massima 0.000 rispetto al migliore di ogni ruolo

## Fallimenti

- nessuno

## Limiti

- Quattro casi: i punteggi descrivono questo campione, non stimano una popolazione.
- Il modello selezionato non e' valutato in modo indipendente.
- Modelli locali (`json_schema`) e cloud (`prompt_validated`) non partono alla
  pari sul `valid_output_rate`: la differenza e' una proprieta' del deployment.
- Tre seed danno un accordo run-to-run che vale solo 1/3, 2/3 o 1.
- La domanda di C1 nomina la terapia attesa: il recall terapeutico di quel caso
  e' meno informativo degli altri.
