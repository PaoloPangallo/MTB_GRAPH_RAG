# Validazione Stadio 1

Verifica dei criteri hard-stop (sezione 9 del protocollo), calcolata per
ognuna delle 25 righe con `stage1_pilot.detect_hard_stops`:

| Condizione | Rilevata |
|---|---|
| Quote inesistente accettata | No (0/25) |
| SourceUnit inventata accettata | No (0/25) |
| Campo graph-only promosso | No (0/25) |
| CONTRADICTED promosso a positivo | No (0/25) |
| Validatore aggirato/modificato | No (`validator_version` invariata su tutte le righe con esito) |
| Prompt modificato durante il pilot | No (`prompt_version` invariata) |
| Transport modificato durante il pilot | No (`transport_version` invariata) |
| File EvidenceBundle modificato | No (hash prima/dopo identico) |

Nessun hard stop scattato. Le 22 nuove chiamate sono state eseguite tutte,
nessuno stop anticipato.

## Comportamento del validatore sui casi limite

Due bundle (`EB-4c70544954c0fd9241e2adca`,
`EB-56d2ac75d26d1e64b9d40da2`, entrambi baseline `AMBIGUOUS`) hanno prodotto
proposte con `disease` e `intervention` grounded correttamente, ma il testo
sorgente conteneva un segnale di negazione che il modello non ha dichiarato
in `negation.detected`. Il validatore (invariato) ha rigettato l'intera
proposta con `REJECTED_CONTRADICTION` /
`NEGATION_OR_CONTRADICTION_NOT_PRESERVED`, come previsto dal criterio B
("nessuna promozione impropria"): nessun campo è stato accettato, nessun
supporto positivo è stato prodotto nonostante due campi fossero altrimenti
grounded. Questo è il comportamento di sicurezza atteso, non un hard stop:
il validatore ha bloccato correttamente un caso in cui il modello non ha
preservato la negazione.

## Esito rispetto ai criteri dello Stadio 2 (sezione 8)

| Criterio | Esito |
|---|---|
| Transport validi >= 90% | **No — 68% (17/25)** |
| Campi unsupported accettati = 0 | Sì |
| Quote inesistenti accettate = 0 | Sì |
| SourceUnit inventate accettate = 0 | Sì |
| Campi graph-only accettati = 0 | Sì |
| CONTRADICTED promosso a positivo = 0 | Sì |
| DIRECT dello smoke preservato | Sì |
| Validatore invariato | Sì |
| Nessun hard stop | Sì |

Un solo criterio non è soddisfatto — il tasso di transport validi — ma è
l'unico che il protocollo rende bloccante per lo Stadio 2 senza eccezioni.
Vedi `gemma_stage2_decision.md`.
