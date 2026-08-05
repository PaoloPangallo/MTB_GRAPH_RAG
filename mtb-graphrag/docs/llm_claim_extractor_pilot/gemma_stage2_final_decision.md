# Decisione finale sullo Stadio 2

## A. Trasporto

Transport validi (riconciliato): 24/25 (96%) >= 23/25 e >= 90% —
**superato**.

## B. Sicurezza

| Criterio | Esito |
|---|---|
| Quote inesistenti accettate = 0 | Sì |
| SourceUnit inventate accettate = 0 | Sì |
| Campi graph-only accettati = 0 | Sì |
| CONTRADICTED promosso a positivo = 0 | Sì |
| DIRECT originario preservato | Sì |
| Validatore invariato | Sì |
| Nessun hard stop | Sì (0 su 25 + 8) |

**Superato.**

## C. Utilità

Almeno un segnale richiesto è presente (`NEW_VALIDATED_FIELD`=1,
provenance migliorata=2 bundle, contraddizioni bloccate=26 campi) — vedi
`gemma_incremental_value.md` per la lettura onesta della grandezza di
questi segnali (marginale ma non nulla). **Superato.**

## Decisione

**STAGE2_AUTHORIZED**

Trasporto, sicurezza e utilità superano tutti i criteri della sezione 11
del protocollo. Questo autorizza — non esegue — le altre due run per
bundle (fino a 50 chiamate aggiuntive). Nessuna chiamata dello Stadio 2 è
stata effettuata in questa fase.

`gemma_stage2_executed = false`
`full_75_call_pilot_executed = false`
