# CHECKPOINT A — run_index=1

25/25 chiamate eseguite, 0 retry infrastrutturali, 0 hard stop.

| Metrica | Valore |
|---|---:|
| Transport validi | 22/25 (88%) |
| Transport outcomes | `FORCED_TOOL_VALID`=22, `TEXT_RESPONSE`=2, `FORCED_TOOL_IGNORED`=1 |
| `tool_choice` applicato correttamente | 22/25 (88%) |
| `ACCEPTED` | 1 |
| `ACCEPTED_WITH_DROPPED_FIELDS` | 1 |
| `REJECTED_DIRECTION` | 8 |
| `REJECTED_CONTRADICTION` | 2 |
| `ABSTAINED` | 10 |
| `final_support_status`: DIRECT/PARTIAL/AMBIGUOUS | 0/2/10 |
| Quote inesistenti accettate / SourceUnit inventate / graph-only accettati / CONTRADICTED promosso | 0 / 0 / 0 / 0 |
| Latenza (ms) min/media/max | 4918.9 / 10132.0 / 32891.2 |
| Token input/output medi | 2127.3 / 416.8 |

Nota rilevante: il bundle DIRECT dello smoke test/Stadio 1
(`EB-b4c48ba003913f278ff182a6`) ha transport `TEXT_RESPONSE` in questa run —
il modello non ha invocato il tool nonostante `tool_choice` forzato, quindi
nessuno status finale è stato calcolato per questo bundle in run 1
(recuperato in run 2, vedi `gemma_run2_checkpoint.md`). Nessun hard stop
scattato: transport sotto soglia non è un hard stop di sicurezza.
