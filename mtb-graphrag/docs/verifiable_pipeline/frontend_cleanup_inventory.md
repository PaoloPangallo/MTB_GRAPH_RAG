# Frontend cleanup inventory — Fase A

**Branch:** `feature/v3-verifiable-pipeline-ui`
**Ambito:** `mtb-graphrag/frontend/src` — 24 file, 7.637 righe
**Data:** 2026-08-04

Inventario di sola lettura. **Nessun file è stato modificato o rimosso.** La
rimozione è Fase H e, per vincolo della sezione 25 del prompt, non può precedere
un caso end-to-end visualizzabile nella nuova UI.

## 1. Struttura attuale

Nessun router, nessuno store globale, nessun hook API, nessun hook SSE.
`App.tsx` (707 righe) è simultaneamente entry point, router implicito via
booleani, store e livello di trasporto HTTP.

```
main.tsx (14)
└── App.tsx (707)              15 useState locali; nessun reducer
    ├── ArchitectureComparison (723)   ← ramo alternativo, booleano architectureView
    ├── InputForm (305)
    │   └── onV3Retrieve  ──────────→ handleV3Retrieve   (percorso V3 #1)
    ├── V3RunForm (106)  ───────────→ handleV3Run        (percorso V3 #2)
    ├── V3EvidenceView (418)
    ├── ReportView (144)
    ├── StructuredData (422)
    │   └── KnowledgeGraph3D (672)
    └── JudgePanel (116)
```

Il "routing" è una coppia di booleani: `architectureView` e `compareMode`. Non
esiste deep-link, quindi **nessuno stato è ricostruibile da URL** e un refresh
perde la run. Questo confligge direttamente con il criterio di accettazione
"un refresh non perde la trace" (sezione 22).

## 2. Classificazione per file

| File | Righe | Classe | Motivo |
|---|---:|---|---|
| `main.tsx` | 14 | KEEP | bootstrap neutro |
| `theme.ts` | 136 | REFACTOR | tema MUI slate/blu/teal/ambra/rosso; va riconciliato col design system fornito (§18) |
| `types.ts` | 470 | REFACTOR | contiene tipi V2 e V3 mescolati; i tipi run/stage/event sono MISSING |
| `App.tsx` | 707 | **REPLACE** | entry point, store, trasporto e routing in un solo file; vedi §3 |
| `InputForm.tsx` | 305 | REFACTOR | form condiviso V2/V3; il bottone V3 è un percorso duplicato |
| `V3RunForm.tsx` | 106 | REFACTOR | form V3 esplicito; base per lo Stage 1 Case Input |
| `V3EvidenceView.tsx` | 418 | REFACTOR | unica vista V3; copre bucket/provenance, non gli stage |
| `ArchitectureComparison.tsx` | 723 | RESEARCH_ONLY | confronto V2 deterministico/agentico; vedi §4 |
| `dossierSections.ts` | 61 | RESEARCH_ONLY | usato **solo** da `ArchitectureComparison` |
| `comparisonRequest.ts` | 68 | RESEARCH_ONLY | costruzione richiesta comparison |
| `StructuredData.tsx` | 422 | LEGACY_COMPATIBILITY | rendering dati V2 |
| `KnowledgeGraph3D.tsx` | 672 | RESEARCH_ONLY | vedi §5 — grafo sintetico in `mode=zeroshot` |
| `ReportView.tsx` | 144 | LEGACY_COMPATIBILITY | report narrativo V2 |
| `JudgePanel.tsx` | 116 | RESEARCH_ONLY | LLM-as-judge, strumento di valutazione |
| `App.css`, `index.css`, `assets/` | — | KEEP | |
| 4 file `*.test.*` | 760 | REFACTOR | copertura solo su comparison e V3; vedi §7 |

## 3. `App.tsx` — problemi puntuali con riferimento di riga

### 3.1 Base URL hardcoded — 4 occorrenze (difetto reale)

`API_BASE_URL` è definito a riga 34 leggendo `VITE_API_BASE_URL`, ma **viene
ignorato** da metà delle chiamate:

| Riga | Chiamata | Usa `API_BASE_URL`? |
|---:|---|---|
| 149 | `` fetch(`http://localhost:8000/api/v1/${endpoint}`) `` | **no** |
| 168 | `fetch(API_BASE_URL + '/api/v1/v3/retrieve')` | sì |
| 186 | `` fetch(`${API_BASE_URL}/api/v1/v3/retrieve`) `` | sì |
| 244 | `` fetch(`http://localhost:8000/api/v1/${endpoint}`) `` | **no** |
| 281 | `fetch('http://localhost:8000/api/v1/enrich')` | **no** |
| 303 | `fetch('http://localhost:8000/api/v1/judge')` | **no** |

Anche `KnowledgeGraph3D.tsx:227` hardcoda `http://localhost:8000`.

Conseguenza: la UI funziona solo in locale sulla porta 8000, e la variabile
d'ambiente dà la falsa impressione di essere configurabile. Da correggere in un
client API unico.

### 3.2 Due percorsi V3 concorrenti

`handleV3Run` (riga 164, da `V3RunForm`) e `handleV3Retrieve` (riga 182, dal
bottone in `InputForm.tsx:218-225`) colpiscono **lo stesso endpoint** con
payload costruiti diversamente. Entrambi scrivono `setV3Data`. È la
"duplicazione tra pipeline V2, V3 e pilot" della sezione 4.
Risoluzione prevista: un solo percorso, `V3RunForm`.

### 3.3 Stato non canonico

15 `useState` indipendenti, fra cui `compareResults`, `compareLoadings`,
`compareErrors` come tre `Record` paralleli tenuti in sincrono a mano. Nessun
reducer testabile. La sezione 12 richiede una rappresentazione canonica unica
derivata da snapshot + eventi: oggi **non esiste**.

Da segnalare: riga 45, `const [, setZeroShotData] = useState<ReportResponse | null>(null)`
— lo stato viene scritto e mai letto (getter scartato). Codice morto.

## 4. `ArchitectureComparison` — valutazione corretta del rischio "mock"

`ArchitectureComparison.tsx:556` inizializza `useState<ExecutionMode>('demo')`:
**il default è la modalità demo**, che per dichiarazione dell'endpoint usa
"fixture e client scriptati" e non richiede Neo4j né LLM.

Va però riconosciuto quanto il componente già fa correttamente:

- riga 689 mostra un `<Alert severity="warning">` quando `execution_mode === 'demo'`;
- riga 616 dichiara "La demo mostra il contratto architetturale con una fault
  injection dichiarata";
- riga 679 spiega quali dipendenze richiede il live;
- riga 634 rende la scelta esplicita nel selettore.

Quindi **non** è un caso di "mock presentati come output reali": è una demo
etichettata. La criticità residua è che il *default* è demo, e un osservatore
distratto potrebbe partire da lì. Classificazione **RESEARCH_ONLY**: resta
disponibile come artefatto di ricerca, ma fuori dal flusso principale della
nuova UI.

Nota positiva riusabile: riga 268 espone già un link a
`/api/v1/agent-runs/{run_id}`, cioè **la UI sa già puntare al ledger di una
run**. È il precedente diretto della Audit Mode richiesta dalla sezione 9.F.

## 5. `KnowledgeGraph3D` + `/subgraph`

`KnowledgeGraph3D.tsx:227` chiama `/api/v1/subgraph`. Con `mode=zeroshot`
il backend (`routes.py:108-110`) risponde con `build_zeroshot_subgraph(pmids)`,
cioè **un grafo sintetico costruito per evidenziare l'allucinazione**.

È materiale didattico/di ricerca legittimo, ma è esattamente il tipo di
contenuto che la sezione 4 vuole fuori dal percorso principale: un grafo
generato non deve poter essere confuso con provenance reale.
Classificazione: **RESEARCH_ONLY**.

## 6. Terminologia da correggere (§13)

Verifica testuale sui file non-test. Esito: **nessuna occorrenza** di "AI
recommendation", "clinical recommendation" o "raccomandazione clinica" nella UI.
Su questo il frontend è già conforme.

Mancano invece del tutto i termini richiesti dalla sezione 13 — nessuno di
questi compare nella UI: `CaseContext`, `CaseContext Match`,
`Graph Candidate Assertion`, `Document Resolution`, `Source Unit`,
`Paper Selection`, `Author Context`, `Quote Validation`,
`Deterministic Gates`. Classificazione: **MISSING**, da introdurre con la
nuova UI, non da correggere sull'esistente.

## 7. Test frontend

4 file, 760 righe: `ArchitectureComparison.test.tsx` (403),
`V3EvidenceView.test.tsx` (225), `comparisonRequest.test.ts` (83),
`V3RunForm.test.tsx` (49).

Copertura assente su: `App.tsx`, `InputForm`, `StructuredData`,
`KnowledgeGraph3D`, `ReportView`, `JudgePanel`. Non esiste alcun test di
timeline, evento SSE, deduplicazione, reducer o provenance — coerentemente col
fatto che quelle funzioni non esistono.

Da verificare prima di eseguirli: la spec precedente
(`2026-08-01-v3-pipeline-observability-ui-design.md`) segnalava che il runner
Vitest era bloccato su Windows da `spawn EPERM` in fase di caricamento della
configurazione. Non ho ancora eseguito la suite; lo stato dei test è quindi
**non verificato** e non lo dichiaro passante.

## 8. Cosa manca del tutto (MISSING)

Nessun equivalente esiste per: timeline/stepper di pipeline, stage inspector,
candidate explorer, provenance tree, supervisor mode, "why this result?",
dossier view strutturata, vista eventi, JSON viewer redatto, sezione demo cases,
client SSE con reconnect e deduplicazione, gestione `lastEventId`, stati
empty/loading/error per la run.

## 9. Ordine di rimozione proposto (Fase H, non ora)

1. unificare le chiamate HTTP in un client unico → elimina i 4 hardcoded;
2. rimuovere `handleV3Retrieve` e il bottone V3 di `InputForm` → un solo percorso V3;
3. rimuovere lo stato morto di riga 45;
4. spostare `ArchitectureComparison`, `KnowledgeGraph3D`, `JudgePanel`,
   `dossierSections`, `comparisonRequest` dietro una sezione dichiarata
   "ricerca/storico", non raggiungibile dal flusso principale;
5. solo dopo che un caso end-to-end è visibile nella nuova UI, valutare la
   rimozione definitiva di `ReportView` e `StructuredData`.

Per ogni voce servirà, come richiesto dalla sezione 4: file, motivo,
sostituzione, compatibilità mantenuta, test che dimostra che non serve più.
Quei test **non esistono ancora**, quindi nessuna rimozione è giustificabile
oggi.
