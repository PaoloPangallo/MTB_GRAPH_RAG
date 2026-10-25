# Trasporto flat 1.2

Sono mantenuti separati `RAW_JSON_TEXT` 1.0 e `TOOL_CALL_NESTED` 1.1. Il nuovo contratto ? `TOOL_CALL_FLAT`, versione `llm-claim-proposal-transport/1.2`, con funzione `submit_flat_claim_proposal`.

Tutti i campi sono top-level: valore, ID delle SourceUnit, quote ed explicitness. Il parser rifiuta oggetti annidati, array serializzati come stringhe, chiavi extra e tipi errati. Non usa regex per ricostruire oggetti e non applica fallback alla baseline.
