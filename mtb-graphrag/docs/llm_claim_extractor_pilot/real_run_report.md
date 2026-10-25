# Real run report

Il pilot reale è stato fermato dopo lo smoke test.

- modello: minimax-m3:cloud
- endpoint: ollama Python client, ollama.chat
- chiamate smoke: 3
- chiamate previste complessive: 75
- chiamate complessive eseguite: 3
- output JSON validi: 0
- esito validatore: REJECTED_SCHEMA per tutti i tre casi
- chiamate residue: non eseguite
- corpus completo: non eseguito

Il modello è accessibile, ma l'output non è utilizzabile dal parser JSON locale.
Non sono state applicate riparazioni sintattiche o semantiche.
