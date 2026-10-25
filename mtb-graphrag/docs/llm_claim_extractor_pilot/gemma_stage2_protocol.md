# Protocollo Stadio 2 — stabilità e riproducibilità

Obiettivo: misurare la stabilità e riproducibilità dell'estrazione Gemma,
non più solo il grounding. 50 chiamate autorizzate: 25 EvidenceBundle x
run_index=1 (CHECKPOINT A), poi 25 x run_index=2 (CHECKPOINT B) soltanto se
il CHECKPOINT A non produce hard stop di sicurezza. `run_index=0` non è mai
stato ripetuto.

Configurazione congelata, identica al recupero dello Stadio 1: modello
`gemma4:cloud`, endpoint OpenAI-compatible
(`http://localhost:11434/v1/chat/completions`), `tool_choice` forzato su
`submit_flat_claim_proposal`, `temperature=0`, `top_p=1.0`, `seed=run_index`,
`max_tokens=4096`, `stream=false`. Transport `OPENAI_COMPAT_FORCED_TOOL/1.3`,
prompt `llm-claim-extractor-prompt/1.3`, schema `llm-claim-proposal/1.0`,
adapter e validatore invariati. Nessuna modifica al prompt durante il pilot,
nessuna calibrazione tra CHECKPOINT A e B basata sui risultati di run 1.

Retry ammessi solo per errore infrastrutturale (timeout, HTTP 5xx,
connessione interrotta), mai per esito semantico. Retry infrastrutturali
effettivamente usati: 0 su 50 chiamate.

Esito: CHECKPOINT A completato senza hard stop -> CHECKPOINT B eseguito.
Nessun hard stop in nessuno dei due checkpoint. 50/50 chiamate eseguite.
