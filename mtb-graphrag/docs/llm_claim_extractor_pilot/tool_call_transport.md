# Trasporto tool-call 1.1

Il protocollo precedente resta congelato come `RAW_JSON_TEXT` (prompt e schema 1.0). Il nuovo trasporto usa una sola funzione `submit_claim_proposal`. Il modello deve invocarla una volta; gli argomenti sono acquisiti come struttura, mentre il testo libero non ? usato per costruire la claim.

Il parser accetta solo una chiamata con nome esatto e argomenti conformi anche nella struttura annidata. Una chiamata presente ma con argomenti deformati ? `INVALID_TOOL_ARGUMENTS`, non una proposta valida. Non viene applicata riparazione semantica.

`think=false` ? inviato esplicitamente. `message.content`, `message.thinking` e `message.tool_calls` sono registrati separatamente. Il thinking non entra nella validazione.

Il protocollo non esegue la funzione: usa soltanto gli argomenti della chiamata come trasporto.
