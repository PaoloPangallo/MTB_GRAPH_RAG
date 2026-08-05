# Protocollo del pilot di interazione end-to-end

Nuova divisione dei compiti (sezione 1 del protocollo): LLM CaseContext
Parser -> CaseContext Match Verifier (deterministico) -> retrieval
deterministico -> selezione paper deterministica -> Gemma Paper Context
Enricher (solo citazione + riassunto, mai decisione) -> validazione
deterministica -> dossier research-only.

Il precedente `LlmClaimProposalValidator`/`ClaimSupportVerifier`/
`FlatToolArgumentsAdapter` (branch `research/v3-llm-claim-extractor-pilot`)
resta congelato e non è mai usato come componente decisionale qui — solo
il pattern tecnico generico (trasporto forzato via endpoint
OpenAI-compatible di Ollama, retry solo infrastrutturale, hashing) è
riusato, reimplementato in un package nuovo e indipendente
(`benchmarks/mtb_evidence/end_to_end_pipeline_pilot/`). Un test
(`RuntimeInvariantTests.test_pilot_package_never_imports_claim_extractor_decision_classes`)
verifica staticamente che nessun modulo di questo pilot importi
`LlmClaimProposalValidator`, `ClaimSupportVerifier` o
`FlatToolArgumentsAdapter`.

Budget: 20 chiamate reali massime, nessun retry semantico, un solo retry
ammesso per errore infrastrutturale (timeout/HTTP 5xx/connessione). Nessuna
modifica a prompt/schema/validatore durante il pilot (sezione 19).

Branch: `research/v3-end-to-end-pipeline-interaction-pilot`, creato dal
commit `6c345ca` di `research/v3-llm-claim-extractor-pilot`.
