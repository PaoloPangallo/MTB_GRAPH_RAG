# ENTRYPOINTS

Sono riportati solo comandi trovati nel repository o nei README. Nessun
benchmark ufficiale è stato eseguito durante la mappatura.

## Prodotto

| Comando verificato | File | Scopo | Output/scritture | Sicurezza |
|---|---|---|---|---|
| python -m uvicorn backend.api.main:app --reload | backend/api/main.py | backend FastAPI | log/processo | V3 + legacy; casi sintetici |
| powershell -ExecutionPolicy Bypass -File .\scripts\start_v3_product.ps1 -CheckOnly | scripts/start_v3_product.ps1 | preflight V3 | stdout | read-only di processo |
| powershell -ExecutionPolicy Bypass -File .\scripts/start_v3_product.ps1 | scripts/start_v3_product.ps1 | backend/frontend V3 | processi e logs/product-v3 | side effect locale |
| npm run dev | frontend/package.json | dev server | cache Vite locale | nessun dataset |
| POST http://localhost:8000/api/v1/v3/retrieve | backend/api/routes.py | retrieval V3 | response JSON | offline rispetto a servizi esterni |

Payload minimo verificato:

~~~json
{
  "query_id": "docs-example",
  "claim_domain": "therapeutic",
  "gene": "EGFR",
  "alteration": "L858R",
  "interventions": [],
  "policy_mode": "strict_verified",
  "include_technical_records": true,
  "include_gate_trace": true,
  "include_provenance": true,
  "result_limit": 20
}
~~~

## Retrieval Python

~~~python
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline

pipeline = EvidenceRetrievalPipeline.from_config({
    "retrieval_backend": "qualified_claim_v3",
    "qualified_claim_policy_mode": "strict_verified",
})
outcome = pipeline.run(query, retrieval_backend="qualified_claim_v3")
~~~

Legge il repository materializzato; non scrive ledger o corpus.

## Test e controllo statico

| Comando | Scopo | Scritture | Nota |
|---|---|---|---|
| python -m unittest discover -s backend/tests -t . | test backend | normalmente nessuna | suite stdlib |
| python -m pytest backend/tests -q | test backend | dipende dai test | pytest non disponibile nella verifica |
| python -m unittest backend.tests.test_v3_product_output -q | test mirato V3 | nessuna prevista | prodotto invariato |
| npm run typecheck | TypeScript | eventuale cache | package.json |
| npm test -- --run | frontend | eventuale cache | Vitest |
| npm run build | build frontend | frontend/dist | scrive build |
| npm run lint | lint | nessun dataset | baseline può avere errori |

## Benchmark e utility

| Comando verificato | Scopo | Scritture | Stato |
|---|---|---|---|
| python -m benchmarks.mtb_evidence.evaluation.run_gold_evaluation --gold-bundle <PATH> | gold validation | report | ufficiale, non eseguito |
| python -m benchmarks.mtb_evidence.evaluation.run_source_cache_validation --source-abstract-cache <PATH> | cache validation | report | input esterno, non eseguito |
| PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_pilot_evaluation.py ... | pilot | risultati | manuale |
| python benchmarks/mtb_evidence/evaluation/scripts/run_qualified_retriever_prototype.py ... | prototipo | JSONL/trace | esplorativo |
| python scripts/validate_v3_schemas.py | schema check | stdout | read-only |

Gli script di promozione, rigenerazione corpus, build gold e ledger hanno
side effect e non sono stati invocati.

## Configurazioni e versioni

| Configurazione | Lettore | Default/documentato | Impatto | Rischio di confusione |
|---|---|---|---|---|
| retrieval_backend | API/pipeline | V3 route: qualified_claim_v3; default globale pipeline: legacy | seleziona il backend | non assumere il default globale nella route V3 |
| qualified_claim_policy_mode | request/backend/loader | strict_verified; anche ontology_aware_warning e audit_all | bindability e warning corpus | non è un cambio di gate |
| repository version | promotion_contract/loader | qualified_claim_repository/1.4 | asset materializzato V3 | distinta da schema e model version |
| gate version | V3 backend/shadow | qualified_claim_structural_gate/1.3 | gate trace/contract | non confonderla con le shadow storiche |
| CORS_ORIGINS | backend/api/main.py | localhost frontend ports | accesso browser | env locale, non contratto dati |
| VITE_API_BASE_URL | frontend/src/App.tsx | http://localhost:8000 | destinazione fetch | launcher V3 può usare altra porta |
| AGENT_LEDGER_PATH | control/agentic ledger | ./data/agent_events.sqlite3 | ledger V2/agentico | fuori dalla route V3 |
| NEO4J_URI, NEO4J_USER | pipeline/llm e graph | bolt://localhost:7687, user neo4j | graph live legacy | non usati da V3 |
| OLLAMA_BASE_URL | pipeline/llm | https://api.ollama.com | provider LLM legacy | non usato da V3 |
| LLM_PIPELINE, LLM_JUDGE | pipeline/llm | gemma4:31b-cloud, minimax-m2.5 | modelli legacy | nessun valore segreto esposto |

I nomi sensibili come ONCOKB_TOKEN e credenziali non sono riportati nei loro
valori. Il file .env.example è il riferimento per i nomi; .env non è stato
letto. Il default result limit del contratto query è 50, mentre il form V3
propone 20. Il repository V3 e i path corpus sono determinati da
promotion_contract.py e dal registry, non dal Knowledge Graph live.

## Legacy

run.ps1 e run.bat avviano il backend generale sulla porta 8000 e il frontend;
possono esporre route V2/agentiche. Il launcher V3 è separato.
