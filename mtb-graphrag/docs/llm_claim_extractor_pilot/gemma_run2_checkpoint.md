# CHECKPOINT B — run_index=2

Eseguito perché il CHECKPOINT A non ha prodotto hard stop. 25/25 chiamate
eseguite, 0 retry infrastrutturali, 0 hard stop. Nessun parametro cambiato
sulla base dei risultati di run 1.

| Metrica | Valore |
|---|---:|
| Transport validi | 20/25 (80%) |
| Transport outcomes | `FORCED_TOOL_VALID`=20, `FORCED_TOOL_IGNORED`=4, `TEXT_RESPONSE`=1 |
| `tool_choice` applicato correttamente | 20/25 (80%) |
| `ACCEPTED` | 1 |
| `ACCEPTED_WITH_DROPPED_FIELDS` | 2 |
| `REJECTED_DIRECTION` | 5 |
| `REJECTED_CONTRADICTION` | 3 |
| `ABSTAINED` | 9 |
| `final_support_status`: DIRECT/PARTIAL/AMBIGUOUS | 1/2/9 |
| Quote inesistenti accettate / SourceUnit inventate / graph-only accettati / CONTRADICTED promosso | 0 / 0 / 0 / 0 |
| Latenza (ms) min/media/max | 4603.3 / 10155.9 / 32730.0 |
| Token input/output medi | 2127.4 / 419.3 |

Il bundle DIRECT dello Stadio 1 recupera qui: `FORCED_TOOL_VALID`,
`ACCEPTED`, tutti i 4 campi, `final_support_status=DIRECT` — coerente col
risultato originale, ma non riprodotto in run 1 (transport fallito). Questo
è un segnale diretto di instabilità del *transport*, non del grounding
semantico, sullo stesso identico bundle.

Il tasso di transport valido scende ulteriormente rispetto a run 1
(80% vs 88%), entrambi sotto la soglia del 90% richiesta per l'idoneità.
