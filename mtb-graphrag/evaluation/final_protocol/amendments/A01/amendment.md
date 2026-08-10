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
| A | `cache_hit` | `nct:NCT02624973` · caso `GCA-0000b1703877453334da0001` | 40 | corpus congelato |
| B | `cache_miss_success` | `pmid:24088390` → `pmcid:PMC4157820` · caso `GCA-0101aa9c8f708d6f8dd74be0` | 1 | `cache_miss_results.jsonl` |
| C | `pmid_only_to_pmcid` | `pmid:24088390` → `PMC4157820` | 1 | `pmc_resolution_results.jsonl` |
| D | `pmc_fulltext` | `pmcid:PMC4157820` | 1 | `pmc_resolution_results.jsonl` |
| E | `pmc_unavailable_abstract_degradation` | `pmid:23724867` → `PMC4081656` | 1 | `abstract_fallback_results.jsonl` |
| F | `unseen_document` | `pmid:24088390` → `PMC4157820` | 1 | `unseen_document_e2e.json` |
| G | `document_unavailable` | `pmid:00000000` | 1 | `document_unavailable_results.jsonl` |
| H | `parser_failure_fixture` | `FIX-PARSER-FAILED-01` | — | `failure_taxonomy.json` |
| I | `selector_failure_fixture` | `FIX-SELECTOR-FAILED-01` | — | `failure_taxonomy.json` |

### Due decisioni che hanno richiesto approvazione umana

**A01-D1 — scenario A.** La regola di selezione conteneva un conflitto interno:
l'artefatto storico indica `pmcid:PMC4157820`, che **non appartiene** ai 43
documenti congelati. Il contratto di cache pretende però `fetch_count = 0`, e
un documento fuori dalla baseline non è seminabile senza una fetch — che
renderebbe l'osservabile impossibile. Prevale l'appartenenza al corpus
congelato: A si vincola al primo dei 40 documenti seminabili in ordine
lessicografico. Approvato da Paolo Pangallo il 2026-08-10.

**A01-D2 — scenari H e I.** L'istruzione era di promuovere una fixture
preesistente. Non ne esiste alcuna: `PARSER_FAILED` e
`SOURCEUNIT_SELECTION_FAILED` sono implementati e raggiungibili nel runtime, ma
nessun test, probe o artefatto li esercitava. Le fixture sono quindi **derivate
dalle definizioni già congelate** in `failure_taxonomy.json` — non da un
comportamento osservato — e sono dichiarate **nuove**, non promosse. Approvato
da Paolo Pangallo il 2026-08-10.

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
