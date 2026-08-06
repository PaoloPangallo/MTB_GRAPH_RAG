# Audit della catena documentale — prima di rendere LIVE la pipeline

Stato rilevato al commit `5533010`, branch `feature/v3-verifiable-pipeline-ui`.

Questo documento risponde alle domande poste dalla sezione 3 del mandato **prima**
di qualunque modifica al codice. Distingue cinque cose che il runtime attuale
confonde: cache documentale, manifest, indice delle SourceUnit, testo
effettivamente disponibile, artefatti LLM registrati.

---

## 1. Sintesi

| Domanda | Risposta |
|---|---|
| La cache documentale esiste? | Sì, ma **fuori da questo worktree** |
| Le SourceUnit con `exact_text` sono ricostruibili? | **Sì — 3402 su 3402, hash identici** |
| La pipeline le usa oggi? | **No** |
| Gemma è raggiungibile? | **Sì**, `gemma4:cloud` via Ollama Cloud |
| Il percorso LIVE funziona oggi? | **No** — due difetti bloccanti, sotto |
| Esiste un fallback silenzioso LIVE→REPLAY? | **Sì**, `research_routes.py:108` |

La conclusione operativa: **una run completamente LIVE è tecnicamente possibile**,
ma non con il codice attuale. Servono quattro correzioni, nessuna delle quali
indebolisce un controllo.

---

## 2. Cache documentale

### 2.1 Dove si trova

Risolta da `data_access.cache_root()`:

```python
os.getenv("RESEARCH_PIPELINE_CACHE_ROOT") or data_root() / "data_cache/document_grounding"
```

`AuthorizedDocumentCache` ha un **secondo** meccanismo, indipendente e non
allineato — `documents/authorized_cache.py:41`:

```python
os.environ.get("DOCUMENT_GROUNDING_CACHE", "data_cache/document_grounding")
```

Quest'ultimo è relativo alla **directory di lavoro del processo**, non alla
radice del repository. Due variabili d'ambiente diverse per la stessa cache è di
per sé un difetto: `data_access` passa sempre `root=` esplicito, quindi oggi
`DOCUMENT_GROUNDING_CACHE` è di fatto morto sul percorso del runtime, ma resta
attivo per chiunque istanzi la classe direttamente.

### 2.2 Presenza effettiva

Nel worktree principale la cache **non esiste**. È presente nel worktree del
pilot:

```
C:/Users/paolo/AppData/Local/Temp/codex-v3-document-grounded-claims/
  mtb-graphrag/data_cache/document_grounding/
```

È ignorata da git — correttamente: contiene testo integrale di terzi.

### 2.3 Contenuto

| Sottocartella | File | Natura |
|---|---:|---|
| `pubmed/metadata/` | 17 `.json` | ESummary — **solo metadata** |
| `pubmed/abstracts/` | 17 `.xml` | EFetch — **contiene testo** |
| `pmc/xml/` | 11 `.xml` | JATS full text — **contiene testo** |
| `clinical_trials/` | 12 `.json` | ClinicalTrials.gov v2 — **contiene testo** |
| `local_pdf/` | 0 | vuota |
| `manifests/documents.jsonl` | 1 | manifest interno alla cache |
| `errors/` | 0 | vuota |

40 documenti con contenuto testuale. Nessun PDF, nessun articolo caricato a mano.

### 2.4 Due manifest distinti — da non confondere

- **Manifest della cache**: `<cache>/manifests/documents.jsonl`, append-only,
  scritto da `AuthorizedDocumentCache._record()` durante la risoluzione di rete.
  Non versionato.
- **Manifest committato**: `benchmarks/mtb_evidence/document_grounded_claims/
  authorized_document_cache_pilot/document_manifest.jsonl`, 43 righe, versionato.
  È lo snapshot congelato usato dal runtime via `data_access.document_manifest_path()`.

Il runtime legge **il secondo**. Il primo esiste solo dentro la cache.

Disponibilità dichiarata nel manifest committato:

| `availability` | Righe | Testo? |
|---|---:|---|
| `ABSTRACT_AVAILABLE` | 17 | sì |
| `PMC_XML_AVAILABLE` | 11 | sì |
| `METADATA_ONLY` | 12 | sì (trial registry) |
| `PMC_RESOLUTION_FAILED` | 3 | **no** |

40 righe su 43 hanno un `local_cache_path` che risolve a un file esistente nella
cache. Le 3 restanti sono genuinamente non disponibili e devono restare tali:
sono il caso `DOCUMENT_UNAVAILABLE` reale, non simulato.

---

## 3. SourceUnit: indice contro materializzazione

Sono due cose diverse e il runtime attuale usa quella sbagliata.

### 3.1 Indice committato — **senza testo**

`authorized_document_cache_pilot/source_unit_index.jsonl`, 3402 righe.
Campi: `source_unit_id`, `document_id`, `unit_type`, `section`,
`paragraph_index`, `sentence_index`, `char_start`, `char_end`, `page`,
`content_hash`, metadati del parser.

**Nessun campo `text`.** È deliberato: è ciò che l'API può esporre.

### 3.2 Materializzazione dalla cache — **con testo**

`data_access.load_source_units(documents)` → `AuthorizedDocumentCache
.source_units_for_record()`, con `network=False`. Instrada per `availability`:

| Availability | Parser | Unit type prodotti |
|---|---|---|
| `ABSTRACT_AVAILABLE` | `PubMedAbstractParser` | `ABSTRACT_SENTENCE`, titolo |
| `PMC_XML_AVAILABLE` | `JatsXmlParser` | paragrafi/sezioni JATS |
| `LOCAL_PDF_AVAILABLE` | `PdfDocumentParser` | pagine |
| `nct:*` + `local_cache_path` | costruzione diretta | `TRIAL_TITLE`, `BRIEF_SUMMARY`, `DETAILED_DESCRIPTION`, `CONDITION`, `INTERVENTION` |

### 3.3 Verifica eseguita

Ri-parsando le 43 righe del manifest committato contro la cache del pilot:

```
rebuilt source units:            3402
with non-empty text:             3402
committed index size:            3402
id overlap rebuilt vs index:     3402
```

Su `SU-6e4d5a52c9be05f545487ad0` (l'unità della quote accettata di CASE-1):

```
document:      pmid:19223544
unit_type:     ABSTRACT_SENTENCE
content_hash:  6e4d5a52c9be05f5…   (identico all'indice committato)
text length:   203
quote registrata letteralmente presente:  True
```

**La ricostruzione è esatta.** `source_unit_id` è derivato dall'hash del
contenuto (`SourceUnit.from_document_text`), quindi la coincidenza degli ID è
essa stessa la prova che il testo ri-parsato è byte-identico a quello del pilot.

### 3.4 Cosa usa il runtime oggi

`run_store._execute()` passa:

```python
source_units_by_id=da.load_source_unit_index()      # ← indice, senza testo
```

`da.load_source_units()` — la funzione che il testo lo carica davvero — **non è
mai chiamata da nessun percorso di esecuzione**. Ha solo test.

Conseguenza a catena: `paper_selection.select_papers_for_association()` ammette
un bundle solo se almeno una unità ha `text` non vuoto (riga 36). Con l'indice
nudo la condizione è falsa per ogni bundle, quindi **ogni paper viene escluso con
`TEXT_NOT_AVAILABLE_IN_CACHE`**, zero paper raggiungono Gemma, e il validatore
rigetterebbe ogni quote con `QUOTE_NOT_LITERAL_IN_SOURCE_UNIT`.

È esattamente la ragione per cui `replay.py` esiste, ed è documentata nel suo
docstring. Non è un difetto nascosto: è una scelta consapevole che ora va
rimossa alla radice invece che aggirata.

---

## 4. Document availability e selezione dei paper

**Availability** oggi non viene determinata durante la run. Lo stage 6
(`orchestrator.py:330-341`) non risolve nulla: enumera i `document_id` già
presenti nei bundle del retrieval e li marca `replayed: True` incondizionatamente
— anche quando la cache è disponibile e la risoluzione sarebbe possibile.

Lo stage 7 fa lo stesso: proietta i locatori dall'indice e marca `replayed: True`.

**Paper selection** ha una logica reale e corretta (`paper_selection.py`): 9
criteri ordinati, massimo 2 paper, deduplicazione per `document_id`, ranking per
`bundle_type`. Il tetto di 4 SourceUnit per documento è applicato a monte, in
`kg_retrieval.retrieve()` (`MAX_SOURCE_UNITS_PER_DOCUMENT = 4`, riga 139). Questa
logica non ha bisogno di modifiche: ha bisogno di **input con testo**.

---

## 5. Come il runtime decide fra LIVE e REPLAY

Un solo punto, `backend/api/research_routes.py:108`:

```python
use_replay = replay.has_frozen_case(case_id)
```

Cioè: **se esistono artefatti congelati per quel `case_id`, la run è replay.**
Tutti e 5 i casi dimostrativi hanno artefatti congelati, quindi ogni run avviata
dalla Supervisor UI è oggi REPLAY. Il chiamante non può chiedere LIVE: non
esiste un parametro per farlo.

`execution_mode` viene restituito nella risposta di `POST /runs` ma **non è
persistito né sulla run né sui suoi stage**, e non compare nel ledger. Chi legge
`GET /runs/{id}` in un secondo momento non ha modo di sapere in quale modalità la
run sia stata eseguita, se non deducendolo dai `replayed: true` sparsi nei
preview.

Cosa viene rigiocato in modalità replay (`run_store._providers`):

| Stage | Provider replay | Origine |
|---|---|---|
| 2 — parser | `replay.parser_fn` | `casecontext_outputs.jsonl` |
| 8 — paper selection | `replay.selection_fn` | `paper_selection_results.jsonl` |
| 9 — enricher | `replay.enricher_fn` | `paper_context_enricher_v2_runs.jsonl` (7 chiamate) |
| 10 — validazione | `replay.validation_fn` | `paper_context_enricher_v2_validation_results.jsonl` |

Stage 6 e 7 sono marcati `replayed` **in entrambe le modalità**, perché la marcatura
è cablata nell'orchestratore e non deriva dalla modalità della run.

---

## 6. Invocazione di Gemma

`enricher_v2.call_enricher_v2` → `transport.post_with_infra_retry` →

```python
OPENAI_COMPAT_ENDPOINT = "http://localhost:11434/v1/chat/completions"   # transport.py:19
MODEL = "gemma4:cloud"                                                  # transport.py:20
```

Entrambi **cablati**, senza header di autorizzazione.

`llm_config.py` esiste, legge `OLLAMA_BASE_URL`/`OLLAMA_API_KEY`, costruisce
l'header `Bearer` e solleva `MissingLLMCredentials` invece di degradare — ma
**nessun modulo di trasporto lo importa**. È configurazione scritta e non
collegata. `research_routes.create_run` la invoca solo come *check* prima di
avviare una run non-replay; la chiamata vera ignora l'esito di quel check.

Verifica dell'ambiente:

- `.env` → `OLLAMA_API_KEY=` **vuota**
- nessun processo in ascolto su `11434` all'inizio della sessione
- Ollama 0.18.3 installato; avviandolo, `gemma4:cloud` **risolve** via
  `POST /api/show` con capability `tools`

Quindi il percorso praticabile è quello che il pilot ha già usato: l'app Ollama
locale come proxy autenticato verso Ollama Cloud. L'endpoint cablato è corretto
per questo ambiente; è la sua **non configurabilità** il problema, non il valore.

Prompt e transport v2.0 sono in `enrichment/prompt_v2.py` e
`enrichment/transport_v2.py`. Parametri già conformi al mandato:
`temperature=0`, `top_p=1.0`, `stream=False`, `max_tokens=1024`,
`tool_choice` forzato su `submit_paper_context_enrichment_v2`.
`think` **non è impostato** — va aggiunto esplicitamente.

---

## 7. Difetto bloccante: enricher v2 contro validatore v1

`orchestrator.run_case`, riga 225, quando `validate_fn` non è iniettato:

```python
enrichment_validator.validate_enrichment(transport, enrichment, ...)   # validator.py — v1
```

Ma il chiamante è `enricher_v2`, che produce:

- `transport_result = "V2_TRANSPORT_VALID"`
- campi `decision` / `abstention_reason`

mentre il validatore v1 (`validator.py:25`) apre con:

```python
if transport_result != "FORCED_TOOL_VALID":
    return _result("REJECTED_TRANSPORT", ...)
```

**Ogni enrichment v2 in modalità LIVE viene quindi rigettato al primo controllo**,
prima di qualunque verifica semantica. Il v1 cerca inoltre `enrichment["abstain"]`
e `enrichment["drug"]`, campi che il contratto v2 non ha.

`PaperContextEnrichmentV2Validator` (`validator_v2.py`) è implementato,
completo e testato — ma **non è raggiungibile da nessun percorso di esecuzione**:
in replay l'esito arriva dal file congelato, in live si ferma sul v1.

Questo è il difetto che rende il percorso LIVE non solo inutilizzato ma
**inutilizzabile**, ed è la ragione per cui non è mai stato notato: in replay non
si manifesta.

---

## 8. Persistenza

`RunStore` è un `dict` in memoria (`run_store.py:68`). Il ledger
(`data/research_pipeline_events.sqlite3`) è su disco e append-only con hash-chain,
ma:

- `GET /runs/{id}` legge `RunStore`, non il ledger → **404 dopo un riavvio**;
- `GET /runs/{id}/events` legge il ledger, ma passa prima da `_handle_or_404`,
  quindi **404 anche lui**;
- gli stessi eventi contengono già tutto il necessario per ricostruire la vista
  (`REPLAYABLE_EVENT_TYPES` lo dichiara esplicitamente), ma nessuno lo fa.

La fonte canonica esiste già ed è verificabile. Manca soltanto la proiezione.

---

## 9. Classificazione dei componenti

### Live oggi

| Componente | Nota |
|---|---|
| CaseContext Match Verifier | deterministico, sempre eseguito |
| KG retrieval | legge `candidates.jsonl` + `evidence_bundles.jsonl` a ogni run |
| Deterministic gates | sempre eseguiti |
| Status classification | sempre eseguita |
| Dossier builder | sempre ricostruito |

### Replay oggi

| Componente | Sostituibile con LIVE? |
|---|---|
| CaseContext Parser | sì — serve Gemma raggiungibile |
| Document resolution | sì — serve la cache collegata |
| SourceUnit | sì — `load_source_units()` già scritta |
| Paper selection | sì — automatico appena le unità hanno testo |
| Paper Context Enricher | sì — serve Gemma + validatore v2 |
| Enrichment validation | sì — `validator_v2` da collegare |

### Artefatti LLM registrati

`benchmarks/mtb_evidence/end_to_end_pipeline_pilot/`, commit `6ee64c5`:

- `casecontext_outputs.jsonl` — output del parser per i 5 casi
- `paper_context_enricher_v2_runs.jsonl` — **7 chiamate reali**: 3 QUOTE, 4 ABSTAIN
- `paper_context_enricher_v2_validation_results.jsonl` — 2 accettate, 1 rigettata
  (`QUOTE_NOT_LITERAL_IN_SOURCE_UNIT`), 2 astensioni pulite, 2 astensioni con
  campi incoerenti
- `paper_selection_results.jsonl`, `retrieval_results.jsonl`, `dossier_previews.jsonl`

Non sono mock: sono risposte reali del modello. Restano validi come REPLAY
esplicito e come termine di paragone — **non** come sostituto di una run LIVE.

---

## 10. Coppia candidate-paper per il Checkpoint A

Dagli artefatti congelati, l'unica quote accettata su un solo paper:

```
case_id:        CASE-1-therapy-evaluation-strong-match
candidate_id:   GCA-008ae3aad1a64c118318ef79
paper_id:       EB-b4c48ba003913f278ff182a6
document_id:    pmid:19223544        (ABSTRACT_BUNDLE, in cache)
source_unit:    SU-6e4d5a52c9be05f545487ad0
esito pilot:    QUOTE → ENRICHMENT_V2_ACCEPTED
```

Il documento è nella cache, le SourceUnit sono ricostruibili, la quote registrata
è letteralmente presente nel testo ri-parsato. Il Checkpoint A userà **lo stesso
caso, candidate, paper e SourceUnit**, con una **nuova** chiamata al modello.

---

## 11. Correzioni necessarie

Nessuna di queste allenta un controllo. Tre sono collegamenti mancanti, una è la
rimozione di un automatismo.

1. **Collegare la cache al runtime** — un solo meccanismo di configurazione,
   validato all'avvio, sola lettura, errore esplicito se assente.
2. **Caricare le SourceUnit con testo** durante la run, invece dell'indice nudo.
   Il testo resta nel backend; l'API continua a esporre solo locatori e hash.
3. **Collegare `validator_v2` all'enricher v2.** Il validatore non viene
   modificato: viene semplicemente raggiunto per la prima volta.
4. **Rendere la modalità un input esplicito**, non una deduzione dalla presenza
   di artefatti. Nessun passaggio automatico LIVE→REPLAY.

Più due estensioni: `execution_mode`/`artifact_origin` per run e stage, e la
proiezione della run dal ledger per sopravvivere al riavvio.

---

## 12. Rischi da sorvegliare

| Rischio | Presidio |
|---|---|
| `exact_text` finisce nel ledger o nell'API | `events.assert_payload_is_publishable`, già attivo e ricorsivo |
| La cache viene committata | resta fuori dal repo; nessun percorso di scrittura nel runtime |
| Un ABSTAIN viene letto come guasto | `ENRICHMENT_V2_ABSTAINED` è esito valido e va reso come tale |
| Il replay viene presentato come live | `artifact_origin` per stage + conteggio `replay_artifacts_used` |
| Superamento del budget di 10 chiamate | budget centralizzato, speso dal chiamante reale |
