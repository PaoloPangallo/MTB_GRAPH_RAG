# Selezione del modello — risultati

- **Generato:** 2026-07-22T11:41:04.798929+00:00
- **Stato:** `qualified`
- **Casi development:** 4 (il test set non e' stato usato)
- **Seed:** [20240517, 13, 991] · **num_ctx:** 16384 · **temperature:** 0
- **Modelli valutati:** ['gemma4:31b-cloud', 'gpt-oss:120b-cloud', 'gpt-oss:20b-cloud', 'nemotron-3-ultra-cloud']

La selezione usa soltanto i quattro casi development. Il modello scelto non e'
quindi valutato in modo indipendente: questi casi dicono quale modello e'
preferibile fra i candidati, non quanto sara' bravo.

## Modelli valutati

| Modello | Endpoint | Modalita' output | Digest | Quantizzazione |
| --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | cloud | prompt_validated | `221b330d11a8` | BF16 |
| `gpt-oss:120b-cloud` | cloud | prompt_validated | `d98fe6ba01e6` | MXFP4 |
| `gpt-oss:20b-cloud` | cloud | prompt_validated | `05afbac4bad6` | MXFP4 |
| `nemotron-3-ultra-cloud` | cloud | prompt_validated | `4eecabff7a75` | - |

## Metriche per ruolo

### planner

| Modello | conditional_step_accuracy | fallback_rate | median_latency_ms | planner_failure_rate | required_tool_recall | run_to_run_agreement | stop_condition_accuracy | task_completion | unnecessary_tool_rate | valid_action_rate | valid_output_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | 1.000 | 0.000 | 2677.055 | 0.000 | 0.939 | 0.833 | 1.000 | 0.833 | 0.000 | 1.000 | 1.000 |
| `gpt-oss:120b-cloud` | 1.000 | 0.000 | 7186.880 | 0.000 | 0.970 | 0.833 | 1.000 | 0.917 | 0.059 | 1.000 | 1.000 |
| `gpt-oss:20b-cloud` | 1.000 | 0.000 | 4912.975 | 0.000 | 0.939 | 0.833 | 1.000 | 0.833 | 0.128 | 1.000 | 1.000 |
| `nemotron-3-ultra-cloud` | 1.000 | 0.000 | 48527.050 | 0.000 | 0.879 | 0.917 | 1.000 | 0.917 | 0.094 | 1.000 | 1.000 |

### verifier

| Modello | applicability_status_accuracy | compatible_overstatement_rate | documentary_status_accuracy | median_latency_ms | missing_context_detection | qualifier_extraction_accuracy | run_to_run_agreement | valid_output_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | 1.000 | 0.000 | 1.000 | 17093.225 | 0.625 | 0.875 | 1.000 | 1.000 |
| `gpt-oss:120b-cloud` | 1.000 | 0.000 | 1.000 | 6584.345 | 0.917 | 0.896 | 1.000 | 1.000 |
| `gpt-oss:20b-cloud` | 1.000 | 0.000 | 1.000 | 6472.170 | 0.875 | 0.938 | 1.000 | 1.000 |
| `nemotron-3-ultra-cloud` | 1.000 | 0.000 | 0.958 | 26563.540 | 0.667 | 0.979 | 1.000 | 1.000 |

### free_report

| Modello | abstention_accuracy | citation_accuracy | claim_precision | claim_recall | context_omission_rate | median_latency_ms | qualifier_preservation | run_to_run_agreement | unsupported_claim_rate | valid_output_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:31b-cloud` | 1.000 | 1.000 | 1.000 | 1.000 | 0.506 | 81771.090 | 0.494 | 0.917 | 0.000 | 1.000 |
| `gpt-oss:120b-cloud` | 1.000 | 0.960 | 0.960 | 0.960 | 0.293 | 26100.270 | 0.707 | 0.500 | 0.040 | 1.000 |
| `gpt-oss:20b-cloud` | 1.000 | 1.000 | 1.000 | 1.000 | 0.429 | 19193.020 | 0.571 | 0.542 | 0.000 | 0.917 |
| `nemotron-3-ultra-cloud` | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 146654.550 | 1.000 | 0.625 | 0.000 | 0.917 |

## Ammissibilita'

- `gpt-oss:20b-cloud` / planner: ammesso
- `gemma4:31b-cloud` / planner: ammesso
- `gpt-oss:120b-cloud` / planner: ammesso
- `nemotron-3-ultra-cloud` / planner: ammesso
- `gpt-oss:20b-cloud` / verifier: ammesso
- `gemma4:31b-cloud` / verifier: ammesso
- `gpt-oss:120b-cloud` / verifier: ammesso
- `nemotron-3-ultra-cloud` / verifier: ammesso
- `gpt-oss:20b-cloud` / free_report: **escluso** — ['valid_output_rate=0.917 sotto la soglia 0.95']
- `gemma4:31b-cloud` / free_report: ammesso
- `gpt-oss:120b-cloud` / free_report: ammesso
- `nemotron-3-ultra-cloud` / free_report: **escluso** — ['valid_output_rate=0.917 sotto la soglia 0.95']

## Avvertenze sulle soglie

Con dodici run per ruolo (4 casi x 3 seed), un solo output non valido porta `valid_output_rate` a 0.917 e fa scattare l'esclusione a 0.95. La soglia e' quindi molto grossolana a questo n: distingue zero fallimenti da uno, non un modello affidabile da uno inaffidabile.

- `gpt-oss:20b-cloud` escluso da **free_report**: ['valid_output_rate=0.917 sotto la soglia 0.95'] pur avendo `citation_accuracy` = 1.000, `claim_precision` = 1.000.
- `nemotron-3-ultra-cloud` escluso da **free_report**: ['valid_output_rate=0.917 sotto la soglia 0.95'] pur avendo `citation_accuracy` = 1.000, `claim_precision` = 1.000, `qualifier_preservation` = 1.000.

- Su **free_report**, `gpt-oss:120b-cloud` e' l'unico modello con `citation_accuracy` = 0.960 mentre gli altri sono a 1.000. Se e' il modello selezionato, e' un difetto da dichiarare.
- Su **free_report**, `gpt-oss:120b-cloud` e' l'unico modello con `unsupported_claim_rate` = 0.040 mentre gli altri sono a 0.000. Se e' il modello selezionato, e' un difetto da dichiarare.

## Classifiche

**planner**
1. `gpt-oss:120b-cloud` — 0.9434
2. `nemotron-3-ultra-cloud` — 0.9284
3. `gemma4:31b-cloud` — 0.9212
4. `gpt-oss:20b-cloud` — 0.9020

**verifier**
1. `gpt-oss:20b-cloud` — 0.9750
2. `gpt-oss:120b-cloud` — 0.9708
3. `nemotron-3-ultra-cloud` — 0.9500
4. `gemma4:31b-cloud` — 0.9375

**free_report**
1. `gpt-oss:120b-cloud` — 0.8361
2. `gemma4:31b-cloud` — 0.8188

## Modello unico

gpt-oss:120b-cloud — perdita massima 0.004 rispetto al migliore di ogni ruolo

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
