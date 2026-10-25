# Blocker report

Il secondo tentativo con gemma4:26b in cloud è bloccato.

Ollama 0.18.3 è operativo, ma:

- gemma4:26b non compare in ollama list;
- ollama show gemma4:26b restituisce model not found;
- il controllo del tag gemma4:26b-cloud non rende disponibile il modello.

Non è stato eseguito pull/download e non è stato usato alcun fallback. Smoke test
e 75 chiamate del pilot restano non eseguiti.

Stato: MODEL_CLOUD_NOT_ACCESSIBLE.
