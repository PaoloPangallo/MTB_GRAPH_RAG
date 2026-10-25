# PROJECT_MAP

## Obiettivo

MTB-GraphRAG è un prototipo di ricerca per preparare evidenze revisionabili
per un Molecular Tumor Board. Il prodotto non formula decisioni terapeutiche
autonome. Il repository contiene sia il runtime V3 strutturale attuale sia
l'architettura storica V2/agentica, i percorsi di costruzione dei dati, la
provenance e campagne sperimentali.

## Stato di partenza registrato

- Branch di partenza: feat/v3-pipeline-observability-ui.
- Commit di partenza: 6ebfe56d19be6eb56266820c52fdc5a708c17a84.
- Branch creato per la documentazione: docs/repository-architecture-map.
- Stato iniziale Git: working tree con soli artefatti non tracciati già
  presenti; nessuna modifica tracked da sovrascrivere. Gli artefatti erano
  manual_v3_cases/, i quattro case_*_api_response.json, gli script e i
  documenti superpowers della correzione V3. Sono rimasti fuori dal commit.

Il conteggio è stato fatto senza .git, ambienti virtuali, node_modules, cache,
build/dist/coverage, output temporanei e binari non pertinenti.

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
