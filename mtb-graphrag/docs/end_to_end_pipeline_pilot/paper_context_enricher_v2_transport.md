# Transport v2.0

Versione: `paper-context-enrichment-transport/2.0`, denominazione
documentale `OLLAMA_FORCED_TOOL_CHOICE_V2`. Controlla esclusivamente:
presenza di una singola tool call, nome esatto, `arguments` di tipo dict,
presenza dei cinque campi, tutti stringa, `decision` esattamente `QUOTE`
o `ABSTAIN`. Non rigetta mai a livello di transport: `decision=ABSTAIN`
con campi popolati, `decision=QUOTE` con summary vuoto, quote
semanticamente errata, `source_unit_id` inesistente, `abstention_reason`
vuoto — tutte queste condizioni sono deferite al validatore semantico
(`paper_context_enricher_v2_validator.py`).

## Risultati (7 chiamate)

| Esito | Conteggio |
|---|---:|
| `V2_TRANSPORT_VALID` | 7 |
| tutti gli altri (`NO_TOOL_CALL`, `TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL`, `WRONG_TOOL_NAME`, `MULTIPLE_TOOL_CALLS`, `MISSING_ARGUMENT`, `WRONG_ARGUMENT_TYPE`, `INVALID_DECISION`, `INVALID_TOOL_ARGUMENTS`) | 0 |

**7/7 transport validi** — contro 4/7 (v1.0) e 0/7 (v1.1). Lo schema
minimale, tutto-stringa, senza `evidence_kind` elimina completamente sia
la causa di fallimento osservata in v1.0 (`EVIDENCE_KIND_INVALID`) sia
quella osservata in v1.1 (`ABSTAIN_TRUE_BUT_FIELDS_POPULATED`, qui non
più un errore di transport per esplicita scelta di design — sezione 3 del
protocollo — ma un esito semantico gestito dal validatore, vedi
`paper_context_enricher_v2_validation.md`).
