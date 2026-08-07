# 04 — Contratto di output del Narrator

Output **strutturato**, mai free-text non tipizzato.

```json
{
  "narrative_summary": "...",
  "candidate_narratives": [{"candidate_id": "...", "text": "..."}],
  "limitations_summary": "...",
  "closing_note": "..."
}
```

`additionalProperties: false` sull'oggetto esterno **e** su ogni voce di
`candidate_narratives`. Nessun campo opzionale che permetta di creare un
concetto clinico nuovo.

## Cosa il modello non può emettere

Verificato eseguendo il trasporto reale: `canonical_status`, `support_mask`,
`gate_bucket`, `provenance`, `pmid` producono tutti `INVALID_TOOL_ARGUMENTS`.

Non è una restrizione di prompt: è lo schema, più `_argument_errors` che rifiuta
le chiavi extra, più il trasporto che scarta la chiamata.

## Metadati aggiunti localmente

`narrative_id`, `narrative_hash`, `narrator_input_hash`, `model`,
`prompt_version`, `transport_version`, `language`, `timestamp`.

Il modello non li produce. È la stessa disciplina di `enricher_v2`.

## Esiti del trasporto

```
FORCED_TOOL_VALID · NO_TOOL_CALL · TEXT_RESPONSE · FORCED_TOOL_IGNORED
MULTIPLE_TOOL_CALLS · WRONG_TOOL_NAME · INVALID_TOOL_ARGUMENTS · TIMEOUT · HTTP_ERROR
```

`FORCED_TOOL_VALID` significa soltanto che la **forma** è corretta. La fedeltà è
decisa dallo stage 15.
