# Trasporto forced-tool (OpenAI-compatible)

Il trasporto nativo Ollama usato finora è congelato come
`OLLAMA_NATIVE_TOOL_OPTIONAL/1.2` (tool-calling opzionale, il modello può
rispondere con testo libero). Per recuperare gli 8 bundle falliti nello
Stadio 1 (2 `NO_TOOL_CALL`, 6 `TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL`) è stato
introdotto `OPENAI_COMPAT_FORCED_TOOL/1.3`: stesso modello (`gemma4:cloud`),
stesso prompt 1.3, stessa definizione del tool, stesso schema flat —
cambia solo il meccanismo di invocazione, verso l'endpoint OpenAI-compatibile
di Ollama (`http://localhost:11434/v1/chat/completions`), con
`tool_choice` forzato:

```json
{"type": "function", "function": {"name": "submit_flat_claim_proposal"}}
```

`temperature=0`, `top_p=1.0`, `seed=run_index`, `max_tokens=4096`,
`stream=false`.

## Supporto di `tool_choice`

Su 8 chiamate: 7 `APPLIED_CORRECTLY` (il modello ha invocato esattamente il
tool richiesto), 1 `ACCEPTED_BUT_IGNORED` (`EB-35a15fff70830617392cfa75`:
l'endpoint ha accettato il parametro senza errore, ma la risposta non
conteneva alcuna tool-call né testo — `finish_reason=stop`, transport
risultante `FORCED_TOOL_IGNORED`). Nessun rifiuto del parametro da parte
dell'endpoint (nessun `REJECTED_BY_ENDPOINT`).

## Esiti di trasporto (8 chiamate)

| Esito | Conteggio |
|---|---:|
| `FORCED_TOOL_VALID` | 7 |
| `FORCED_TOOL_IGNORED` | 1 |
| `NO_TOOL_CALL` / `TEXT_RESPONSE` / `WRONG_TOOL_NAME` / `MULTIPLE_TOOL_CALLS` / `INVALID_TOOL_ARGUMENTS` / `HTTP_ERROR` / `TIMEOUT` | 0 |

Nessun retry semantico eseguito (0 su 8); il codice supporta retry solo per
errore HTTP 5xx/timeout/connessione, mai usato in questa run. Nessun testo
libero è stato convertito automaticamente in proposta.
