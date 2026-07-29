"""Test che aprono un ingresso esterno privato.

Fuori da `backend/tests/` per costruzione, non per convenzione: la discovery
della suite core (`-s backend/tests`) non arriva qui, quindi un ingresso
mancante non produce nessuno skip nella suite che non lo usa.

Un albero per ingresso, e un comando per albero:

    backend/tests_external/gold/          <- run_gold_evaluation
    backend/tests_external/source_cache/  <- run_source_cache_validation

La separazione fra i due non e' pedanteria. Prima, i test che dipendevano dalla
cache degli abstract saltavano insieme a quelli del gold e venivano contati con
loro: ottantaquattro test saltati per un ingresso, attribuiti a un altro. Un
conteggio che mescola due cause non dice niente su nessuna delle due.
"""
