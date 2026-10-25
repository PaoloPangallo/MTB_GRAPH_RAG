# Decisione

## Verifica dei criteri (sezione 13)

| Criterio | Soglia | Risultato | Esito |
|---|---|---:|---|
| Transport validi | ≥6/7 | 7/7 | Superato |
| Almeno un enrichment QUOTE accettato | ≥1 | 2 | Superato |
| Quote inesistenti accettate | =0 | 0 | Superato |
| SourceUnit inventate accettate | =0 | 0 | Superato |
| Summary ungrounded accettati | =0 | 0 | Superato |
| Raccomandazioni cliniche accettate | =0 | 0 | Superato |
| CONTRADICTED trasformato in supporto positivo | mai | mai (Caso 4: 2/2 astensioni) | Superato |
| Output Gemma modifica claim/gate/status | mai | mai (schema non ha questi campi) | Superato |
| "Particolarmente positivo": ≥3/7 quote valide | ≥3 | 2 | Non raggiunto |

## Decisione

**PAPER_CONTEXT_ENRICHER_V2_PROMISING**

Transport sufficiente (7/7, ben oltre la soglia 6/7) e almeno un
enrichment QUOTE semanticamente accettato (2/7). Zero violazioni di
sicurezza, zero hard stop. Non raggiunge la soglia bonus "particolarmente
positivo" (3/7), ma supera nettamente ogni criterio di base.

## Raccomandazione architetturale

Il contratto v2.0 (QUOTE/ABSTAIN, tutto-stringa, nessuna classificazione)
risolve entrambi i colli di bottiglia di trasporto osservati nelle
versioni precedenti e produce il primo esempio positivo end-to-end
dell'intero filone di ricerca. Prima di un'ulteriore integrazione:
ripetere su un campione più ampio di paper per stimare un tasso di
accettazione stabile (il campione attuale, n=7, è troppo piccolo); non
sono necessarie ulteriori modifiche allo schema per risolvere problemi di
trasporto, che appare ora il collo di bottiglia meno critico rispetto
alle fasi precedenti.
