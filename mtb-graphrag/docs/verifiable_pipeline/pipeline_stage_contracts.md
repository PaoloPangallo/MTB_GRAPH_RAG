# Pipeline stage contracts (Fase B)

Per ogni stage: cosa produce, chi lo produce, cosa la UI deve mostrare.
Envelope comune in `backend_pipeline_contract.md`.

Legenda producer: **D** deterministico · **L** LLM · **R** replay di artefatto congelato.

---

## STAGE 1 — Case Input · D

`output_preview`: `case_id`, `clinical_text` (bounded 600), `query_intent`
suggerito, `demo_case_key`, timestamp.

UI: testo clinico, case_id, tipo di esecuzione, avviso che il sistema non
formula raccomandazioni cliniche.

---

## STAGE 2 — CaseContext Parser · **L**

Componente: `casecontext_parser` + `casecontext_prompt`.
Schema: `end-to-end-pilot-casecontext/1.0`.

Output: `CaseContext` con `disease`, `biomarkers[]`, `previous_interventions[]`,
`target_intervention`, `query_intent`, `clinical_question`, `uncertainties[]`.
Ogni campo porta `raw_value`, `normalized_value` e `source_spans[]`
(`quote`, `start_offset`, `end_offset`).

Validazione **strutturale** (`case_context_schema_errors`), non semantica:
`MISSING_KEYS`, `QUERY_INTENT_INVALID`, `BIOMARKERS_NOT_LIST`,
`PREVIOUS_INTERVENTIONS_NOT_LIST`, `UNCERTAINTIES_NOT_LIST`,
`THERAPY_DISCOVERY_MUST_HAVE_NULL_TARGET_INTERVENTION`.

Fallimento transport → `stopped_at = PARSER_TRANSPORT_FAILED`.

UI: modello, prompt version, tutti i campi, span estratti evidenziati sul testo.
Badge **LLM**. Nessun thinking interno.

---

## STAGE 3 — CaseContext Match Verifier · D

Componente: `casecontext_match_verifier`.

Un `MatchVerificationRecord` per ciascuno dei 6 `MATCH_FIELDS`:
`field`, `casecontext_value`, `status` (`MATCH`/`MISMATCH`/`UNCERTAIN`/`MISSING_IN_TEXT`),
`supporting_text`, `start_offset`, `end_offset`, `reason_code`.

Decisione di blocco: `essential_fields_pass()` → `stopped_at = CASECONTEXT_MISMATCH`.

**Proprietà di sicurezza da preservare:** il verifier **non si fida degli offset
autodichiarati dal modello** — li ricalcola. Regressione registrata nel pilot,
da coprire con test.

UI: tabella campo per campo. Badge **deterministico**. La decisione di
proseguire è mostrata, **non ricalcolata** dal browser.

---

## STAGE 4 — Retrieval Plan · D

Query deterministica derivata dal CaseContext: intent, filtri, disease,
biomarker, intervention, limiti, repository interrogato.

**Non è un planner LLM.** La UI deve dirlo esplicitamente: è il punto in cui il
prompt vieta al modello di pianificare.

---

## STAGE 5 — Knowledge Graph Retrieval · D

Componente: `retrieval.retrieve` su
`graph_candidate_repository/2.0/candidates.jsonl` (72,5 MB).

Output: `associations[]` con `candidate`, `no_match`.
Ogni candidate: `candidate_id`, `disease`, `biomarkers`, `interventions[]`,
`direction`, `predicate`.

`no_match: true` → `stopped_at = RETRIEVAL_NO_MATCH`.

**Correzione architetturale del pilot da preservare:** il matching del
biomarcatore considera l'intero contenuto testuale del campo
(`gene` + `normalized_value` + `raw_value`), non un singolo campo preferito.

UI: candidate trovate ed escluse, nodi, archi, path, provenance del grafo, e
l'etichetta obbligatoria:

> **Graph-derived candidate — non ancora prova documentale.**

---

## STAGE 6 — Document Resolution · **R**

Nessun fetch. Gli artefatti provengono da `evidence_bundles.jsonl`.

Output: `document_id`, identificatori (PMID/PMCID/DOI/NCT), `availability`,
`document_type`, `replayed: true`.

UI: etichetta obbligatoria

> **Artefatto congelato — risolto in una run precedente, non recuperato ora.**

Presentarlo come risoluzione live sarebbe falso.

---

## STAGE 7 — Source Unit · **R**

Da `source_unit_index.jsonl` (2,0 MB).

Campi reali, **verificati**: `source_unit_id`, `document_id`, `unit_type`,
`section`, `subsection`, `paragraph_index`, `sentence_index`, `char_start`,
`char_end`, `page`, `bbox`, `table_id`, `figure_id`, `content_hash` (SHA-256),
`parser`, `parser_version`, `locator_confidence`.

**L'indice non contiene testo.** Nessun campo `text`, `content` o `body`.

Regola vincolante: l'API espone il record indice; il campo `text` è **sempre
`null`**. Il testo esiste solo nel document store, il join resta interno
all'enricher, e l'unico testo esposto è la quote validata dello STAGE 9.

UI: locatori e hash. Nessun articolo completo.

---

## STAGE 8 — Paper Selection · D

Componente: `paper_selection.select_papers_for_association`.

Output: `selected_papers[]` (**massimo 2**, invariante verificata nel pilot:
7 paper su 4 associazioni), `excluded_papers[]`, criterio di ranking,
`resolved_source_unit_ids[]`.

UI: per ogni candidate, paper selezionati ed esclusi, ranking, motivo, SourceUnit
passate all'enricher. Il limite di 2 va mostrato come vincolo, non come caso.

---

## STAGE 9 — Paper Context Enricher v2 · **L**

Componenti: `paper_context_enricher_v2`, `_prompt`, `_transport`.

Output `PaperContextEnrichment`: `enrichment_id`, `case_id`, `candidate_id`,
`paper_id`, `source_unit_id`, `drug`, `author_claim_quote`,
`author_context_summary`, `evidence_kind`, `abstain`, `abstention_reason`,
`model`, `prompt_version`.

`evidence_kind` ∈ RESPONSE · BENEFIT · RESISTANCE · DIAGNOSTIC · MECHANISTIC · OTHER.
Fuori enum → `REJECTED_SCHEMA` (3/7 nella v1; 0 nella v2).

Transport: `V2_TRANSPORT_VALID` 7/7 nella run `6ee64c5`.
Decisioni: QUOTE 3, ABSTAIN 4.

UI: modello, prompt version, transport version, tool call, decisione
**QUOTE o ABSTAIN entrambe come esiti normali**, `abstention_reason`, token e
latenza se disponibili (oggi `null`). Badge **LLM**.

**Vietato:** thinking interno, e qualunque resa dell'enricher come decisore
clinico.

---

## STAGE 10 — Enrichment Validation · D

Componenti: `paper_context_enricher_v2_validator`, `enrichment_validator`.

Controlli: la SourceUnit citata esiste; appartiene al paper corretto; la quote è
**letterale e continua** nella SourceUnit; gli offset corrispondono; il summary è
grounded; nessuna raccomandazione clinica.

Esito: uno dei 10 `ENRICHMENT_OUTCOMES` (vedi `error_and_abstention_model.md` §4).

**Solo** `ENRICHMENT_ACCEPTED` e `ENRICHMENT_ACCEPTED_WITH_WARNING` proseguono.

UI: ogni controllo con esito e reason code. Un rigetto mostra **quale** controllo
ha fallito.

---

## STAGE 11 — Deterministic Gates · D

Componente: `deterministic_pipeline.evaluate_association`.

`support_mask` a **4 assi reali**:

| Asse | Valori | Origine |
|---|---|---|
| `disease` | SUPPORTED | **ereditata** dallo STAGE 5, non ricalcolata |
| `biomarker` | SUPPORTED | **ereditata**, idem |
| `intervention` | SUPPORTED, DISCOVERED | dal query intent |
| `direction` | SUPPORTED, CONTRADICTED, UNRELATED_EVIDENCE, NO_DOCUMENT_SIGNAL, NOT_APPLICABLE | dagli enrichment validati |

`direction_consistencies[]` ∈ CONSISTENT · CONFLICTING · UNRELATED.

UI: le 4 assi con input, risultato, reason code, evidence reference, versione.
Per `disease` e `biomarker` l'etichetta obbligatoria è *"ereditato dal match
strutturale — STAGE 5"*, con link all'evidenza di retrieval. Nel codice partono
da valore hardcoded: mostrarli come gate valutati sarebbe falso.

**`NOT_IMPLEMENTED` espliciti:** source gate, provenance gate, completeness,
negation, contradiction come gate autonomo, score. Elencati e marcati, mai
lasciati vuoti come se fossero stati valutati.

---

## STAGE 12 — Status e classificazione · D

Stessa chiamata dello STAGE 11, output separato.

`status` ∈ DIRECT · PARTIAL · AMBIGUOUS · CONTRADICTED · DISCOVERED · NO_MATCH
`gate_bucket` ∈ PRIMARY · WARNING · REJECTED · DISCOVERY
`warnings[]` ∈ NO_VALIDATED_ENRICHMENT_AVAILABLE ·
SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING ·
VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION

Tabella decisionale completa in `error_and_abstention_model.md` §5.

UI: status, bucket, motivazione deterministica, campi mancanti, contraddizioni.
**L'LLM non compare mai come autore dello status.** Il producer è
`DETERMINISTIC`; il badge lo dichiara.

---

## STAGE 13 — Dossier Builder · D

Componente: `dossier.build_dossier_preview` + `build_candidate_therapy_entry`.
Versione: `end-to-end-pilot-dossier/1.0`.

Struttura per candidate: `candidate_id`, `drug`, `graph_relation`,
`document_support`, `author_context[]`, `validation_results[]`,
`gate_results{bucket, support_mask}`, `status`, `warnings[]`.

Provenance dichiarata alla fonte:

```json
{"dossier_kind": "research_only_end_to_end_pilot_preview",
 "gemma_role": "paper_context_enricher_only",
 "gemma_never_decides": ["support_status","direction","contradiction","gate","score","bucket"],
 "not_wired_to_production_runtime": true}
```

Tre sezioni separate in UI, come da §17:
**A. evidenza deterministica** (graph relation, document support, gate,
provenance, status) · **B. author context** (quote, paper, SourceUnit, summary,
validazione, astensione) · **C. limitazioni**.

`author_context` **non sovrascrive mai** claim o status. Test di contratto.

---

## STAGE 14 — Dossier Narrator · **NOT_IMPLEMENTED**
## STAGE 15 — Narrative Verifier · **NOT_IMPLEMENTED**

Presenti nel contratto con `status: SKIPPED` permanente e
`reason_codes: ["NOT_IMPLEMENTED"]`. Mai eseguiti, mai simulati.

UI:

> Narrazione non eseguita. Il risultato è esclusivamente strutturale e
> deterministico.
