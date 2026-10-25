# Diagnosi del primo smoke

Le risposte raw non sono recuperabili integralmente. Il runner precedente ha
conservato solo raw_response_hash, raw_response_length, token e parse_error;
smoke_raw.jsonl contiene soltanto hash e campo raw vuoto per protezione.

| Caso | content length | output token | done_reason | thinking | tool call | classificazione |
|---|---:|---:|---|---|---|---|
| DIRECT | 0 | 1024 | NOT_CAPTURED | NOT_CAPTURED | NOT_CAPTURED | RAW_CAPTURE_GAP |
| PARTIAL | 0 | 1024 | NOT_CAPTURED | NOT_CAPTURED | NOT_CAPTURED | RAW_CAPTURE_GAP |
| CONTRADICTED | 654 | 1024 | NOT_CAPTURED | NOT_CAPTURED | NOT_CAPTURED | RAW_CAPTURE_GAP |

Per tutti i casi il parser aveva segnalato JSON_PARSE_ERROR. Non è possibile
stabilire retroattivamente se done_reason fosse length, se il JSON fosse
troncato, o se thinking fosse separato. Non viene quindi dichiarata una causa
semantica inventata.
