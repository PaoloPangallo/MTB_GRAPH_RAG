# Paper Context Enricher (Gemma)

Nuovo componente research-only, **non** chiamato `ClaimExtractor`. Prompt
versionato `paper-context-enricher-prompt/1.0`
(`paper_context_enricher_prompt.py`), tool call forzato
`submit_paper_context_enrichment`, `gemma4:cloud`, `temperature=0`,
`think=false`, `max_tokens=2048`, trasporto `OLLAMA_FORCED_TOOL_CHOICE`
(lo stesso endpoint OpenAI-compatible di Ollama già validato nel recupero
dello Stadio 1 del Claim Extractor — nessun servizio OpenAI). Gemma non
riceve mai `enrichment_id`/`case_id`/`candidate_id`/`paper_id`: questi sono
sempre assegnati deterministicamente dall'adapter, così il modello non può
inventare identificatori.

## Risultati (7 chiamate)

| Esito trasporto | Conteggio |
|---|---:|
| `FORCED_TOOL_VALID` | 4 |
| `INVALID_TOOL_ARGUMENTS` (`EVIDENCE_KIND_INVALID`) | 3 |

Sulle 4 chiamate con trasporto valido, **tutte e 4** hanno prodotto
`abstain=true` con motivazioni esplicite e grounded:

- Caso 3 (2x): il testo discute il protocollo statistico di uno studio
  senza riportarne i risultati, oppure discute "immune checkpoint
  blockade" in generale senza mai nominare "nivolumab".
- Caso 4 (2x): il testo discute **BGJ398**, non **infigratinib** —
  Gemma ha correttamente rilevato che il farmaco richiesto non è quello
  discusso nel documento e si è astenuto, invece di trattare BGJ398 come
  equivalente o inventare un collegamento.

Le 3 chiamate con `EVIDENCE_KIND_INVALID` sono un vincolo di schema non
rispettato dal modello (valore fuori enum) — un limite tecnico del
transport/modello, non un errore di grounding; nessuna proposta
scorretta è stata accettata in nessuno dei due casi. Vedi
`pilot_limitations.md` per la lettura completa e
`architectural_decision.md` per la raccomandazione.
