# 02 — Architettura target (§2 del mandato) vs runtime reale

Confronto stadio per stadio fra l'architettura che la tesi intende descrivere e
ciò che `orchestrator.run_case` esegue davvero.

| # | Stadio target | Presente nel runtime | Come | Scostamento |
|---|---|---|---|---|
| 1 | Testo clinico libero | ✅ | `POST /runs` → `stage_1` | — |
| 2 | LLM CaseContext Parser | ✅ | `stage_2`, gemma4:cloud, forced tool call | — |
| 3 | CaseContext strutturato | ✅ | `case_context_raw`, contratto `case-context/1.0` esteso a 2.0 in modo additivo | il parser produce 1.0; le menzioni tipizzate 2.0 sono **derivate deterministicamente** a valle, non richieste al modello |
| 4 | CaseContext Match / Eligibility Verification | ✅ | `stage_3` (letteralità) + `stage_3b` (gate semantico) | — |
| 5 | STOP su mismatch essenziale | ✅ | `STOPPED / CASECONTEXT_MISMATCH`, `STOPPED / <eligibility_status>` | — |
| 6 | Retrieval deterministico | ✅ | `stage_4` + `stage_5`, nessun LLM | — |
| 7 | Knowledge Graph | ⚠️ | repository **statico già materializzato**, non query Neo4j live | scostamento di natura, non di forma — vedi sotto |
| 8 | GraphCandidateAssertion | ⚠️ | contratto **2.0** | il contratto 3.0 esiste, è validato, ma **non è nel runtime** — vedi sotto |
| 9 | Gate e verifiche deterministiche | ✅ | `stage_11` `determinism/gates.py` | — |
| 10 | Support mask / provenance / canonical status | ✅ | `stage_11` + `stage_12`, `check_origin.py` | — |
| 11 | DocumentResolver | ✅ | `stage_6`, `DocumentRuntime.resolve`, `network=False` | **non eseguibile qui**: `data_cache/` assente |
| 12 | Document | ✅ | 25 documenti, 43 nel manifest | — |
| 13 | SourceUnit | ✅ | `stage_7`, ri-parsata dalla cache | in REPLAY solo locatori + hash, mai testo |
| 14 | Selezione deterministica paper | ✅ | `stage_8`, max 2 paper / 4 unit | in REPLAY **rigiocata**, non ricalcolata |
| 15 | Paper Context Enricher | ✅ | `stage_9`, LLM | — |
| 16 | QUOTE \| ABSTAIN | ✅ | contratto dell'enricher v2 | — |
| 17 | Validazione letterale deterministica | ✅ | `stage_10`, `validator.py` / `validator_v2.py` | in REPLAY **rigiocata, non rieseguita** — vedi sotto |
| 18 | Rigetto enrichment se quote non valida | ✅ | `_accepted_for_gates` → `None` | — |
| 19 | AuthorContext validato | ✅ | sezione separata del dossier | — |
| 20 | ABSTAIN → warning / nessun enrichment | ✅ | `_accepted_for_gates` → `None` | — |
| 21 | Dossier strutturato | ✅ | `stage_13`, `build_dossier_preview` | — |
| 22 | LLM Dossier Narrator [opzionale] | ❌ | `stage_14` in `NOT_IMPLEMENTED_STAGE_IDS` | **NOT IMPLEMENTED** |
| 23 | Narrative Verifier | ❌ | `stage_15` in `NOT_IMPLEMENTED_STAGE_IDS` | **NOT IMPLEMENTED** |
| 24 | Dossier leggibile per MTB | ⚠️ | dossier strutturato reso dalla UI | nessuna narrazione LLM esiste |

## I tre scostamenti che contano

### A. Il KG è materializzato, non interrogato

Il runtime di ricerca non apre alcuna connessione Neo4j. `kg_retrieval.retrieve`
legge `graph_candidate_repository/2.0/candidates.jsonl`, un artefatto statico di
46 864 record, e lo dichiara nel proprio docstring.

Non è un difetto — è una scelta di scope motivata nel pilot — ma **cambia il
significato di RQ1**. La *representation fidelity* misurabile oggi è la fedeltà
del **materializzatore** (grafo → GraphCandidateAssertion), non la fedeltà di un
retrieval sul grafo vivo. La tesi deve dirlo in questi termini.

Corollario da verificare nel §25: se il materializzatore è anche ciò che produce
il gold contro cui viene misurato, si tratta di self-comparison. Ripreso in
`11_experimental_contamination.md`.

### B. Le proprietà semantiche v3 non sono nel runtime

Questo è lo scostamento più rilevante per le claim della tesi.

Il runtime consuma **GraphCandidateAssertion 2.0**. Il contratto 3.0 — con
`source_support_polarity`, `source_alignment_status`, `graph_direction`,
`alteration_expression_ast`, `alteration_parse_status`, `intervention_structure`,
`regimen_semantics_status`, `intervention_components`, `source_path_ids` —
esiste, è materializzato in 46 142 record, è validato da test, ed è **fuori dal
percorso di esecuzione**.

Raggiungibilità misurata (`runtime_component_matrix.csv`):

```
retrieval.kg_retrieval        CANONICAL_RUNTIME       ← eseguito
retrieval.kg_retrieval_v3     DEAD_OR_UNREACHABLE     ← zero riferimenti nel repo
retrieval.admission           SHADOW_EVALUATION       ← solo evaluation/ e test
retrieval.repository_v3       SHADOW_EVALUATION       ← solo evaluation/ e test
gca_v3.*                      SHADOW_EVALUATION
```

`data_access.candidates_path()` scrive `2.0` nel percorso, senza variabile
d'ambiente. `GRAPH_CANDIDATE_REPOSITORY_VERSION` esiste ma è letta solo da
`repository_v3.py`, che il runtime non importa: impostarla **non cambia nulla**
nel comportamento dell'API.

Questa non è una scoperta nascosta. `docs/runtime_v3_integration/13_runtime_switch_decision.md`
dichiara esplicitamente `runtime_default_changed_to_v3 = false` e ne motiva le
tre ragioni sostanziali. Il codice e la documentazione sono **coerenti fra loro**.

Ciò che va corretto è il perimetro delle claim:

> Le affermazioni «la polarità della fonte determina il ramo», «`A AND B`
> richiede entrambi i termini», «un regime irrisolto non produce supporto per un
> singolo farmaco» sono vere di `admission.py`, verificate su tutte le 46 142
> candidate v3, ed è un risultato solido. **Non** sono vere del sistema che
> risponde a `POST /runs`.

Il §28 elenca fra gli hard stop «il runtime canonico non corrisponde
all'architettura documentata». Qui **non** scatta: il runtime corrisponde alla
propria documentazione. Scatterebbe se la tesi descrivesse il runtime come v3.

`kg_retrieval_v3.py` resta comunque un problema a sé: 147 righe che sembrano
implementare il retrieval v3 e che nessuno chiama, nemmeno un test. Un lettore
del repository concluderebbe ragionevolmente che il retrieval v3 sia integrato.

### C. In REPLAY la validazione delle quote non viene eseguita

`replay.validation_fn` (`replay.py`, righe 117–132) restituisce l'esito
**registrato**, non ricalcolato. Il docstring lo motiva: senza il testo delle
SourceUnit ogni quote risulterebbe assente e verrebbe rigettata, producendo un
`REJECTED_QUOTE_NOT_FOUND` che contraddirebbe l'esito reale del pilot. Anche
`selection_fn` rigioca invece di ricalcolare.

La conseguenza per l'audit è vincolante:

- LIVE non è eseguibile senza `data_cache/` → stage 6 fallisce;
- REPLAY è eseguibile ma **non esercita il validatore**;
- quindi **nessuna run end-to-end oggi disponibile dimostra che una quote
  inventata viene rigettata**.

La proprietà può ancora essere dimostrata, ma solo a livello di componente,
sonda direttamente su `validator.py` / `validator_v2.py`. È esattamente ciò che
fa il Checkpoint D. Va detto nella tesi che la garanzia è verificata a livello
unitario, non end-to-end.

## `pipeline.run_case` — riferimento obsoleto

L'orchestratore dichiara nel docstring che `pipeline.run_case` è
l'implementazione di riferimento e che «un test confronta i due percorsi sugli
stessi input». Il test non esiste, e `pipeline.run_case` **non contiene lo stage
3b**. Le due implementazioni divergono sul gate pre-retrieval, che è il
contributo architetturale principale di questa fase. Registrato come issue in
`12_open_issues.md`.
