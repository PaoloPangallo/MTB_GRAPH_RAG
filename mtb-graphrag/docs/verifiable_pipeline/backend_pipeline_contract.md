# Backend pipeline contract — run e stage (Fase B)

Contratto **congelato**: da qui in poi le modifiche richiedono una revisione
esplicita. Dettaglio per singolo stage in `pipeline_stage_contracts.md`.

## 1. `PipelineRun`

```python
@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    case_id: str
    status: RunStatus
    started_at: str
    completed_at: str | None
    current_stage: str | None
    stopped_at: StopReason | None
    input_text: str                  # bounded a 600 caratteri
    stages: tuple[PipelineStage, ...]
    dossier_id: str | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    versions: Mapping[str, str | int]
    metrics: Mapping[str, Any]
```

Immutabile (`frozen=True`), coerentemente con lo stile del progetto: un
avanzamento produce una nuova run, non muta quella esistente. La sequenza
autorevole degli stati resta comunque il ledger.

### 1.1 `RunStatus`

`CREATED` · `RUNNING` · `COMPLETED` · `PARTIAL` · `FAILED` · `STOPPED`

| Stato | Quando |
|---|---|
| `COMPLETED` | tutti gli stage eseguiti, dossier prodotto |
| `PARTIAL` | dossier prodotto, ma con stage in warning o candidate senza supporto |
| `STOPPED` | arresto **corretto**: `CASECONTEXT_MISMATCH`, `RETRIEVAL_NO_MATCH` |
| `FAILED` | guasto: `PARSER_TRANSPORT_FAILED`, `CALL_BUDGET_EXCEEDED`, errore infrastrutturale |

`STOPPED` ≠ `FAILED`. È la distinzione che impedisce di presentare come guasto
il comportamento corretto del Caso 5 del pilot.

## 2. `PipelineStage`

```python
@dataclass(frozen=True)
class PipelineStage:
    stage_id: str
    stage_type: StageType
    sequence: int
    status: StageStatus
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    input_ref: str | None
    output_ref: str | None
    input_preview: Mapping[str, Any]
    output_preview: Mapping[str, Any]
    reason_codes: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    producer: StageProducer
    metrics: Mapping[str, Any]
    lineage: Mapping[str, Any]
```

`StageStatus`: `PENDING` · `RUNNING` · `SUCCEEDED` · `WARNING` · `FAILED` · `SKIPPED`

`SKIPPED` porta sempre in `reason_codes` lo `stopped_at` che lo ha causato: uno
stage saltato senza spiegazione sarebbe indistinguibile da un difetto.

## 3. `StageProducer`

```python
@dataclass(frozen=True)
class StageProducer:
    kind: Literal["DETERMINISTIC", "LLM", "HYBRID"]
    component: str
    version: str
    model: str | None = None
    prompt_version: str | None = None
    transport_version: str | None = None
```

`kind == "LLM"` **solo** per gli stage 2 e 9. Ogni altro stage è
`DETERMINISTIC`. Test di contratto: se un qualunque altro stage dichiara `LLM`,
la suite fallisce.

`model`, `prompt_version` e `transport_version` sono non-null **solo** dove
`kind` è `LLM`.

## 4. Identificatori di stage

Stabili, riusano i nomi del pilot dove esistono:

| `stage_id` | `stage_type` | §8 |
|---|---|---:|
| `stage_1_case_input` | `CASE_INPUT` | 1 |
| `stage_2_casecontext_parser` | `CASECONTEXT_PARSER` | 2 |
| `stage_3_casecontext_match` | `CASECONTEXT_MATCH_VERIFIER` | 3 |
| `stage_4_retrieval_plan` | `RETRIEVAL_PLAN` | 4 |
| `stage_5_kg_retrieval` | `KG_RETRIEVAL` | 5 |
| `stage_6_document_resolution` | `DOCUMENT_RESOLUTION` | 6 |
| `stage_7_source_units` | `SOURCE_UNIT` | 7 |
| `stage_8_paper_selection` | `PAPER_SELECTION` | 8 |
| `stage_9_paper_context_enricher` | `PAPER_CONTEXT_ENRICHER` | 9 |
| `stage_10_enrichment_validation` | `ENRICHMENT_VALIDATION` | 10 |
| `stage_11_deterministic_gates` | `DETERMINISTIC_GATES` | 11 |
| `stage_12_status` | `STATUS_CLASSIFICATION` | 12 |
| `stage_13_dossier` | `DOSSIER_BUILDER` | 13 |
| `stage_14_narrator` | `DOSSIER_NARRATOR` | 14 |
| `stage_15_narrative_verifier` | `NARRATIVE_VERIFIER` | 15 |

Gli stage 4/5 e 11/12 sono **prodotti da una sola chiamata** ciascuno
(`retrieval.retrieve`, `evaluate_association`) ma esposti come due stage
distinti, perché il codice restituisce già output separabili. Gli stage 14 e 15
esistono nel contratto con `status: SKIPPED` permanente e
`reason_codes: ["NOT_IMPLEMENTED"]`: non vengono mai eseguiti né simulati.

## 5. Orchestratore

`backend/research_pipeline/orchestrator.py`, derivato da `pipeline.py::run_case`.
Modifiche rispetto all'originale:

1. emette eventi sul ledger a ogni transizione;
2. assegna `stage_id` e `sequence`;
3. misura `duration_ms` per stage;
4. traduce `stopped_at` in `SKIPPED` per gli stage successivi;
5. **non cambia la logica di decisione**: gli stessi input producono gli stessi
   output del pilot.

Il punto 5 è verificabile: gli artefatti del pilot (`*_runs.jsonl`,
`*_validation_results.jsonl`, `dossier_previews.jsonl`) sono la baseline di
regressione. Se l'orchestratore promosso produce output diversi a parità di
input, è un difetto della promozione.

## 6. Budget chiamate

`CallBudget` con `MAX_REAL_CALLS_TOTAL = 20` viene preservato: è una protezione
di costo e va mantenuta nel research runtime. Il superamento è
`CALL_BUDGET_EXCEEDED` → `FAILED`, mai un'astensione silenziosa.

Il budget è **per run**, e il suo stato è esposto nelle metriche.

## 7. Accesso ai dati congelati

`data_access.py` [NUOVO] centralizza:

| Asset | Dimensione | Uso |
|---|---:|---|
| `graph_candidate_repository/2.0/candidates.jsonl` | 72,5 MB | STAGE 5 |
| `evidence_bundle/evidence_bundles.jsonl` | 35 KB | STAGE 6–8 |
| `authorized_document_cache_pilot/source_unit_index.jsonl` | 2,0 MB | STAGE 7 |

Regole:

1. percorsi da **configurazione**, mai da `Path(__file__).parents[n]` — è ciò
   che si rompe nel move;
2. **sola lettura**, nessuna copia dei 72,5 MB;
3. i loader `_load_source_units` / `_load_supporting_maps` vengono
   reimplementati qui: oggi vivono in `llm_claim_extractor/run_pilot.py` e sono
   l'unico aggancio residuo al vecchio Claim Extractor;
4. l'indice SourceUnit **non contiene testo** (verificato): il join col document
   store resta interno all'enricher e non esce mai dall'API.
