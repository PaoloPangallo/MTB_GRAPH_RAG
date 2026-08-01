# V3 pipeline observability UI — design specification

**Branch:** `feat/v3-pipeline-observability-ui`

**Base commit:** `70c3450b1bdb67a6c0d3c350191f3a68a2e0ceb0`

## Goal

Turn the existing V3 frontend into an inspection console for the deterministic
MTB Evidence Retrieval pipeline. The console must make the real path visible:
clinical input → normalized query context → promoted repository → structural
gates → buckets → provenance → deterministic dossier projection.

The legacy V2/GraphRAG, comparison, zero-shot, web-search and judge flows remain
available and are not changed by this work. The new form and observability views
apply only to `/api/v1/v3/retrieve`.

## Findings from the existing implementation

The actual V3 path is:

| Layer | File / symbol | Responsibility | Planned change |
|---|---|---|---|
| Form | `frontend/src/components/InputForm.tsx` | Builds the shared legacy request and currently invokes the V3 action with an empty intervention list and an implicit direction | Add a dedicated V3 form with explicit intervention, direction, policy and limit fields; leave legacy controls available |
| Frontend request | `frontend/src/App.tsx::handleV3Retrieve` | POSTs to `/api/v1/v3/retrieve` | Send the explicit V3 payload and retain the configured API base URL |
| Request model | `backend/api/v3_schemas.py::V3RetrieveRequest` | Validates the direct V3 payload | Extend only if a displayed V3 form field is already supported by the native query contract |
| Query normalization | `backend/pipeline/evidence/retrieval/v3_query.py::QualifiedClaimQuery` | Builds `normalized`, `gate_query` and `original` forms | Expose the existing forms in pipeline observability; do not introduce a second normalization algorithm |
| Pipeline binding | `backend/pipeline/evidence/retrieval/pipeline.py::EvidenceRetrievalPipeline.run` | Calls the explicit `qualified_claim_v3` backend | Do not change backend selection or execution semantics |
| Native V3 backend | `backend/pipeline/evidence/retrieval/v3_backend.py::QualifiedClaimRetrieverV3.retrieve` | Loads repository, evaluates gates, scores where allowed and ranks within buckets | Reuse its real counts, gate order and phase timing |
| Presentation adapter | `backend/api/v3_presentation.py::present_retrieval_outcome` | Separates clinical claims from technical records and maps reason/provenance data | Add a read-only `pipeline` section and richer display metadata |
| Response model | `backend/api/v3_schemas.py::V3RetrieveResponse` | Validates the product response | Add optional typed observability fields while preserving existing fields |
| React response types | `frontend/src/types.ts::V3RetrieveResponse` | Describes the current response | Add types for stages, gate summaries, buckets, provenance and dossier summaries |
| React view | `frontend/src/components/V3EvidenceView.tsx` | Shows counts, bucket cards and a collapsed technical section | Split into coordinated tabs: dossier, pipeline, evidences, provenance and technical data |

The direct V3 endpoint does not instantiate the older control-layer
`CaseContext`; it constructs a typed `QualifiedClaimQuery`. The UI will label the
result as the normalized case context while showing the exact `original` and
`normalized` forms returned by the native V3 query.

## Confirmed diagnostics

- The current V3 form sends `interventions: []` and `direction: ""`.
- The form uses `Lung Adenocarcinoma`, while the exploratory EGFR run uses
  `Non-Small Cell Lung Cancer`, `osimertinib` and `sensitivity`.
- The current form uses `result_limit: 50`; the exploratory inputs use `20`.
- For the current EGFR form payload the backend returns native score `total: 0`
  with `structural_score_eligible: false`; the frontend is reading the native
  score field and is not losing a native `108`.
- The manual EGFR payload returns three primary claims with native score `108`.
- The visible `?` characters are literal JSX separators in the current view.
- The baseline backend product test passes 7/7. The frontend test runner is
  currently blocked during Vitest configuration loading by Windows `spawn EPERM`.

## Product structure

The V3 console is one run with coordinated MUI tabs:

1. **Dossier clinico** — readable deterministic projection.
2. **Pipeline** — vertical MUI Stepper using the native stage order.
3. **Evidenze** — four bucket sections with readable claim cards.
4. **Provenienza** — lineage from qualified claim to source locator.
5. **Dati tecnici** — collapsed audit/technical records, explicitly not clinical evidence.

The run header remains visible above every tab and contains query ID, status,
latency, normalized context confirmation, repository/gate/backend/policy
versions, total records, claim records, technical records and bucket counts.

The abstention message is shown when there are no primary claims:

> Nessuna evidenza direttamente compatibile con il caso. Il sistema si astiene
> dal produrre conclusioni principali.

## Read-only backend observability contract

The endpoint keeps the current top-level response unchanged and adds:

```json
{
  "pipeline": {
    "stages": [],
    "gate_summary": [],
    "bucket_summary": {},
    "provenance_summary": {},
    "dossier_summary": {}
  }
}
```

Every item is derived from native output. Missing measurements are `null`.
Large raw payloads are not duplicated.

Stages represent:

- input clinical payload;
- normalized query context;
- repository/candidate loading;
- structural gate evaluation;
- bucket classification and ranking;
- provenance projection;
- deterministic dossier projection;
- optional narration status.

The stage details expose repository version, candidate count, claim/technical
split and technical categories. Gate summary follows the real native order from
`GATE_EXECUTION_ORDER`; per-record counts come only from native gate data. The
adapter does not invent phase timings or gate events.

Gate trace rows retain the original status (`pass`, `fail`, `not_applicable` or
`warning`), reason code and an Italian explanation. When query/claim values are
not present in the native axis data, the UI displays “dato non esposto”.

The dossier summary is a presentation projection from classified claims. It
does not claim that an unavailable native dossier object was executed. Audit and
rejected claims remain excluded from the clinical dossier projection and remain
available in technical/audit views.

The narration stage reports:

> Narrazione LLM non eseguita. Il risultato corrente è esclusivamente strutturale e deterministico.

No LLM renderer is added in this scope.

## Evidence and provenance rendering

Claim title fallback order:

1. `claim_text`;
2. complete structured tuple;
3. biomarker, direction and intervention;
4. claim ID with a structured-text-unavailable notice.

Claim ID and evidence type are separate typography elements. Reason codes are
shown as technical identifiers beside human-readable explanations, never as a
single string joined with `?`.

The score is displayed as “punteggio strutturale”. A native numeric zero remains
zero; missing or null values display “non disponibile”. The score is never shown
as a percentage or clinical probability.

Provenance is rendered as:

```text
Qualified Claim
  ↓
Parent GraphEvidenceRecord
  ↓
Source Unit
  ↓
PMID / DOI / NCT / URL / locator
```

Only real locator URLs are clickable. A parent ID alone is labeled `PARENT_ONLY`
and is never presented as a verified source.

## Visual direction and responsive behavior

The existing MUI theme remains the foundation: slate text, light slate canvas,
blue run accent, teal verified state, amber limitation state, red rejected state
and violet audit state. Inter remains the UI font; monospace is reserved for
technical identifiers.

The signature element is a run spine: a compact vertical sequence of real V3
stages with status markers, counts and expandable evidence. At 1920×1080 it
shares a two-column layout with the detail panel; at 1366×768 it keeps the form
compact and lets the detail area scroll; at tablet width the form stacks above
the run tabs. All interactive states retain keyboard focus and respect reduced
motion.

## Testing strategy

Backend tests will cover response compatibility, real stage derivation, counts,
gate summary/trace agreement, technical separation, provenance states, native
score preservation, null serialization, OpenAPI validity and planner/LLM
non-invocation.

Frontend tests will cover the explicit intervention/direction payload, context
display, stepper, bucket navigation, gate trace, lineage, technical separation,
score fallback, claim fallback, abstention, narration-not-run state, loading,
error, empty and responsive rendering, literal separator removal and isolation
from OncoKB.

Verification will include the four specified cases plus the current form case,
recording payload, normalized context, counts, scores, buckets, provenance and
latency before and after the correction. Corpus, claims, gate semantics,
scoring semantics, experiments, ledgers, gold and V2 remain untouched.

