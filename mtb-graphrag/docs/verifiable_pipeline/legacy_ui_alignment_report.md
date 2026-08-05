# Allineamento della UI alla pipeline finale

Stato al commit corrente del branch `feature/v3-verifiable-pipeline-ui`.

## 1. La pagina degli screenshot era legacy

La domanda posta era se la schermata revisionata fosse una pagina della vecchia
V3 o la nuova Supervisor Mode rimasta incompleta. È il primo caso, e la
distinzione non era ricostruibile guardando la pagina.

| | Valore |
|---|---|
| Rotta (prima) | nessuna: vista iniziale di `App`, dietro `useState(researchView)` |
| Componente | `frontend/src/components/V3EvidenceView.tsx` |
| Form di ingresso | `V3RunForm` / `InputForm` — campi strutturati |
| Endpoint | `POST /api/v1/v3/retrieve` |
| Orchestratore | percorso V3 preesistente (`backend/api/v3_presentation.py`) |
| Repository | `qualified_claim_repository/1.4` |
| Pipeline eseguita | input strutturato → CaseContext normalizzato → qualified claim → gate strutturali → bucket → provenienza parent-level → dossier |

Le tre stringhe che identificano la pagina senza ambiguità, tutte in
`V3EvidenceView.tsx`:

- `Catena verificabile: Qualified Claim → Parent GraphEvidenceRecord → Source Unit → PMID / DOI / NCT / URL / locator` (riga 312);
- `Evidenze principali` (riga 25);
- `Applicabilità non valutata separatamente` (righe 158 e 162).

Nessuna compare in `backend/research_pipeline/`. Un `grep qualified_claim` su
quel pacchetto non trova nulla: la nuova pipeline non ha mai letto quel
repository.

**La nuova Supervisor Mode esisteva già ed era collegata alla pipeline reale.**
Non era un guscio: `ResearchConsole` chiamava `/api/v1/research/pipeline/*`, che
esegue `orchestrator.run_case`. Era però raggiungibile solo da un bottone
nell'AppBar, e la home apriva la vista storica. Il disallineamento era di
percorso e di completezza della resa, non di sostanza della pipeline.

## 2. Le due rotte oggi

| | Verifiable Research Pipeline | Legacy V3 |
|---|---|---|
| Rotta | `/research/verifiable-pipeline` | `/legacy/v3-deterministic` |
| Con run | `/research/verifiable-pipeline/runs/{run_id}` | — |
| Componente | `research/ResearchConsole.tsx` | `legacy/LegacyV3Console.tsx` |
| Ingresso | textarea in linguaggio libero | campi strutturati |
| Endpoint | `/api/v1/research/pipeline/*` | `POST /api/v1/v3/retrieve` |
| Orchestratore | `research_pipeline/orchestrator.py` | percorso V3 preesistente |
| Repository | `graph_candidate_repository/2.0` | `qualified_claim_repository/1.4` |
| Oggetto | `GraphCandidateAssertion` | Qualified Claim |
| In navigazione | rotta principale; `/` vi reindirizza | link secondario, in fondo alla barra nera |

Il backend è condiviso a livello di processo — stessa app FastAPI — ma i due
percorsi non condividono router, orchestratore, repository né vocabolario.

## 3. Cosa è stato spostato e cosa no

`App.tsx` conteneva sia le viste storiche sia il rimando alla console. È stato
scomposto:

- `src/legacy/LegacyV3Console.tsx` — l'intero corpo precedente, **spostato con
  `git mv` e non riscritto**. Le sole modifiche sono gli import relativi, la
  rimozione del toggle `researchView` e l'aggiunta della striscia di
  identificazione. Nessun comportamento è cambiato, quindi un confronto fra le
  due pipeline resta significativo;
- `src/App.tsx` — solo la composizione delle rotte;
- `src/routes.ts` — i percorsi come costanti.

La striscia in testa alla rotta legacy dichiara `LEGACY V3 DETERMINISTIC` e
nomina il repository letto.

## 4. Componenti ancora riutilizzati dalla vista storica

Tutti raggiungibili solo da `LegacyV3Console`:

`InputForm`, `V3RunForm`, `V3EvidenceView`, `ReportView`, `StructuredData`,
`JudgePanel`, `ArchitectureComparison`, `KnowledgeGraph3D` (via
`StructuredData`), `comparisonRequest.ts`, `dossierSections.ts`.

**Nessun componente è diventato irraggiungibile con la separazione**, quindi
nessuna cancellazione è stata fatta. Rimuovere qualcosa avrebbe alterato la
vista storica, che serve proprio come termine di paragone. Non restano
compatibility shim: la separazione è per rotta, non per adattatori.

## 5. Terminologia

Nella rotta nuova non compare, e un test lo verifica sull'albero renderizzato
(`src/App.test.tsx`):

`qualified_claim_repository`, `Qualified Claim`, `Parent GraphEvidenceRecord`,
`Evidenze principali`, `Applicabilità non valutata separatamente`.

Al loro posto: `GraphCandidateAssertion`, `Graph-derived direction`,
`Document support`, `Author Context`, `Validated Quote`, `Deterministic Status`,
`Research Dossier`. Ogni candidate del grafo porta il badge `GRAPH-DERIVED` e la
riga «non è ancora evidenza documentale».

`PRIMARY_BUCKET` resta il nome del bucket prodotto dal backend, con accanto la
precisazione che è una classificazione interna di evidenza e non una
raccomandazione terapeutica. Rinominarlo nella UI avrebbe fatto divergere
l'etichetta dal valore che il backend emette e che compare nel ledger.

## 6. `[object Object]`

Origine del difetto: `String(value)` e l'interpolazione in template su valori
non primitivi. Punti corretti nella rotta nuova:

| Punto | Difetto |
|---|---|
| `StageInspector` | un unico blocco JSON per ogni stage; nessuna resa strutturata |
| `ProvenanceTree.refToText` | `JSON.stringify` su una riga per la voce di dossier |
| `SupervisorPanel` | `` `${key}: ${String(val)}` `` su `Record<string, unknown>` |

Sostituiti da `research/values/StructuredValue.tsx`, che decide dalla forma:
primitiva → testo, enum → badge, array di primitive → chip, array di oggetti →
tabella, oggetto → coppie chiave/valore, ricorsivamente, con JSON formattato
oltre il quarto livello. `null` legge «Non disponibile» e un array vuoto
«Nessun elemento», così assente e vuoto restano distinguibili.

`values/testing.ts` espone `expectNoObjectObject`, usata dai test unitari e
dallo script di browser.

I due `String(...)` residui in `V3EvidenceView.tsx` (righe 44 e 351) **non sono
stati toccati**: appartengono alla vista storica, che è stata spostata e non
riscritta.

## 7. Modifiche al backend

Tre, tutte a supporto di ciò che la UI doveva poter mostrare.

**`determinism/check_origin.py`.** Lo stage 11 emetteva una support mask di
quattro assi e una nota in prosa. Ora ogni controllo dichiara `source`
(`COMPUTED_HERE`, `INHERITED_VERIFIED_RESULT`, `NOT_IMPLEMENTED`,
`NOT_APPLICABLE`), `source_stage`, `result`, `reason_code` e `version`.
`disease` e `biomarker` risultano ereditati da `stage_5_kg_retrieval`, dove la
candidate è stata ammessa proprio perché quel match passava; `intervention` e
`direction` sono gli unici decisi allo stage 11. I sei controlli previsti dal
design e non implementati restano elencati come `NOT_IMPLEMENTED`, e non possono
dichiarare uno stage di origine.

**`GET /runs/{id}/provenance`.** La catena si fermava a `GATE_AND_STATUS` e
saltava il punto in cui tocca un documento. Ora attraversa `CASE_CONTEXT`,
`GRAPH_CANDIDATE_ASSERTION`, `DOCUMENT`, `SOURCE_UNIT`, `AUTHOR_QUOTE`,
`ENRICHMENT_VALIDATION`, `DETERMINISTIC_CHECK`, `DOSSIER_ITEM`, separando le
quote accettate da quelle rigettate e dalle astensioni. Senza quote accettata la
candidate è marcata `PARENT_LEVEL_ONLY`.

**`run_store.py`.** Passava `source_units_by_id={}` mentre l'indice era
disponibile, così lo stage 7 mostrava solo identificativi: un'unità esistente
era indistinguibile da una non risolta. Ora l'indice viene caricato — 3402 voci
con `unit_type`, sezione, offset, pagina e `content_hash`, e per costruzione
nessun testo. **Non altera alcuna decisione**:
`select_papers_for_association` ammette un bundle solo se una sua unità ha `text`
non vuoto, campo che l'indice non ha, quindi l'esclusione per
`TEXT_NOT_AVAILABLE_IN_CACHE` resta invariata e il validatore è intatto.
Verificato: `CASE-1` seleziona ancora esattamente un paper.

Nessun endpoint preesistente è stato modificato. `/api/v1/v3/retrieve` è ancora
registrato e un test lo verifica.

## 8. Casi eseguiti dalla UI

Nessun mock. Esiti reali, raccolti dal backend dopo l'esecuzione dalla rotta
nuova.

| Caso | Run | Enricher | Validazione | Provenienza |
|---|---|---|---|---|
| CASE-1 therapy evaluation | COMPLETED | QUOTE | `ENRICHMENT_V2_ACCEPTED` | DOCUMENT_GROUNDED |
| CASE-2 therapy discovery | COMPLETED | QUOTE, QUOTE | `REJECTED_QUOTE_NOT_FOUND`, `ENRICHMENT_V2_ACCEPTED` | DOCUMENT_GROUNDED |
| CASE-3 partial context | COMPLETED | ABSTAIN, ABSTAIN | `..._ABSTAINED_WITH_INCONSISTENT_FIELDS`, `..._ABSTAINED` | PARENT_LEVEL_ONLY |
| CASE-4 contradicted/resistance | COMPLETED | ABSTAIN, ABSTAIN | `..._ABSTAINED`, `..._ABSTAINED_WITH_INCONSISTENT_FIELDS` | PARENT_LEVEL_ONLY |
| CASE-5 no match | STOPPED · `RETRIEVAL_NO_MATCH` | mai chiamato | — | nessuna catena |

La QUOTE accettata di CASE-1 è quella già osservata nel pilot:

> patients with mCRC bearing KRAS mutations are clinically resistant to therapy
> with panitumumab or cetuximab.

`CASE-4` mostra il comportamento richiesto: la candidate asserisce
Sensitivity/Response, l'enricher si astiene, e la pipeline **non** promuove il
caso a esito positivo.

`CASE-2` è il solo caso in cui coesistono una quote accettata e una rigettata:
la rigettata resta visibile nello stage 10 e nella catena, marcata come non
entrante nel dossier.

Screenshot in `docs/verifiable_pipeline/screenshots/`, prodotti da
`scripts/e2e_supervisor_ui.py`.

## 9. Limitazioni residue

**Gli stage 8-10 rigiocano artefatti congelati.** La cache documentale non è
disponibile (`document_cache_available: false`), e senza testo delle SourceUnit
la selezione escluderebbe ogni paper: la pipeline produrrebbe zero citazioni, un
esito tecnicamente corretto che rappresenterebbe male il sistema. Gli artefatti
rigiocati sono **risposte reali del modello registrate al commit `6ee64c5`**,
con transport, quote, `source_unit_id`, prompt version, token e latenza — non
sono mock. Ogni stage rigiocato porta il badge `REPLAY` nella UI e
`replayed: true` nel payload. Gli stage 1-5 e 11-13 sono eseguiti, non
rigiocati.

**Il percorso free-text è LIVE ma non arriva a una citazione.** Un testo inedito
fa chiamare davvero il parser; gli stage documentali, privi di cache, non
selezionano paper. La UI lo dichiara prima dell'avvio, non dopo.

**Gli stage 14 e 15 non esistono.** `DOSSIER_NARRATION` e
`NARRATIVE_VERIFICATION` sono nel contratto e privi di implementazione. Restano
`SKIPPED` permanenti con reason code `NOT_IMPLEMENTED`; `PipelineStage` rifiuta
in costruzione qualunque altro stato per quei due.

**Sei controlli deterministici non sono implementati:** `source_gate`,
`provenance_gate`, `completeness`, `negation`, `contradiction_gate`, `score`.
Sono elencati come tali, non nascosti.

**Le run non sopravvivono a un riavvio del backend.** `RunStore` è in memoria; il
ledger degli eventi è su disco, quindi la trace resta ispezionabile, ma
`GET /runs/{id}` risponde 404 dopo un riavvio. Un refresh della pagina a
processo vivo ricarica correttamente snapshot ed eventi.

**`CASECONTEXT_MISMATCH` non è raggiungibile dai casi dimostrativi.** `CASE-5`
fabbrica un gene inesistente, ma il verificatore lo trova davvero nel testo — il
parser lo ha estratto fedelmente — quindi la run si ferma più a valle su
`RETRIEVAL_NO_MATCH`. Il ramo è coperto da un test dell'orchestratore con un
parser che afferma qualcosa di assente dal testo.

**CORS.** `CORS_ORIGINS` elenca le porte 5173 e 5174. Servire il frontend
altrove richiede di estenderlo, altrimenti la console mostra «Backend non
raggiungibile» — che è il comportamento voluto, ma la causa è di configurazione.

## 10. Verifica

- backend: 226 test (`pytest backend/research_pipeline/tests/`);
- frontend: 149 test (`npm test`), typecheck pulito;
- browser: 5 casi, 0 problemi (`python scripts/e2e_supervisor_ui.py`).

Lo script di browser controlla, oltre agli esiti: assenza di `[object Object]`
in ogni stage e in ogni tab, assenza della terminologia legacy, presenza degli
otto livelli della catena, e che un refresh non perda la trace.
