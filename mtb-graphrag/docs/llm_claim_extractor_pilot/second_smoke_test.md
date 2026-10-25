# Secondo smoke test

Modello: `minimax-m3:cloud`; endpoint: client Python Ollama; `think=false`; `temperature=0`; `max_output_tokens=4096`; tre chiamate reali e nessuna chiamata successiva. Sono stati inviati solo i quattro SourceUnit selezionati per ciascun bundle: 8.878 caratteri e 1.266 parole complessivi.

| Bundle | Caso | Tool call presente | done_reason | content | thinking separato | Esito trasporto | Esito validatore |
|---|---|---:|---|---:|---:|---|---|
| `EB-b4c48ba003913f278ff182a6` | DIRECT | 1 | `tool_calls` | 0 | s? | `INVALID_TOOL_ARGUMENTS` | `REJECTED_SCHEMA` |
| `EB-2ae853e8abf1195cc4c84846` | PARTIAL | 1 | `tool_calls` | 0 | s? | `INVALID_TOOL_ARGUMENTS` | `REJECTED_SCHEMA` |
| `EB-6a291f12975b20b79e1c3dd7` | CONTRADICTED | 1 | `tool_calls` | 0 | s? | `INVALID_TOOL_ARGUMENTS` | `REJECTED_SCHEMA` |

Il modello ha emesso una funzione, ma gli argomenti non rispettavano lo schema compatto: i campi usavano chiavi alternative (`name`/`direction`) o `value` stringa con `null` testuale, e negazione/contraddizione avevano una forma diversa. Il post-processing corretto ha classificato tutte le tre chiamate come argomenti invalidi. Nessun campo ? stato accettato e nessuno status finale ? stato calcolato.

Dati diagnostici: output token 1.499, 1.728 e 1.400; latenza 11.572,096 ms, 14.435,301 ms e 10.186,509 ms. Thinking acquisito separatamente: 3.503, 5.016 e 3.686 caratteri.
