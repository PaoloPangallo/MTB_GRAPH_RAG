# Quarto smoke test

Modello: `minimax-m3:cloud`; prompt: `llm-claim-extractor-prompt/1.3`; transport: `llm-claim-proposal-transport/1.2`; chiamate reali: `3`.

| Misura | Risultato |
|---|---:|
| transport validi | 2/3 |
| semanticamente raggiunte | 2/3 |
| `INVALID_TOOL_ARGUMENTS` | 1 |
| `REJECTED_SCHEMA` | 1 |
| `REJECTED_DIRECTION` | 1 |
| status finali | 0 |

Il primo caso ha prodotto chiavi top-level inattese. Il secondo ha raggiunto il validatore ma ? stato rifiutato per schema e quote non sufficienti. Il terzo ? stato rifiutato per direction incompatibile. Non sono state accettate quote inesistenti o SourceUnit inventate.

Latenza e token sono conservati nei file JSONL; il raw resta nella cache ignorata. Il criterio per autorizzare le 75 chiamate non ? raggiunto.
