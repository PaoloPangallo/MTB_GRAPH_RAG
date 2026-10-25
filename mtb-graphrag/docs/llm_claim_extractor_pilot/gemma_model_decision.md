# Decisione Gemma

Verifica dei criteri di validità (protocollo §9, elenco base):

- transport validi: 3/3 (soglia: >=2/3) — superato
- proposte che raggiungono il validator: 3/3 (soglia: >=2/3) — superato
- proposte `ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS`: 1/3 (soglia: >=2/3) —
  **non superato**
- quote inesistenti accettate: 0 — superato
- SourceUnit inventate accettate: 0 — superato
- campi graph-only accettati: 0 — superato
- CONTRADICTED non promosso: confermato — superato
- validatore invariato: confermato — superato

Verifica dei criteri preferiti per l'autorizzazione delle 75 chiamate
(protocollo §9, elenco stretto): 3/3 transport validi (superato), 3/3
semanticamente valutabili (superato), DIRECT preservato (superato,
`ACCEPTED` con tutti i 4 campi grounded), CONTRADICTED preservato
(superato, `ABSTAINED` -> `AMBIGUOUS`, nessuna evidenza positiva
fabbricata), nessun campo unsupported accettato (superato).

Un solo criterio della lista base non è soddisfatto: il tasso di
`ACCEPTED`/`ACCEPTED_WITH_DROPPED_FIELDS` è 1/3 anziché >=2/3, perché sul
bundle PARTIAL il campo `direction` genera un `DROPPED_DIRECTION_CONFLICT`
che fa fallire l'intera proposta (`REJECTED_DIRECTION`) anche se `disease` e
`intervention` erano correttamente grounded. Applicando il criterio
letteralmente:

**MODEL_SEMANTIC_GROUNDING_INSUFFICIENT**

per la soglia di validità richiesta dal protocollo, su questo campione di
3 chiamate.

Va segnalato che Gemma supera MiniMax su ogni altra metrica misurata (vedi
`minimax_gemma_comparison.md`): transport interamente valido, un caso
DIRECT pienamente accettato e grounded (MiniMax: nessuno), rispetto
effettivo di `think=False`, zero accettazioni non grondate in entrambi i
modelli. Il fallimento del criterio è puntuale (un conflitto di direzione
su un singolo bundle PARTIAL) e non un fallimento sistemico di grounding
semantico come osservato per MiniMax.

Non si modifica il prompt, il transport o il validatore.
Non si eseguono le 75 chiamate.
Non si tenta automaticamente un altro modello in questa sessione.
