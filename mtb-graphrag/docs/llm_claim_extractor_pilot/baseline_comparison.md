# A/B/C baseline comparison

| Percorso | Unità | DIRECT | PARTIAL | AMBIGUOUS | CONTRADICTED | NO_SUPPORT_FOUND | DOCUMENT_UNAVAILABLE |
|---|---:|---:|---:|---:|---:|---:|---:|
| A single SourceUnit + rules | candidate | 1 | 11 | 4 | 0 | 8 | 16 |
| B EvidenceBundle + rules | candidate | 1 | 8 | 5 | 2 | 8 | 16 |
| C bundle + LLM + validator | candidate | non eseguito | non eseguito | non eseguito | non eseguito | non eseguito | non eseguito |

C è bloccato da MODEL_NOT_CONFIGURED. I numeri A/B sono baseline congelate,
non risultati prodotti dal provider LLM.
