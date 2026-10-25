# 09 — Sostenibilità di RQ1–RQ5

Dati: `evaluation/deliverability/rq_readiness.json`,
`evaluation/deliverability/raw/G01_rq_reproduction.jsonl`.

## Metodo

Ogni script di evaluation è stato **rieseguito** con `OUT` rediretto in una
directory di scratch, e l'output confrontato **byte a byte** con l'artifact
committato.

| Script | exit | file | identici | differenti | delta reale |
|---|:-:|:-:|:-:|:-:|---|
| `run_rq1.py` | 0 | 7 | 6 | 1 | solo `generated_at` |
| `run_rq2.py` | 0 | 5 | 4 | 1 | `generated_at` + `ncbi_requests` (12 → 0, nessuna rete usata qui) |
| `run_rq4.py` | 0 | 5 | 0 | 5 | RQ4 chiama l'LLM: varia per costruzione |
| `run_gca_v3_audit.py` | 0 | 9 | 8 | 1 | solo `generated_at` |
| `run_runtime_v3_integration.py` | 0 | 11 | 10 | 1 | solo `generated_at` |

**Tutti e cinque gli script girano oggi e riproducono le proprie metriche.** Con
l'unica eccezione di RQ4 — che invoca il modello e quindi non è deterministico —
ogni numero pubblicato è riprodotto identico. Non ci sono metriche hard-coded.

> **Incidente dichiarato.** `run_rq1` e `run_gca_v3_audit` hanno scritto
> `aggregate_metrics.json` anche nella directory committata nonostante il
> redirect di `OUT`. L'unica differenza era `generated_at`; i due file sono stati
> ripristinati con `git checkout` e lo stato del repository è tornato identico a
> quello iniziale (verificato con `git status --porcelain`). Registrato per
> trasparenza: significa che quei due script **non onorano** un `OUT` sostituito,
> e un revisore che li esegua sovrascrive gli artifact committati.

---

## RQ1 — Graph representation fidelity · **DELIVERABLE**

```
materialization_precision = 1.0        matched_paths      = 46 864
materialization_recall    = 1.0        excluded_paths     = 0
field_completeness        = 1.0        exact_duplicate_rate = 0.0
direction_inversions_contract = 0
direction_inversions_graph    = 486
ALTERATION_LOST  = 1 091   REGIMEN_SPLIT = 1 294   semantic_duplicate_groups = 344
```

Lo script verifica lo SHA-256 dichiarato dell'artifact (`verified: true`),
registra un `corpus_fingerprint` del KG sorgente e dichiara esplicitamente
`neo4j_used: false`. Il KG sorgente (`data_expl/DatasetTESI/Dataset TESI/Clean_Graph_Data`,
43 005 nodi / 60 546 archi) **è tracciato in git**.

**Il risultato più importante di questa sezione**: l'evaluation RQ1 del
repository *già misura e pubblica* le tre perdite di fedeltà che questo audit ha
trovato indipendentemente. Il mio conteggio autonomo delle inversioni di
direzione — 486 — **coincide esattamente** con `direction_inversions_graph`.

Va letto correttamente: `precision = recall = 1.0` riguarda il
**materializzatore** (ogni percorso eleggibile diventa una GCA senza perdita di
campo, `direction_inversions_contract = 0`). Le 486/1091/1294 sono perdite
**già presenti nell'export del grafo**, misurate e dichiarate.

Quindi RQ1 è sostenibile, a due condizioni:

1. dichiarare che RQ1 misura la **materializzazione** da un export CSV
   congelato, non una query Neo4j live;
2. **non confondere** questi numeri con il comportamento del runtime. La misura
   dice «la rappresentazione conserva X»; ISS-002 dice «il runtime che la
   consuma converte 752 candidate negative in positive». Sono affermazioni
   diverse, e solo la prima è supportata da RQ1.

---

## RQ2 — Document grounding · **PARZIALMENTE DELIVERABLE**

```
candidates_total          46 864
candidates_with_pmid       8 230  (17,6 %)
unique_pmids               2 229
pmid_resolved_metadata_only 2 228     pmid_not_found  1
pmid_document_available       15      pmid_document_unavailable 2 214
pairs_candidate_level      4 860      pairs_parent_level_only 3 370
retraction_or_correction_signals  3
semantic_relevance        NOT_MEASURED
```

La catena a sette livelli del §20 **è distinguibile nel codice**, e
`research_routes._ACCEPTED_OUTCOMES` codifica esplicitamente che solo una
validazione accettata rende `document_grounded` vero. La distinzione
candidate-level / parent-level provenance esiste ed è misurata (`scope:
evidence_record` vs `linked_publication`).

Due qualità da segnalare in positivo:

- `semantic_relevance` è `NOT_MEASURED` con motivazione esplicita e il flag
  `semantic_pmid_precision_claimed_without_gold: false`. Lo script **si rifiuta
  di rivendicare** una precisione semantica che non ha modo di misurare;
- i segnali di ritrattazione/correzione sono contati (3).

**Ciò che limita RQ2:**

| Livello | Stato |
|---|---|
| 1. identificatore presente | ✅ 8 230 / 46 864 |
| 2. identificatore risolve | ✅ 2 228 / 2 229 |
| 3. documento disponibile | ⚠️ 15 — e i byte non ci sono |
| 4. SourceUnit con testo | ❌ non ricostruibile senza `data_cache/` |
| 5. passaggio rilevante | ❌ non calcolabile |
| 6. quote proposta | ⚠️ 3, dalle 7 chiamate congelate |
| 7. quote validata | ⚠️ 2 accettate, 1 rigettata — e in REPLAY **non rieseguita** |

E soprattutto: **16 candidate su 46 864 (0,034 %) sono raggiungibili
end-to-end**. È il denominatore onesto di ogni claim end-to-end.

RQ2 è sostenibile come **studio di fattibilità della catena di grounding**, non
come misura di copertura del grounding. La differenza va scritta nella tesi.

---

## RQ3 — Hybrid authority separation · **DELIVERABLE** ✅

Il risultato più solido dell'audit.

```
prompt_only_restrictions       = 0
uncontrolled_paths             = 0
invented_quotes_accepted       = 0
invented_sourceunits_accepted  = 0
wrong_document_quotes_accepted = 0
llm_can_change_canonical_status = false
```

8 punti su 9 del §21 sono `IMPOSSIBLE_BY_CONSTRUCTION` o `VALIDATED_DOWNSTREAM`
— nessuno è `PROMPT_ONLY_RESTRICTION`, nessuno è `UNCONTROLLED`. Il dettaglio è
in `06_llm_authority_boundaries.md`.

La separazione non poggia su istruzioni nel prompt: poggia su uno schema di tool
call con cinque proprietà, un trasporto che rifiuta le chiavi extra, un
validatore che confronta le quote alla lettera, e un `frozenset` di due soli
stage LLM su quindici.

**L'unica riserva** è ISS-003: il dossier *presentato* può contenere una quote
fabbricata, anche se lo stato *canonico* non ne è toccato. Delimitare la claim
allo stato canonico rende RQ3 pienamente sostenibile così com'è.

---

## RQ4 — Selective routing · **PARZIALMENTE DELIVERABLE**

Metriche post-gate (riprodotte identiche):

```
empty_casecontext_retrieval   = 0     symptom_copied_into_disease_field = 0
out_of_scope_retrieval        = 0     injected_drug_extracted_as_target = 0
non_actionable_retrieval      = 0     control_instruction_execution     = 0
contradictory_case_retrieval  = 0     forbidden_downstream_calls        = 0
```

Questo audit ha **verificato l'invariante per via indipendente**, misurando le
chiamate anziché leggerle: 0 chiamate al retrieval su 12 casi non eleggibili con
parser stub, e 0 su 5 categorie in LIVE con LLM reale. **L'invariante regge.**

Ma due problemi ne limitano la portata:

**1. La metrica non misura il runtime.** `run_runtime_v3_integration.py` chiama
`casecontext.pipeline.run` direttamente, bypassando l'orchestratore. Attraverso
il runtime canonico, ogni decisione non eleggibile termina con un `ValueError`
non gestito (**ISS-001**), confermato in LIVE su 5 categorie via API reale. Il
sistema si ferma per la ragione giusta e lo comunica come un guasto.

**2. Nel 28 % delle run LIVE il gate non viene mai raggiunto.** Il parser reale
ha fallito il trasporto in 5 casi su 18 nelle mie misurazioni — coerente con il
benchmark congelato (`FORCED_TOOL_VALID: 26` su 35, cioè 26 % di fallimento).
`PARSER_TRANSPORT_FAILED` non è uno stop del gate e non va contato come tale.

Il benchmark congelato pre-gate resta un riferimento utile e onesto
(`routing_matches_protocol_requirement: 0.3143`,
`symptom_copied_into_disease_field: 5`, `contract_violation_rate: 0.2571`): è la
baseline che il gate ha migliorato.

RQ4 diventa pienamente sostenibile con la correzione di ISS-001 e un rerun della
misura **attraverso l'orchestratore**.

---

## RQ5 — External citation recovery (OncoKB) · **PLANNED**

```
oncokb_integrated_into_runtime  = false
pilot_executed                  = false
oncokb_calls_executed           = 1     (GET /api/v1/info — solo metadati)
oncokb_knowledge_data_retrieved = false
queryable_candidate_count       = 0
not_queryable_candidates        = 38 634
reason = ONCOKB_FALLBACK_BLOCKED_NO_AUTHORIZATION + ONCOKB_FALLBACK_LOW_YIELD
```

Esistono uno studio di fattibilità, un report di licensing, un piano di query e
un file di risultati vuoto per costruzione. **Nessun dato di conoscenza OncoKB è
stato recuperato**; l'unica chiamata è ai metadati della versione.

Il mandato ha chiesto di non chiamare OncoKB: non è stato chiamato. Il §27
ammette RQ5 come `PILOT` o `PLANNED` purché dichiarato esplicitamente, e lo è.
Nessun modulo di `backend/research_pipeline` importa OncoKB;
`backend/pipeline/agents/oncokb_enricher.py` appartiene alla pipeline di
prodotto legacy.

**RQ5 = PLANNED, con fattibilità documentata. Conforme.**

---

## Sintesi

| | Stato | Blocca il freeze? |
|---|---|:-:|
| RQ1 | DELIVERABLE con delimitazione | no |
| RQ2 | PARZIALE — fattibilità, non copertura | no, se dichiarato |
| RQ3 | **DELIVERABLE** | no |
| RQ4 | PARZIALE — bloccata da ISS-001 | **sì** |
| RQ5 | PLANNED, dichiarato | no |
