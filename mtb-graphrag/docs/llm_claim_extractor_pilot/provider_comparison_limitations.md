# Limiti del confronto MiniMax / Gemma

Campione di 3 chiamate per modello: non è un campione statisticamente
significativo, è uno smoke test qualitativo sui 3 casi baseline
(DIRECT/PARTIAL/CONTRADICTED). Un solo `run_index` per bundle: non misura
la stabilità tra run ripetuti sullo stesso bundle (il pilot completo da 75
chiamate userebbe `RUNS_PER_BUNDLE=3`, qui non eseguito).

Il tag richiesto `gemma4-31b:cloud` non è mai stato disponibile in questo
ambiente; il confronto usa `gemma4:cloud` come sostituto più vicino
disponibile (stessa architettura `gemma4`, dimensione compatibile
~31-32B). Non è stato verificato se `gemma4-31b:cloud` esista come tag
separato in un catalogo cloud diverso da quello raggiungibile da questa
installazione di Ollama.

La cache documenti (`data_cache/document_grounding/`) è stata riusata
invariata dal pilot MiniMax (stesso worktree), non è stata ricostruita né
validata contro una nuova fetch di rete in questa sessione — si assume che
il testo sia identico a quello visto da MiniMax, coerente con l'obiettivo
di confrontare i modelli sugli stessi identici input.

Le risposte raw dei modelli non sono committate (solo hash e lunghezze),
quindi il confronto qualitativo (case review §8) si basa sulle proposte
canoniche post-adapter e sui `reason_codes`, non sul testo grezzo generato
dal modello.
