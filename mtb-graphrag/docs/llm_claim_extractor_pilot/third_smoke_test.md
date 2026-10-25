# Terzo smoke test

Modello: `minimax-m3:cloud`; endpoint: client Python Ollama; `think=false`; massimo quattro SourceUnit per bundle; tre chiamate reali.

| Bundle | Transport | Validatore | Status finale |
|---|---|---|---|
| DIRECT | `TOOL_CALL_VALID` | `REJECTED_UNGROUNDED` | non calcolato |
| PARTIAL | `TOOL_CALL_VALID` | `REJECTED_UNGROUNDED` | non calcolato |
| CONTRADICTED | `TOOL_CALL_VALID` | `REJECTED_DIRECTION` | non calcolato |

Risultati aggregati: 3/3 tool flat valide, 3/3 semanticamente raggiunte, 0 status finali. Il DIRECT e il PARTIAL non hanno prodotto campi grounded accettabili; nel caso CONTRADICTED il validatore ha bloccato la direction incompatibile. Le tre proposte hanno riportato `negation_detected=false` e `contradiction_detected=false`; quindi il caso contraddittorio non ? stato promosso, ma la contraddizione non ? stata riconosciuta dal modello.

Output token: 2672, 2851, 2623. Latenza ricavata dal metadato Ollama: 20.445,900 ms, 21.519,004 ms, 15.570,113 ms. Il thinking separato era presente in tutti i casi; `think=false` richiesto, non onorato osservabilmente.
