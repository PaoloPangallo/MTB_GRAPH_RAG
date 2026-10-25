# Confronto Paper Context Enricher: prompt v1.0 vs v1.1

Rivalutazione richiesta esplicitamente: stesso modello (`gemma4:cloud`),
stesso transport (`OLLAMA_FORCED_TOOL_CHOICE`), stesso tool
(`submit_paper_context_enrichment`, schema invariato), stessi 5 casi,
stessi 7 (candidate, paper) da arricchire — **CaseContext Parser mai
richiamato** (riusato dalla cache v1.0), retrieval e selezione paper
ricalcolati deterministicamente (nessuna chiamata reale, esito identico a
v1.0). Unica variabile: il system prompt del Paper Context Enricher,
versionato `paper-context-enricher-prompt/1.1`
(`paper_context_enricher_prompt_v1_1.py`), che sostituisce
`paper-context-enricher-prompt/1.0` **solo per questa rivalutazione** — il
modulo v1.0 resta invariato e continua a essere quello di default nel
resto della pipeline.

Modifica di supporto applicata al validatore (`enrichment_validator.py`):
un `author_context_summary` vuoto non è più rigettato automaticamente
(`REJECTED_SUMMARY_UNGROUNDED`), ma accettato con warning
`SUMMARY_EMPTY` — necessario perché il prompt v1.1 dichiara esplicitamente
"the summary may be empty ... do not abstain only because the summary is
empty", e il vecchio comportamento del validatore avrebbe rigettato
esattamente il comportamento che il nuovo prompt chiede.

## Risultati

| Metrica | v1.0 | v1.1 |
|---|---:|---:|
| Chiamate eseguite | 7 | 7 |
| Transport validi | 4 | **0** |
| Astensioni valide | 4 | 0 |
| `ENRICHMENT_ACCEPTED`/`_WITH_WARNING` | 0 | 0 |
| `REJECTED_TRANSPORT` | 3 | **7** |
| Hard stop | 0 | 0 |

## Dettaglio dei fallimenti v1.1 (7/7 `INVALID_TOOL_ARGUMENTS`)

| Motivo | Occorrenze |
|---|---:|
| `EVIDENCE_KIND_INVALID` (valore fuori enum) | 5 |
| `ABSTAIN_TRUE_BUT_FIELDS_POPULATED` (abstain=true ma altri campi non nulli) | 4 |

Il secondo motivo è nuovo rispetto a v1.0 (mai osservato prima) e appare
correlato alle istruzioni più elaborate di v1.1 sull'astensione ("Do not
abstain merely because...", "Negative, uncertain and contradictory
findings are valid enrichments"): il modello sembra tentare di fornire
comunque un `evidence_kind` o una citazione parziale insieme ad
`abstain=true`, violando lo schema flat che richiede tutti gli altri campi
nulli quando `abstain=true`.

## Lettura

Il prompt v1.1 è stato scritto per essere più permissivo e ridurre le
astensioni eccessivamente caute osservate in v1.0 (`Negative, uncertain
and contradictory findings are valid enrichments and must be quoted
faithfully`). L'effetto osservato è opposto a quello inteso: **il tasso di
successo del trasporto crolla dal 57% (4/7) allo 0% (0/7)** — non per un
problema di grounding semantico, ma perché il modello rispetta meno
rigorosamente lo schema flat richiesto, specialmente nella combinazione
`abstain=true` + campi popolati. Zero esempi di `ENRICHMENT_ACCEPTED` sono
stati ottenuti con nessuna delle due versioni del prompt in questa
sessione.

Nessun retry semantico effettuato. Nessuna modifica ulteriore al prompt
tentata in risposta a questo esito, per rispetto del divieto di
calibrazione durante il pilot.
