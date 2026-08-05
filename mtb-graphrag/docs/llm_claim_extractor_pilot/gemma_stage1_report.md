# Report Stadio 1 (25 bundle, run_index=0)

3 run riusate dallo smoke test (nessuna richiamata), 22 nuove chiamate reali
a `gemma4:cloud`. Nessuno stop anticipato, nessun hard stop.

## Metriche aggregate (25 bundle)

| Metrica | Valore |
|---|---:|
| Transport validi | 17/25 (68%) |
| Proposte canoniche | 17 |
| `ACCEPTED` | 1 |
| `ACCEPTED_WITH_DROPPED_FIELDS` | 1 |
| `REJECTED_UNGROUNDED` | 0 |
| `REJECTED_DIRECTION` | 5 |
| `REJECTED_CONTRADICTION` | 2 |
| `REJECTED_SCHEMA` | 0 |
| `REJECTED_LINEAGE` | 0 |
| `ABSTAINED` | 8 |
| `VALIDATION_ERROR` | 0 |
| Campi proposti | 29 |
| Campi accettati | 16 |
| Campi scartati | 8 |
| Quote inesistenti proposte | 0 |
| Quote inesistenti accettate | 0 |
| SourceUnit inventate accettate | 0 |
| Campi graph-only proposti | 8 |
| Campi graph-only accettati | 0 |
| Direction errate | 5 |
| Negazioni perse | 2 |
| Contraddizioni perse (CONTRADICTED promosso a positivo) | 0 |
| `final_support_status`: DIRECT | 1 |
| `final_support_status`: PARTIAL | 1 |
| `final_support_status`: AMBIGUOUS | 8 |
| `final_support_status`: CONTRADICTED | 0 |
| `final_support_status`: NO_SUPPORT_FOUND | 0 |
| `final_support_status`: non calcolato | 15 |

Il collo di bottiglia è il transport: su 22 nuove chiamate, 8 non hanno
prodotto una tool-call valida (2 `NO_TOOL_CALL`, 6
`TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL`) — un tasso di fallimento del transport
molto più alto che nei 3 bundle dello smoke test (dove era 0/3). Zero
proposte accettate contengono una quote inesistente, una SourceUnit
inventata o un campo graph-only: il validatore ha filtrato correttamente su
tutti i 17 transport validi.

## Applicazione dei criteri A/B/C

**A. DIRECT** (1 bundle, quello dello smoke test, riusato): transport
valido, tutti i 4 campi accettati, `final_support_status=DIRECT` —
**successo**.

**B. PARTIAL** (11 bundle totali): 1 raggiunge `ACCEPTED_WITH_DROPPED_FIELDS`
-> `PARTIAL` (campi supportati accettati, resto scartato correttamente —
successo); 3 ricevono `REJECTED_DIRECTION` (nessuna promozione impropria a
DIRECT — esito ammesso, successo secondo il criterio B anche se non
raggiunge uno status finale); 2 vengono `ABSTAINED` -> `AMBIGUOUS` (esito
ammesso — successo); 5 falliscono a livello di transport (nessuna proposta
da valutare con questo criterio).

**C. CONTRADICTED** (2 bundle): quello dello smoke test (riusato) è
`ABSTAINED` -> `AMBIGUOUS`, nessun supporto positivo — successo. Il secondo
bundle CONTRADICTED (`EB-bd6ce2f5db3fb40af814743e`) riceve
`REJECTED_DIRECTION` con 2 campi (`biomarker`, `intervention`) accettati ma
la proposta complessiva rigettata per conflitto di direzione — nessun
supporto positivo prodotto, il criterio C ("rigetto per direzione" è un
esito ammesso) è soddisfatto.

**AMBIGUOUS come baseline** (11 bundle, non coperti esplicitamente da A/B/C
ma osservati): 5 `ABSTAINED` -> `AMBIGUOUS`, 2 `REJECTED_CONTRADICTION`
(negazione/contraddizione nel testo non preservata correttamente dal
modello — vedi limitazioni), 1 `REJECTED_DIRECTION`, 3 falliscono a livello
di transport.

Vedi `gemma_stage1_transitions.md` per il confronto puntuale con la
baseline B.
