# Protocol Amendment A01 — Operational Scenario Bindings and Isolated Cache Initialization

    amendment_id            : mtb-graphrag-final-evaluation/1.1-A01
    parent_protocol_version : mtb-graphrag-final-evaluation/1.1
    parent_protocol_sha256  : 83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889
    parent_freeze_commit    : 7b0b396b10d10794ac802325f8e7e2ff5ce33e28
    runtime_commit          : 3d2251f82a586535f79f3d0b3725c16330c365ba
    created                 : 2026-08-10
    frozen                  : false — in attesa di review umana dell'emendamento

Questo emendamento è **append-only**. Non modifica un solo byte del protocollo
1.1 congelato: `protocol_sha256` resta `83fcf870…` e resta verificabile.

## Cosa cambia, e cosa no

L'A01 **non cambia che cosa viene misurato**. La §22 del protocollo padre
elenca nove scenari operativi e ne fissa la semantica; quelle definizioni
restano intatte.

L'A01 specifica soltanto **su quale istanza predichiarata** e **con quale stato
iniziale di cache** ciascuno scenario viene eseguito. È la chiusura di un grado
di libertà, non un cambiamento di oggetto.

## Perché serve

Il pre-flight, eseguito dopo il freeze ma **prima di qualunque risultato
finale**, ha rilevato che il protocollo nomina i nove scenari senza vincolarli
a un identificatore:

| Scenario | Rilievo del pre-flight |
|---|---|
| A `cache_hit` | identifier non vincolato |
| B `cache_miss_success` | identifier non vincolato |
| C `pmid_only_to_pmcid` | identifier non vincolato |
| D `pmc_fulltext` | identifier non vincolato |
| E `pmc_unavailable_abstract_degradation` | fixture disponibile |
| F `unseen_document` | fixture disponibile |
| G `document_unavailable` | identifier non vincolato |
| H `parser_failure_fixture` | **fixture non materializzata** |
| I `selector_failure_fixture` | **fixture non materializzata** |

Senza questi vincoli l'esecutore sceglierebbe l'istanza dopo aver visto lo
stato della cache. È esattamente il grado di libertà che il freeze doveva
chiudere.

    final_results_observed_before_amendment = false
    final_runs_executed_before_amendment    = false

## Principio di selezione

Nessuna run è stata eseguita per produrre questo emendamento. Gli
identificatori derivano esclusivamente da:

- artefatti storici prodotti a `f52bbf5`, prima della final evaluation;
- corpus e manifest già congelati;
- definizioni normative già sigillate nel protocollo padre.

Per ogni scenario l'insieme eleggibile è elencato per intero e ordinato; la
selezione applica meccanicamente **SELECT FIRST ELIGIBLE**, con
`selection_index = 0` registrato. Non c'è discrezionalità da esercitare.

Vietato — e non usato — come criterio: output del runtime finale, esiti
osservati, latenza, qualità narrativa, decisioni di Gemma, ranking, stato
canonico prodotto. Lo stato corrente di `data_cache/` è stato letto solo per
verificare che nessuno scenario fosse già contaminato, **mai** per scegliere.

## I nove binding

| # | Scenario | Istanza vincolata | Eleggibili | Fonte |
|---|---|---|---|---|
| A | `cache_hit` | `pmid:15705718` · caso `GCA-0000980ba01970f893f8e4d7` | 17 | PubMed abstract nel corpus congelato |
| B | `cache_miss_success` | `pmid:24088390` → `pmcid:PMC4157820` · caso `GCA-0101aa9c8f708d6f8dd74be0` | 1 | `cache_miss_results.jsonl` |
| C | `pmid_only_to_pmcid` | `pmid:24088390` → `PMC4157820` | 1 | `pmc_resolution_results.jsonl` |
| D | `pmc_fulltext` | `pmcid:PMC4157820` | 1 | `pmc_resolution_results.jsonl` |
| E | `pmc_unavailable_abstract_degradation` | `pmid:23724867` → `PMC4081656` | 1 | `abstract_fallback_results.jsonl` |
| F | `unseen_document` | `pmid:24088390` → `PMC4157820` | 1 | `unseen_document_e2e.json` |
| G | `document_unavailable` | `pmid:00000000` | 1 | `document_unavailable_results.jsonl` |
| H | `parser_failure_fixture` | `FIX-PARSER-FAILED-01` | — | `failure_taxonomy.json` |
| I | `selector_failure_fixture` | `FIX-SELECTOR-FAILED-01` | — | `failure_taxonomy.json` |

### Due decisioni che hanno richiesto approvazione umana

**A01-D1 — scenario A.** La human review ha ristretto la classe sorgente a
PubMed abstract. Dai 43 documenti autorizzati sono stati filtrati quelli
`EXPECTED_AVAILABLE` con source/document type PubMed abstract, payload presente,
parser-readable e testo utilizzabile. I 17 `document_id` eleggibili sono stati
ordinati lessicograficamente e l'indice 0 è `pmid:15705718`. Il risultato non è
stato hardcodificato prima dell'applicazione della regola. La proprietà resta
`CACHE HIT`: target presente nella cache effimera prima della run,
`network_fetch_count = 0`, risoluzione riuscita e prosecuzione normale ammessa.

**A01-D2 — scenari H e I.** H resta invariato. Per I, la human review ha
richiesto una reachability analysis statica prima di accettare la fixture. Al
runtime `3d2251f`, `SOURCEUNIT_SELECTION_FAILED` è
`NATURALLY_REACHABLE_FROM_INPUT_STATE`: `select()` conserva solo unità con
`score_total > min_score` (default `0.0`); il live adapter non seleziona il paper
quando `selected_source_unit_ids` è vuoto; `run_case()` imposta
`selection_failed` se l'associazione ha `available_bundles` ma nessun
`selected_papers`, quindi termina lo stage 8 con il reason code. La fixture I
dichiara candidate, record resolved, bundle disponibile e una SourceUnit con
testo non vuoto ma score totale esattamente zero. Deriva dalla branch condition,
non da un output osservato.

### Reachability statica dello scenario I

- **FILE / FUNCTION:** `backend/research_pipeline/orchestrator.py::run_case`.
- **LINE / BRANCH:** righe 686-687 e 770-779 al runtime congelato; il ramo
  upstream del selector è in `experimental/sourceunit_selector.py::select`,
  righe 414-447, e il live adapter in
  `retrieval/live_sourceunit_selection.py::select_live_papers_for_association`,
  righe 18-113.
- **BOOLEAN CONDITION:** `canonical and association.get("available_bundles")
  and not selection.get("selected_papers")`; dopo il loop,
  `canonical and selection_failed`.
- **INPUT STATE REQUIRED:** un record resolved coerente con candidate e
  documento; almeno una SourceUnit con testo; tutte le unità hanno
  `score_total <= 0.0`; `selected_source_unit_ids = []`; available bundle
  presente.
- **UPSTREAM PRECONDITIONS:** stage 6 risolto; stage 7 non prende
  `PARSER_FAILED`; provenance candidate/document coerente; nessun token o feature
  della candidate compare nel testo della fixture.
- **DOWNSTREAM EFFECT:** stage 8 `FAILED`, finalizzazione
  `SOURCEUNIT_SELECTION_FAILED`, nessuna chiamata agli stage 9, 10, 13 e 14.

L'evidenza congelata `SOURCEUNIT_SELECTOR_INDEPENDENT_20` separa esplicitamente
la rilevanza gold dalla selezione: gli 11 casi zero-direct hanno comunque una
selezione in 11/11. Quindi zero-direct non implica selector failure. La fixture
I non usa la sola "non pertinenza" come giustificazione: richiede il predicato
reale `score_total > 0.0` falso per ogni SourceUnit.

## Inizializzazione isolata della cache

La valutazione operativa **non usa una cache mutabile condivisa**. Ogni
scenario parte da una directory nuova:

    operational_cache_A/ … operational_cache_I/

seminata dalla baseline logica `AUTHORIZED_DOCUMENT_CACHE_43` copiando i soli
`include_ids` e omettendo sempre gli `exclude_ids`. Nessuno scenario legge
l'output di un altro, nessuno modifica la baseline, ciascuno conserva la
propria cache come artefatto grezzo.

Ne discende una proprietà che vale la pena enunciare: **l'ordine di esecuzione
non può determinare l'esito operativo**. Cade quindi il vincolo, altrimenti
necessario, di eseguire per primo lo scenario del documento inedito.

Le directory verranno create durante l'esecuzione futura. **Non esistono ora**,
e la cache reale non è stata toccata.

## Classificazione scientifica

I nove scenari sono **OPERATIONAL CONFORMANCE / PROPERTY TESTS**: verifiche
pre-specificate di capacità e semantica di fallimento del runtime.

B and F intentionally reuse the same document identity under isolated cache
states because they test different operational properties.

Operational scenarios are property tests and must not be interpreted as
statistically independent observations.

Non sono, e non vanno presentati come: stima non distorta di prestazione
clinica, benchmark di generalizzazione, campione di accuratezza clinica.

## Identità della final evaluation

Da qui in poi l'identità del protocollo di valutazione è la coppia:

    parent protocol_sha256  +  amendment A01 sha256

Il primo non cambia. Il secondo è in `amendment_hash.json` e sigilla soltanto i
file normativi dell'A01.

## Runner ancora da scrivere

L'A01 vincola le istanze, non implementa l'esecuzione. Restano da scrivere,
dopo l'approvazione dei binding: il runner degli scenari operativi con
seeding isolato della cache, i runner di RQ3 e delle ablation, quello delle
ripetizioni di affidabilità e l'aggregatore di latenza.
