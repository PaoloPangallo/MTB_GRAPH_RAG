# Decisione Stadio 2

Verifica dei criteri della sezione 8 (vedi `gemma_stage1_validation.md` per
la tabella completa): 8 degli 9 criteri sono soddisfatti. Il solo criterio
non soddisfatto è il tasso minimo di transport validi (richiesto >= 90%,
ottenuto 68%, 17/25).

**STAGE2_NOT_AUTHORIZED**

Le altre due run per bundle (Stadio 2, fino a 50 chiamate aggiuntive) non
sono autorizzate in base ai risultati di questo Stadio 1.

Nota: questo non è un fallimento di grounding semantico — zero quote
inesistenti accettate, zero SourceUnit inventate, zero campi graph-only
promossi, zero CONTRADICTED promosso a positivo, il DIRECT dello smoke
resta preservato, nessun hard stop. È un fallimento di affidabilità del
transport (il modello risponde con testo libero invece di invocare il tool
in 8/22 nuove chiamate) su un campione più ampio ed eterogeneo dei 3 bundle
usati per lo smoke test.

Non si modifica il prompt, il transport o il validatore in risposta a
questo risultato. Non si eseguono le run aggiuntive (Stadio 2). Non si
tenta automaticamente un altro modello in questa sessione.
