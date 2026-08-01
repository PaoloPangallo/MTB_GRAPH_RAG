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
