# Manifest riconciliato dei 25 run_index=0

Regola di selezione (`run_gemma_stage1_reconcile.reconcile`): se il
trasporto nativo era già valido (`TOOL_CALL_VALID`), si mantiene il
risultato originale dello Stadio 1, invariato — nessuna richiamata. Se il
trasporto nativo era fallito (`NO_TOOL_CALL` /
`TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL`), si usa esclusivamente il risultato
forced-tool, senza confrontare o scegliere fra i due esiti semantici.

| Provenienza | Bundle |
|---|---:|
| `ORIGINAL_TRANSPORT_VALID_KEEP` | 17 |
| `ORIGINAL_TRANSPORT_FAILED_USE_FORCED_TOOL_RESULT` | 8 |
| Totale | 25 |

Gli output originali dello Stadio 1
(`gemma_stage1_runs.jsonl`/`gemma_stage1_metrics.json`) non sono stati
sovrascritti; la riconciliazione vive in file separati
(`gemma_stage1_reconciled.jsonl`).

## Metriche sul set riconciliato (25 bundle)

| Metrica | Valore |
|---|---:|
| Transport validi | 24/25 (96%) |
| Transport outcomes | `TOOL_CALL_VALID`=17, `FORCED_TOOL_VALID`=7, `FORCED_TOOL_IGNORED`=1 |
| `ACCEPTED` | 1 |
| `ACCEPTED_WITH_DROPPED_FIELDS` | 1 |
| `REJECTED_DIRECTION` | 7 |
| `REJECTED_CONTRADICTION` | 5 |
| `ABSTAINED` | 10 |
| `REJECTED_UNGROUNDED`/`REJECTED_SCHEMA`/`REJECTED_LINEAGE`/`VALIDATION_ERROR` | 0 |
| Campi proposti | 47 |
| Campi accettati | 25 |
| Campi scartati | 15 |
| Quote inesistenti proposte / accettate | 2 / 0 |
| SourceUnit inventate accettate | 0 |
| Campi graph-only proposti / accettati | 13 / 0 |
| Direction errate | 7 |
| Negazioni perse | 5 |
| Contraddizioni perse (CONTRADICTED promosso) | 0 |
| `final_support_status`: DIRECT/PARTIAL/AMBIGUOUS/CONTRADICTED/NO_SUPPORT_FOUND | 1/1/10/0/0 |
| Non calcolato | 13 |

Il tasso di transport valido passa dal 68% (17/25, solo Stadio 1) al 96%
(24/25, riconciliato) grazie al recupero forced-tool. Zero regressioni di
sicurezza introdotte dal nuovo trasporto.
