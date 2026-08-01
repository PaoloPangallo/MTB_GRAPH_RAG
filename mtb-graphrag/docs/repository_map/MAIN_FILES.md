# MAIN_FILES

La tabella è concentrata sui file che spiegano l'architettura. L'elenco
completo è in FILE_INVENTORY.csv.

| Path | Categoria | Responsabilità | Runtime | Entry point | Dipendenze principali | Side effect | Test | Stato | Note |
|---|---|---|---|---|---|---|---|---|---|
| backend/api/main.py | BACKEND_API | FastAPI, CORS, router | V3 + legacy | uvicorn | FastAPI, routes | startup/log | API/import | corrente | CORS da env |
| backend/api/routes.py | BACKEND_API | route V3 e legacy | V3 diretto; legacy separato | HTTP | schemi, pipeline, graph, LLM | legacy servizi | API tests | corrente + legacy | route /v3/retrieve |
| backend/api/v3_schemas.py | BACKEND_API | request/response Pydantic | V3 | import route | Pydantic, query | nessuno | V3 tests | corrente | contratto pubblico |
| backend/api/v3_presentation.py | BACKEND_API | native outcome → response | V3 | route | v3_result, schemi | nessuno | V3 output | corrente | evidence/technical |
| backend/pipeline/evidence/retrieval/pipeline.py | V3_RUNTIME_CORE | orchestrazione backend | V3 + legacy config | Python/API | backends | osservabilità memoria | pipeline tests | corrente | V3 esplicito |
| backend/pipeline/evidence/retrieval/backends.py | V3_RUNTIME_CORE | costanti/config backend | V3 | import | config/policy | nessuno | backend tests | corrente | default globale legacy |
| backend/pipeline/evidence/retrieval/v3_backend.py | V3_RUNTIME_CORE | retriever qualificato | V3 | class | loader, gate, scoring | corpus read | retriever tests | corrente | offline |
| backend/pipeline/evidence/retrieval/legacy_backend.py | LEGACY | adapter retriever precedente | legacy | class | qualified_retriever | corpus read | legacy retriever tests | legacy | separato da qualified_claim_v3 |
| backend/pipeline/evidence/retrieval/v3_query.py | V3_RUNTIME_CORE | query e normalizzazione | V3 | build_query | contract normalizer | nessuno | query tests | corrente | original/normalized |
| backend/pipeline/evidence/retrieval/v3_objects.py | V3_RUNTIME_CORE | claim/parent rehydration | V3 | claim_objects | corpus models | nessuno | object tests | corrente | classi tecniche |
| backend/pipeline/evidence/retrieval/v3_result.py | V3_RUNTIME_CORE | result, bucket, provenance | V3 | result class | contract types | nessuno | result tests | corrente | trace/reasons |
| backend/pipeline/evidence/retrieval/v3_scoring.py | V3_RUNTIME_CORE | score e eligibility | V3 | score | shadow scoring | nessuno | scoring tests | congelato | semantica protetta |
| backend/pipeline/evidence/shadow/integrated_gates_v13.py | V3_RUNTIME_CORE | structural gate 1.3 | V3 | evaluate | structural policy | nessuno | gate tests | congelato | semantica protetta |
| backend/pipeline/evidence/corpus/promotion_contract.py | QUALIFIED_CLAIMS_AND_CORPUS | versioni e registry | V3 load | import | pathlib/json | nessuno | corpus tests | corrente | repository 1.4 |
| backend/pipeline/evidence/corpus/loader.py | QUALIFIED_CLAIMS_AND_CORPUS | load/verifica corpus | V3 | load_from_registry | registry/integrity | lettura | loader tests | corrente | indici in memoria |
| backend/pipeline/evidence/corpus/v3/prototype_corpus_registry.json | QUALIFIED_CLAIMS_AND_CORPUS | manifest registry | V3 | loader | repository paths | nessuno | integrity | frozen | non riscrivere |
| backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/ | QUALIFIED_CLAIMS_AND_CORPUS | dataset materializzato | V3 | loader | JSON/JSONL | lettura | corpus tests | frozen | claim/parent/link |
| backend/pipeline/graph.py | V2_AGENTIC | LangGraph storico | legacy | import/route | agents, LangGraph, Neo4j | servizi esterni | legacy | legacy | non V3 |
| backend/pipeline/control/runner.py | PROVENANCE_AND_LEDGER | pipeline verificabile | V2/agentico | run_verified_pipeline | ledger, strategies | scrive ledger | control | legacy/product | non V3 |
| backend/pipeline/agentic/ledger.py | PROVENANCE_AND_LEDGER | ledger SQLite | V2/agentico | EventLedger | sqlite | scrive data/agent_events.sqlite3 | ledger | legacy/product | append-only |
| backend/pipeline/llm/ollama_adapter.py | LLM_AND_RENDERING | client/modelli LLM | legacy | import/config | Ollama | rete | LLM | legacy | non V3 |
| backend/pipeline/cypher.py | KNOWLEDGE_GRAPH | query Cypher | legacy/KG | helper | Neo4j | query live | graph | legacy | non V3 |
| backend/api/subgraph.py | KNOWLEDGE_GRAPH | estrazione subgrafo | legacy | route/helper | Neo4j, Cypher | query live | API/graph | legacy | non V3 |
| frontend/src/App.tsx | FRONTEND_V3 | shell, client, viste | V3 + legacy UI | npm run dev | React, API | fetch | component | corrente + legacy | integra entrambe |
| frontend/src/types.ts | FRONTEND_V3 | tipi request/response | V3 + legacy | import TS | React types | nessuno | typecheck | corrente + legacy | contratto TS |
| frontend/src/components/V3RunForm.tsx | FRONTEND_V3 | form V3 | V3 | React | types | DOM state | Vitest | corrente | strict verified |
| frontend/src/components/V3EvidenceView.tsx | FRONTEND_V3 | dossier/evidence/provenance | V3 | React | types | DOM | Vitest | corrente | non calcola gate |
| benchmarks/mtb_evidence/evaluation/run_gold_evaluation.py | EXPERIMENTS_AND_BENCHMARKS | runner gold esterno | benchmark | python -m | gold privato | report | external tests | ufficiale | non eseguito |
| benchmarks/mtb_evidence/evaluation/scripts/run_qualified_retriever_prototype.py | EXPERIMENTS_AND_BENCHMARKS | runner prototipo | esperimento | CLI | V3 retriever | JSONL/trace | prototype | esplorativo | non endpoint |
| backend/evaluation/run_benchmark.py | EXPERIMENTS_AND_BENCHMARKS | benchmark storico | benchmark | python -m | CSV/casi | report | evaluation | legacy | non V3 |
| scripts/validate_v3_schemas.py | UTILITIES_AND_MIGRATIONS | validazione schema | manuale | python | JSON schema | stdout | utility | corrente | read-only |
| scripts/start_v3_product.ps1 | UTILITIES_AND_MIGRATIONS | launcher prodotto V3 | manuale | PowerShell | uvicorn/npm | processi/log | nessuno | locale | fuori commit |
