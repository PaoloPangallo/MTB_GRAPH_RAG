# DEPENDENCY_GRAPH

## Diagramma alto livello

~~~mermaid
flowchart LR
  ui[Frontend V3] --> api[FastAPI /api/v1/v3/retrieve]
  api --> req[V3RetrieveRequest]
  req --> pipe[EvidenceRetrievalPipeline]
  pipe --> v3[QualifiedClaimRetrieverV3]
  v3 --> corpus[Promoted corpus 1.4]
  v3 --> gate[Structural gate 1.3]
  gate --> scoring[Native scoring]
  scoring --> bucket[Native buckets]
  bucket --> adapter[v3_presentation.py]
  adapter --> response[V3RetrieveResponse]
  response --> ui
  corpus --> prov[Parent/source-unit provenance]
  legacy[Legacy V2 and agentic] --> graph[Neo4j and LLM]
  graph --> ledger[SQLite ledger]
  legacy --> legacyui[Legacy UI and comparison]
~~~

## Diagramma runtime V3

~~~mermaid
flowchart TD
  r[backend/api/routes.py:v3_retrieve] --> s[backend/api/v3_schemas.py]
  s --> p[retrieval/pipeline.py:run]
  p --> b[retrieval/v3_backend.py:retrieve]
  b --> q[retrieval/v3_query.py]
  b --> l[corpus/loader.py]
  b --> o[retrieval/v3_objects.py]
  b --> g[shadow/integrated_gates_v13.py]
  g --> sc[retrieval/v3_scoring.py:score]
  sc --> rr[retrieval/v3_result.py]
  rr --> a[api/v3_presentation.py]
  a --> t[api/v3_schemas.py:V3RetrieveResponse]
  t --> c[frontend/src/App.tsx]
  c --> v[frontend/src/components/V3EvidenceView.tsx]
~~~

## Dipendenze dati e legenda

GraphEvidenceRecord/source unit → conversioni/promozione →
qualified_claim_repository_1_4 → loader/indici → candidate/parent object →
gate trace/score/bucket → adapter → UI. Il Knowledge Graph live è fuori da
questa linea e appartiene ai percorsi legacy.

Rettangolo = modulo o asset; freccia = chiamata/dipendenza; legacy = percorso
storico; ledger = scrittura append-only solo nei run V2/agentici.
