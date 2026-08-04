# API contract — research pipeline (Fase B)

Namespace: **`/api/v1/research/pipeline`**
Feature flag: **`VERIFIABLE_PIPELINE_RESEARCH_ENABLED`**, default **off**.

Con flag disattivato ogni rotta risponde `404`, non `403`: il research runtime
non deve rivelare la propria esistenza in un deployment di prodotto.

**Nessun endpoint esistente è modificato.** `/api/v1/v3/retrieve`,
`/analyze`, `/compare-architectures`, `/agent-runs/{run_id}` e gli altri
restano invariati.

## 1. Rotte

| Metodo | Path | Scopo |
|---|---|---|
| `POST` | `/runs` | crea ed esegue una run |
| `GET` | `/runs/{run_id}` | snapshot completo |
| `GET` | `/runs/{run_id}/events` | eventi, append-only, paginati |
| `GET` | `/runs/{run_id}/stages/{stage_id}` | dettaglio di uno stage |
| `GET` | `/runs/{run_id}/dossier` | dossier finale |
| `GET` | `/runs/{run_id}/provenance` | lineage navigabile |
| `GET` | `/runs/{run_id}/metrics` | metriche canoniche |
| `GET` | `/runs/{run_id}/stream` | SSE — vedi `sse_contract.md` |
| `GET` | `/cases` | casi sintetici disponibili |

## 2. `POST /runs`

```json
{
  "clinical_text": "string, obbligatorio",
  "case_id": "string | null",
  "query_intent": "THERAPY_EVALUATION | THERAPY_DISCOVERY | null",
  "demo_case_key": "string | null"
}
```

`query_intent` è **suggerimento**, non imposizione: lo determina il parser dal
testo. Se il valore fornito diverge da quello estratto, la divergenza compare
come warning nello stage 2 e prevale il parser.

`demo_case_key` seleziona uno dei casi sintetici di `case_definitions.py`. Il
caso demo **esegue la pipeline reale**: non restituisce output registrati.

Risposta `201`:

```json
{"run_id": "uuid", "status": "CREATED", "stream_url": "…/stream"}
```

Errori: `422` testo vuoto, `404` flag off, `409` budget chiamate esaurito
(`CALL_BUDGET_EXCEEDED`), `503` dati congelati non disponibili.

## 3. `GET /runs/{run_id}` — snapshot

```json
{
  "run_id": "uuid",
  "case_id": "string",
  "status": "CREATED|RUNNING|COMPLETED|PARTIAL|FAILED|STOPPED",
  "started_at": "iso8601",
  "completed_at": "iso8601 | null",
  "current_stage": "string | null",
  "stopped_at": "PARSER_TRANSPORT_FAILED|CASECONTEXT_MISMATCH|RETRIEVAL_NO_MATCH|CALL_BUDGET_EXCEEDED|null",
  "input_text": "string (troncato a 600 caratteri)",
  "stages": [ /* vedi pipeline_stage_contracts.md */ ],
  "dossier_id": "string | null",
  "warnings": [], "errors": [],
  "versions": {
    "casecontext_schema": "end-to-end-pilot-casecontext/1.0",
    "dossier": "end-to-end-pilot-dossier/1.0",
    "enricher_prompt": "…", "enricher_transport": "…", "ledger_schema": 3
  },
  "metrics": { /* vedi §6 */ },
  "research_notice": {
    "runtime": "VERIFIABLE_RESEARCH_RUNTIME",
    "clinically_validated": false,
    "not_for_clinical_decision_making": true
  }
}
```

`status` **STOPPED** è distinto da **FAILED**: STOPPED è un arresto corretto
(mismatch, no match), FAILED è un guasto. La distinzione è obbligatoria — vedi
`error_and_abstention_model.md` §2.

`research_notice` è **sempre presente** e non disattivabile.

## 4. `GET /runs/{run_id}/events`

```
?after_sequence=<int>&limit=<int, default 200, max 1000>
```

```json
{
  "run_id": "uuid",
  "append_only": true,
  "hash_chain_valid": true,
  "events": [
    {"event_id": "…", "sequence": 1, "stage_id": "…|null",
     "event_type": "STAGE_STARTED", "created_at": "…",
     "payload_hash": "sha256", "parent_action_id": "…|null",
     "generating_action_id": "…|null",
     "producer": {"kind": "DETERMINISTIC", "component": "…", "version": "…",
                  "model": null, "prompt_version": null},
     "payload": { /* redatto e bounded */ }}
  ],
  "next_after_sequence": 42, "has_more": false
}
```

`hash_chain_valid` riusa `EventLedger.verify_chain`, già esposto da
`/agent-runs/{run_id}`. Ordinamento sempre per `sequence`, mai per timestamp.

## 5. `GET /runs/{run_id}/provenance`

Catena navigabile richiesta dalla §14:

```json
{"items": [{
  "dossier_item_id": "…",
  "chain": [
    {"level": "CASE_CONTEXT_FIELD", "ref": "biomarkers[0]", "label": "EGFR L858R"},
    {"level": "GRAPH_CANDIDATE_ASSERTION", "ref": "candidate_id", "graph_derived": true},
    {"level": "DOCUMENT", "ref": "document_id", "replayed": true},
    {"level": "SOURCE_UNIT", "ref": "source_unit_id",
     "locator": {"section": "…", "paragraph_index": 3, "char_start": 120, "char_end": 268},
     "content_hash": "sha256", "text": null},
    {"level": "AUTHOR_QUOTE", "ref": "enrichment_id", "quote": "…"},
    {"level": "VALIDATION", "ref": "…", "outcome": "ENRICHMENT_ACCEPTED"},
    {"level": "GATE", "ref": "…", "support_mask": {}},
    {"level": "DOSSIER_ITEM", "ref": "…", "status": "DIRECT"}
  ]}]}
```

**Regola vincolante:** al livello `SOURCE_UNIT` il campo `text` è **sempre
`null`**. L'indice SourceUnit contiene solo locatori e `content_hash`; il testo
del documento non transita mai per l'API. L'unico testo esposto è la
`AUTHOR_QUOTE` già validata e bounded.

`graph_derived: true` e `replayed: true` sono obbligatori dove si applicano: il
relatore deve poter distinguere una candidate proposta dal grafo da una prova
documentale, e un artefatto congelato da una risoluzione avvenuta ora.

## 6. `GET /runs/{run_id}/metrics`

Metriche **canoniche**, calcolate dal backend. Il frontend non le ricalcola.

```json
{"duration_ms_total": 0, "duration_ms_by_stage": {},
 "llm_calls": 0, "tokens_input": null, "tokens_output": null,
 "candidates_found": 0, "candidates_excluded": 0,
 "documents_resolved": 0, "source_units_used": 0, "papers_selected": 0,
 "enrichment_quote": 0, "enrichment_abstain": 0,
 "quotes_accepted": 0, "quotes_rejected": 0,
 "warnings": 0, "errors": 0, "dossier_items": 0,
 "status_counts": {"DIRECT": 0, "PARTIAL": 0, "AMBIGUOUS": 0,
                   "CONTRADICTED": 0, "DISCOVERED": 0, "NO_MATCH": 0}}
```

Campi non misurabili restano `null`, mai `0`. Il pilot non registra i token:
`tokens_input`/`tokens_output` saranno `null` finché il transport non li espone.
Un `null` visualizzato come "non disponibile" è corretto; visualizzato come zero
sarebbe falso.

## 7. Regole trasversali

1. flag off → `404` su tutte le rotte;
2. `research_notice` in ogni risposta di run;
3. nessun testo documentale in nessuna risposta;
4. nessun chain-of-thought: solo `prompt_version`, tool call, output
   strutturato, `abstention_reason`, reason code;
5. campi non disponibili `null`, mai valori inventati o zero di comodo;
6. nessuna risposta contiene raccomandazioni cliniche;
7. run non trovata → `404`; run in corso → snapshot parziale con
   `status: RUNNING`, non attesa bloccante.
