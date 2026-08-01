# Mappa tecnica del repository

Questa directory descrive MTB-GraphRAG al commit
6ebfe56d19be6eb56266820c52fdc5a708c17a84, sul branch
docs/repository-architecture-map. È una mappa documentale: non cambia il
comportamento di V3 e non sostituisce i contratti già congelati.

## Percorso di lettura

1. [PROJECT_MAP.md](PROJECT_MAP.md)
2. [V3_RUNTIME_FLOW.md](V3_RUNTIME_FLOW.md)
3. [MAIN_FILES.md](MAIN_FILES.md)
4. [DATA_ASSETS.md](DATA_ASSETS.md)
5. [ENTRYPOINTS.md](ENTRYPOINTS.md)
6. [DEPENDENCY_GRAPH.md](DEPENDENCY_GRAPH.md)
7. [LEGACY_AND_EXPERIMENTS.md](LEGACY_AND_EXPERIMENTS.md)
8. [UNREFERENCED_FILES.md](UNREFERENCED_FILES.md)
9. [FILE_INVENTORY.csv](FILE_INVENTORY.csv)

Il contratto claim/case/decision è descritto nell'audit già esistente:
[claim_data_contract_audit.md](../v3_pipeline_ui/claim_data_contract_audit.md).
Questa mappa ne riassume i punti di integrazione senza duplicarne la
tracciatura end-to-end.

## Percorsi per ruolo

- Relatore: PROJECT_MAP.md, V3_RUNTIME_FLOW.md, DATA_ASSETS.md,
  LEGACY_AND_EXPERIMENTS.md.
- Backend: route in backend/api/routes.py, schemi in
  backend/api/v3_schemas.py, pipeline e backend qualificato in
  backend/pipeline/evidence/retrieval/.
- Frontend: frontend/src/App.tsx, frontend/src/types.ts,
  frontend/src/components/V3RunForm.tsx e
  frontend/src/components/V3EvidenceView.tsx.
- Corpus: backend/pipeline/evidence/corpus/ e DATA_ASSETS.md.
- Benchmark: benchmarks/mtb_evidence/evaluation/,
  benchmarks/mtb_evidence/v3/ e LEGACY_AND_EXPERIMENTS.md.

## Metodo e limiti

L'inventario combina import AST/regex, riferimenti testuali, route, entrypoint
CLI, configurazioni e documentazione. Un file non importato non viene
automaticamente considerato inutilizzato: gli script manuali e le pipeline
di build sono marcati MANUAL_ENTRYPOINT o USAGE_UNCERTAIN quando non è
possibile dimostrare l'uso corrente. Le metriche complete e le euristiche sono
in FILE_INVENTORY.csv.

*** Add File: mtb-graphrag/docs/repository_map/PROJECT_MAP.md
# PROJECT_MAP

## Obiettivo

MTB-GraphRAG è un prototipo di ricerca per preparare evidenze revisionabili
per un Molecular Tumor Board. Il prodotto non formula decisioni terapeutiche
autonome. Il repository contiene sia il runtime V3 strutturale attuale sia
l'architettura storica V2/agentica, i percorsi di costruzione dei dati, la
provenance e campagne sperimentali.

## Stato congelato documentato

Il percorso V3 di prodotto è:

POST /api/v1/v3/retrieve → qualified_claim_v3 →
qualified_claim_repository/1.4 → structural gate 1.3 → scoring e bucket
native → adapter V3 → response Pydantic → client React V3.

La route V3 non usa planner, LLM, Neo4j live, web search, PubMed live o
endpoint V2. Il repository materializzato è il confine runtime; la sua
provenance mantiene il legame con parent record e source unit.

## Struttura funzionale

| Area | Directory/file principali | Ruolo |
|---|---|---|
| V3 runtime | backend/pipeline/evidence/retrieval/ | Query tipizzata, pipeline, backend, risultati, scoring e provenance |
| Backend API | backend/api/ | FastAPI, route, schemi, adapter e sottografo legacy |
| Frontend | frontend/src/ | Form V3, client, tipi, dossier/evidence/pipeline/provenance |
| Corpus | backend/pipeline/evidence/corpus/ | Loader, registry, repository materializzato, promozione e rollback |
| KG | backend/pipeline/cypher.py, helpers.py, api/subgraph.py | Query Neo4j e percorsi storici di estrazione |
| Provenance | backend/pipeline/control/, agentic/ledger.py | ledger, replay, vista canonica, verificatori |
| V2/agentico | backend/pipeline/agents/, graph.py, agentic/ | planner, strumenti, LangGraph e strategie |
| LLM/rendering | backend/pipeline/llm/, control/rendering/ | adapter Ollama/Neo4j e rendering/verifica |
| Esperimenti | benchmarks/, experiments/, backend/evaluation/ | protocolli, run, report, output e campagne |
| Utility | scripts/, script root e strumenti evaluation | validazione, migrazione, debug, build e manutenzione |

## Separazione prodotto/ricerca

- Il prodotto V3 è offline e deterministico rispetto a query, repository e
  policy.
- Il backend mantiene route legacy, confronto e percorso agentico; non sono
  dipendenze della route V3.
- benchmarks/mtb_evidence/v3/ contiene contratti, audit, fixture e risultati
  di campagne V3. final_experiment/ e relativi manifest sono artefatti
  ufficiali: sono solo referenziati in questa fase.
- experiments/reproducibility/ e experiments/thesis_alignment/ sono script e
  casi di studio storici, con possibile invocazione manuale.

## Lettura consigliata

Per il runtime: V3_RUNTIME_FLOW.md, poi la route, gli schemi, la pipeline,
v3_backend.py, v3_query.py, v3_result.py e il frontend.

Per i dati: DATA_ASSETS.md, promotion_contract.py, loader.py e il repository
backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/.

Per il passato: LEGACY_AND_EXPERIMENTS.md, poi graph.py, agents/ e control/.

## Numeri dell'inventario

Il conteggio principale è riproducibile con git ls-files, escludendo directory
di ambiente/build/cache e binari: 2.247 file tracciati, 483 Python, 22
TypeScript/TSX, 486 file eseguibili per estensione e circa 612,83 MiB.
Una scansione del working tree con la stessa esclusione conta 2.293 file,
circa 676,47 MiB e 487 file eseguibili. La differenza comprende artefatti
esplorativi non tracciati presenti all'avvio.

*** Add File: mtb-graphrag/docs/repository_map/V3_RUNTIME_FLOW.md
# V3_RUNTIME_FLOW

## Percorso reale endpoint → UI

La route corrente è POST /api/v1/v3/retrieve in backend/api/routes.py,
funzione v3_retrieve. Riceve V3RetrieveRequest, lo converte con to_query(),
costruisce EvidenceRetrievalPipeline con backend esplicito
qualified_claim_v3, esegue run e passa il risultato a
backend/api/v3_presentation.py::present_retrieval_outcome.

| Passo | File e simbolo | Input → output | Responsabilità | Side effect | Copertura |
|---|---|---|---|---|---|
| Route | backend/api/routes.py::v3_retrieve | HTTP JSON → V3RetrieveResponse | Binding FastAPI, selezione V3 | nessun write applicativo | backend/tests/test_v3_product_output.py |
| Request | backend/api/v3_schemas.py::V3RetrieveRequest.to_query | request → query | forma e normalizzazione richiesta | nessuno | test API/schema V3 |
| Pipeline | retrieval/pipeline.py::EvidenceRetrievalPipeline.from_config/run | query → RetrievalOutcome | selezione backend e osservabilità | memoria soltanto | pipeline tests |
| Backend | retrieval/v3_backend.py::QualifiedClaimRetrieverV3.retrieve | query → quattro bucket | carica corpus, gate, score e rank | lettura corpus/hash | retriever tests |
| Repository | corpus/loader.py::load_from_registry | registry → PromotedCorpus | verifica e materializza indici | letture | loader tests |
| Gate | shadow/integrated_gates_v13.py | query + claim → gate result | structural gate 1.3 | nessuno | gate tests |
| Scoring | retrieval/v3_scoring.py::score | gate result → ClaimScore | score ed eligibility | nessuno | scoring tests |
| Risultato | retrieval/v3_result.py | native result → buckets/provenance | claim, parent, trace, reason, provenance | nessuno | result tests |
| Adapter | api/v3_presentation.py::present_retrieval_outcome | native outcome → dict | evidence e technical records | nessuno | V3 output tests |
| Schema | api/v3_schemas.py::V3RetrieveResponse | dict → Pydantic | contratto JSON | nessuno | API tests |
| Client | frontend/src/App.tsx::handleV3Run | form → fetch | HTTP e stato UI | fetch HTTP | component tests |
| Tipi | frontend/src/types.ts | JSON → TS types | contratto TypeScript | nessuno | tsc |
| Vista | frontend/src/components/V3EvidenceView.tsx | response → card/tabs | dossier, confronto, score, provenance | DOM only | Vitest |

## Punti di trasformazione

Il dettaglio del claim pilota è in
[docs/v3_pipeline_ui/claim_data_contract_audit.md](../v3_pipeline_ui/claim_data_contract_audit.md).
La catena tecnica è:

1. il repository conserva la forma sorgente e le relazioni disponibili;
2. v3_objects.py reidrata claim, parent, unsupported e unresolved object;
3. v3_result.py conserva riferimenti tecnici, gate trace e provenance;
4. v3_presentation.py proietta il contratto pubblico e separa evidence da
   technical_records;
5. V3EvidenceView presenta i dati senza ricostruire campi mancanti.

Quando un campo non è alla fonte, la response deve restare null. La tripla
segue la gerarchia dell'audit: claim text reale, tripla reale,
biomarker/direction/intervention, infine claim id con avviso.

## Diagramma Mermaid

~~~mermaid
flowchart TD
  route[backend/api/routes.py:v3_retrieve] --> req[backend/api/v3_schemas.py:V3RetrieveRequest.to_query]
  req --> run[EvidenceRetrievalPipeline.run]
  run --> back[QualifiedClaimRetrieverV3.retrieve]
  back --> query[QualifiedClaimQuery]
  back --> load[loader.load_from_registry]
  back --> gate[integrated_gates_v13]
  gate --> score[v3_scoring.score]
  score --> native[QualifiedClaimResult]
  native --> adapter[v3_presentation.present_retrieval_outcome]
  adapter --> response[V3RetrieveResponse]
  response --> client[frontend/src/App.tsx:handleV3Run]
  client --> view[frontend/src/components/V3EvidenceView.tsx]
~~~

## Runtime versus rendering opzionale

La route V3 è strutturale: non attraversa graph.py, agents/ o llm/. Il
rendering LLM esiste nel percorso V2/agentico, ma non è necessario per la
response V3. La route V3 non scrive ledger, non interroga Neo4j e non chiama
provider esterni.
