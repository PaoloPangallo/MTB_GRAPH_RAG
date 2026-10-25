# Protocollo Paper Context Enricher v2.0

Obiettivo: sperimentare un contratto di output molto più semplice per
Gemma — una sola scelta, QUOTE o ABSTAIN — versionato
`paper-context-enricher-prompt/2.0` e
`paper-context-enrichment-transport/2.0`. Gemma non classifica più
`evidence_kind`, non confronta formalmente candidate e documento, non
decide support status/direction/contradiction/gate/score/bucket.

Nessuna modifica o sovrascrittura di: prompt v1.0
(`paper_context_enricher_prompt.py`), prompt v1.1
(`paper_context_enricher_prompt_v1_1.py`), risultati v1.0/v1.1 già
committati, `pipeline.py` (la pipeline end-to-end precedente), i 5 casi
sintetici, la selezione dei 7 candidate-paper pair. Tutto il codice v2.0
vive in moduli nuovi e indipendenti
(`paper_context_enricher_v2*.py`), verificato staticamente da hash-pin sui
file v1 (`test_paper_context_enricher_v2.py::V1UnchangedTests`).

Campione: esattamente gli stessi 5 casi e gli stessi 7 (candidate, paper)
pair del run v1.0/v1.1. CaseContext Parser mai richiamato (riusato dalla
cache già committata); retrieval e selezione paper ricalcolati
deterministicamente (nessuna chiamata di rete) esclusivamente per provare
che coincidono con il campione congelato prima di spendere qualunque
chiamata reale (`run_pilot_v2.py::verify_frozen_sample`, confermato: 7/7
pair identici).

Budget: 7 chiamate reali (una per pair), nessun retry semantico, un solo
retry ammesso per errore infrastrutturale (mai usato in questa run).
