# Analisi secondaria: run 0 vs run 1 vs run 2

**Attenzione**: run 0 usa i risultati riconciliati dello Stadio 1 (17
bundle via trasporto Ollama nativo, 7 via forced-tool OpenAI-compatible, 1
fallimento residuo) — non è un'osservazione omogenea con run 1/run 2,
entrambe interamente forced-tool. Questa analisi è secondaria e non va
usata come riferimento primario di stabilità (vedi
`gemma_run1_run2_stability.md` per quello).

| Metrica | Valore |
|---|---:|
| Three-run field agreement (100 slot) | 79% |
| Three-run status agreement | 84% |
| Three-run abstention agreement | 96% |
| Three-run validator-outcome recurrence | 60% |
| Bundle con quote ricorrenti tra le run | 10/25 |
| Bundle con SourceUnit ricorrenti tra le run | 11/25 |
| Valori di direction ricorrenti osservati | resistance: 4, sensitivity: 2 |

L'accordo a tre run è generalmente più alto di quello a due (run1/run2)
sulle metriche aggregate di status/astensione, in parte perché run 0
include il trasporto nativo Ollama (più affidabile su alcuni bundle
specifici, es. il bundle DIRECT) che compensa i fallimenti isolati di
run 1 o run 2 sullo stesso bundle.
