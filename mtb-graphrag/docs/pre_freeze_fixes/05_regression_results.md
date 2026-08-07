# 05 — Regressione

Dati: `evaluation/pre_freeze/full_test_results.json`,
`evaluation/pre_freeze/rq_regression_summary.json`.

## §22 — Suite complete

| Comando | exit | passed | failed | skipped | durata |
|---|:-:|---:|---:|---:|---:|
| `env -u PYTHONPATH pytest -q` | 0 | **3 189** | 0 | 17 | 192 s |
| `npx vitest run --no-file-parallelism` | 0 | **200** | 0 | 0 | 34 s |
| `npm run build` | **0** | — | 0 | — | — |
| `npx tsc -b` | **0** | — | 0 | — | — |
| `python -m evaluation.run_rq4_canonical_runtime` | 0 | 35 casi | 0 | — | — |

Sottotest: **36 890** (36 860 prima + 30 aggiunti).

### Conteggi, verificati per differenza

```
python    3 138 baseline  +  51 nuovi  =  3 189
          19 (ISS-002) + 15 (ISS-001) + 17 (ISS-003) = 51 ✅

frontend    195 baseline  +   5 nuovi  =    200 ✅
```

Nessuna suite è stata saltata. La suite di evaluation (91 test) è inclusa in
`pytest` tramite `testpaths`.

La flakiness preesistente del frontend in esecuzione parallela resta la stessa e
non è stata toccata: `--no-file-parallelism` continua a essere la modalità di
riferimento, come già documentato nell'audit.

## §19 — RQ1: invariato

**Nessun artifact storico è stato modificato.**

```
$ git diff --name-only 0219e0a..HEAD -- \
    evaluation/rq1_graph_candidate_fidelity evaluation/rq2_pmid_associations \
    evaluation/rq3_oncokb_fallback evaluation/rq4_casecontext_robustness \
    evaluation/gca_v3 evaluation/runtime_v3_integration \
    benchmarks evaluation/gold
(nessuna riga)
```

`evaluation/gca_v3/` non è stato rimaterializzato, come richiesto.

**Prova strutturale.** Anziché rieseguire gli script — che avrebbero attivato
ISS-017 e rischiato di sovrascrivere gli artifact — la non-regressione è stata
dimostrata per **chiusura transitiva degli import**:

```
evaluation.run_rq1           raggiunge moduli modificati: NESSUNO
evaluation.run_rq2           raggiunge moduli modificati: NESSUNO
evaluation.run_gca_v3_audit  raggiunge moduli modificati: NESSUNO
```

I quattro moduli modificati (`determinism.gates`, `dossier.builder`,
`orchestrator`, `contracts`) non sono raggiungibili da nessuno dei tre script.
Le metriche RQ1 sono quindi **strutturalmente** inalterate:

```
materialization_precision = 1.0     direction_inversions_graph = 486
materialization_recall    = 1.0     ALTERATION_LOST            = 1091
field_completeness        = 1.0     REGIMEN_SPLIT              = 1294
```

## §20 — RQ2: invariato, più una garanzia nuova

Stessa prova strutturale. Gli invarianti sono stati comunque **rieseguiti**:

```
invented_quotes_accepted             = 0
invented_sourceunits_accepted        = 0
wrong_document_quotes_accepted       = 0
invented_quotes_presented_as_accepted = 0   ← NUOVO, obbligatorio per il §20
```

La distinzione richiesta dal §20 è ora rappresentata **nel dato**, non solo nel
report: `presentation_state` separa *accettata dal validatore canonico* da
*presentabile all'utente*.

## §18 — RQ3: preservato

| L'LLM può… | prima | dopo |
|---|---|---|
| decidere l'eligibility | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| creare un PMID | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| creare provenance | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| creare una SourceUnit | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| cambiare il canonical status | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| accettare autonomamente una quote | VALIDATED_DOWNSTREAM | **invariato** |
| modificare il dossier canonico | IMPOSSIBLE_BY_CONSTRUCTION | **invariato** |
| *far presentare come validata una proposta* | ⚠️ PARZIALE | **VALIDATED_DOWNSTREAM** ✅ |

```
PROMPT_ONLY_RESTRICTION = 0
UNCONTROLLED            = 0
```

Riverificato eseguendo il trasporto reale: `pmid`, `canonical_status`,
`provenance`, `recommendation`, `source_unit` → tutti `INVALID_TOOL_ARGUMENTS`.
`TOOL_SCHEMA` resta a 5 proprietà; `LLM_STAGE_IDS` resta 2 su 16 stage.

Batteria di 14 casi di validazione quote rieseguita: **13/14 conformi**. Il
quattordicesimo è ISS-019 (P3), la debolezza deliberata già documentata
dall'audit — il farmaco può comparire nell'unità invece che nella quote. Non
introdotta qui e fuori perimetro.

**RQ3 non è regredito, ed è anzi rafforzato**: l'unico punto classificato
`PARZIALE` dall'audit è ora chiuso.

## §21 — RQ4: migliorato

```
noneligible_retrieval_calls        = 0
forbidden_downstream_calls         = 0
expected_controlled_stops_failed   = 0
runtime_exceptions                 = 0
controlled_stops_ok                = 18 / 27
path_disagreements                 = 0
```

RQ4 è ora misurabile **attraverso il runtime canonico**, che era la condizione
mancante.

I 9 casi restanti su 27 non raggiungono il gate perché il trasporto del parser
era fallito nella run congelata: sono guasti del modello (ISS-012, P2), contati
a parte e non fra gli stop mancati.

## RQ5

Invariato. `oncokb_called = false`. Nessun modulo di
`backend/research_pipeline` importa OncoKB.

## GCA v3

`GRAPH_CANDIDATE_REPOSITORY_VERSION` non è stato toccato. Il runtime consuma
`graph_candidate_repository/2.0`. `gca_v3` resta `SHADOW / EVALUATION`, come
prescritto dal §13.
