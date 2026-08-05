# V3 Claim Contract Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve and present real V3 claim fields and case comparisons from repository to card while keeping retriever, gate, scoring, bucket, corpus, ledger, gold and official experiments unchanged.

**Architecture:** Keep `RetrievalOutcome` and the native retriever result untouched. Extend `v3_presentation.py` as a read-only projection: use the existing promoted-corpus loader only for optional source fields lost before `QualifiedClaimResult`, copy native score/gate/provenance values, and add explicit nullable `claim`, `decision`, and `case_comparison` sections. Extend Pydantic and TypeScript contracts, then make `V3EvidenceView` render those sections without changing the legacy V2 path.

**Tech Stack:** Python 3, FastAPI/Pydantic, `unittest`, React 19, TypeScript, MUI, Vitest, Testing Library.

## Global Constraints

- Do not modify corpus, retriever execution, gate semantics, scoring semantics, bucket semantics, ledger, gold, official experiments, or V2 flows.
- Keep every existing V3 top-level response field and add only backward-compatible fields.
- Copy optional source fields only when present; missing source data remains `null`.
- Do not use `applicability` as a bucket fallback.
- Do not show `structural_score=0` as a normal score when `structural_score_eligible=false`.
- Preserve native provenance and gate trace meaning; only add presentation metadata around them.
- Use the exact user-facing strings requested for tripla, score, direction and reason states.
- Preserve the five final invariants: `core_gate_semantics_modified=false`, `scoring_semantics_modified=false`, `bucket_semantics_modified=false`, `corpus_modified=false`, `source_identifiers_invented=false`, `official_experiment_modified=false`.

---

### Task 1: Record the source-to-card audit

**Files:**
- Create: `docs/v3_pipeline_ui/claim_data_contract_audit.md`
- Create: `docs/superpowers/specs/2026-08-01-v3-claim-contract-correction-design.md`

**Interfaces:**
- Consumes the live `CLM-e565f65d73cb1d4aa67b` repository row and direct V3 result.
- Produces a field-by-field loss/availability record used by backend and frontend tests.

- [x] **Step 1: Trace the pilot repository row and native result**

Run a read-only `EvidenceRetrievalPipeline` query with EGFR/L858R,
`Lung Adenocarcinoma`, no intervention and no requested direction. Record the
repository row, `AtomicInterventionClaim`, `QualifiedClaimResult`, adapter
record, endpoint-compatible JSON, TypeScript fields and card mappings.

- [x] **Step 2: Write the audit**

Document all requested fields at every boundary. Explicitly state that
`claim_text`, `subject`, `relation`, and `object` are absent from the pilot
source; `direction` exists in the source/internal model but is lost by the
native result projection; `applicability` is absent from the source; and the
source-unit list/locators are empty.

- [x] **Step 3: Self-review the audit**

Check that every value is copied from a live result or source row, that no
source identifier is invented, and that the audit records the current wrong
`not_constrained`, bucket-as-applicability, and score-zero UI mappings.

### Task 2: Lock the response contract with failing backend tests

**Files:**
- Modify: `backend/tests/test_v3_product_output.py`
- Modify: `backend/api/v3_schemas.py`

**Interfaces:**
- Produces typed `V3Claim`, `V3Decision`, `V3ComparisonValue`,
  `V3CaseComparison`, and optional nullable fields on `V3EvidenceRecord`.
- Keeps `V3RetrieveResponse` compatible with existing response fixtures.

- [ ] **Step 1: Add failing tests for the pilot contract**

Add tests that call `present_retrieval_outcome()` and assert:

```python
claim = response["evidence"]["primary"][0]
assert claim["claim"]["claim_text"] is None
assert claim["claim"]["structured_tuple_complete"] is False
assert claim["decision"]["bucket"] == "primary"
assert claim["decision"]["applicability"] is None
assert claim["decision"]["structural_score"] == 0.0
assert claim["decision"]["structural_score_eligible"] is False
assert claim["case_comparison"]["biomarker"]["query_value_original"] == ""
assert claim["case_comparison"]["biomarker"]["query_value_normalized"] == "EGFR L858R"
assert claim["case_comparison"]["biomarker"]["claim_value"] == "EGFR L858R"
assert claim["case_comparison"]["intervention"]["not_applicable_reason"] == "NOT_PROVIDED_BY_CASE"
assert claim["case_comparison"]["direction"]["comparison_result"] == "not_constrained"
```

Also assert the source direction is `sensitivity` in the new claim object, the
source unit is still `None`, the parent/provenance values are unchanged, and
the endpoint validates the extended response.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest backend.tests.test_v3_product_output -v
```

Expected: the new assertions fail because `claim`, `decision`, and
`case_comparison` do not yet exist and the adapter currently maps direction
and applicability incorrectly.

- [ ] **Step 3: Add minimal Pydantic models**

In `backend/api/v3_schemas.py`, define nullable models for the new objects and
add them to each evidence record. Keep the legacy `score`, `gate_trace`,
`reason_codes`, `parent_graph_evidence_record`, `source_unit`, and `provenance`
fields unchanged. `V3RetrieveResponse` continues to accept the existing
top-level shape and keeps `pipeline` optional for compatibility with old
fixtures.

- [ ] **Step 4: Run the focused tests again**

Run the same unittest command. Expected: Pydantic accepts the intended shape,
but assertions about the adapter values still fail.

### Task 3: Implement the read-only adapter projection

**Files:**
- Modify: `backend/api/v3_presentation.py`
- Modify: `backend/tests/test_v3_product_output.py`

**Interfaces:**
- Consumes native `RetrievalOutcome`, native query forms, gate axes, score
  dictionaries, provenance and optional promoted source records.
- Produces enriched evidence records without changing native bucket, score,
  gate or provenance values.

- [ ] **Step 1: Add the failing adapter helper tests**

Cover source-field copying, complete/partial/missing triple states, all five
comparison availability states, real score `108`, ineligible score, null score,
applicability distinct from bucket, gate-specific reason-code rows, and
direction separation (`case_requested`, `claim_direction`, `gate_result`).

- [ ] **Step 2: Add a cached read-only source lookup**

Use the existing `load_from_registry()` only to read the promoted source row
by `claim_id`. Copy `claim_text`, `subject`, `relation`, `object`, and
`direction` only if the source mapping contains them. If the source row is
unavailable or a field is absent, return `None`; never synthesize a sentence or
triple. Do not alter the loader, corpus files, retriever, gate or scoring code.

- [ ] **Step 3: Add comparison projection helpers**

Implement helpers with explicit values:

```python
_comparison_state(query_original, query_normalized, claim_value, result, not_applicable_reason)
_case_comparison(result, query_original, query_normalized)
_decision(result)
_claim_projection(result, source_record)
```

Use `NOT_PROVIDED_BY_CASE` for an empty case constraint,
`MISSING_IN_CLAIM` for absent claim data, `NOT_APPLICABLE` for an axis not
meaningfully evaluated, `NOT_EXPOSED_BY_GATE` when the native gate does not
publish the value, and `AVAILABLE` when both value and result are real.

- [ ] **Step 4: Correct reason and gate messages**

Attach every reason code to its originating gate in the comparison/gate trace
data. For empty-code gates use specific native-data messages such as
`Lo stato della claim è ammesso.`, `Il dominio della claim è compatibile.`,
`Nessun intervento è stato imposto dal caso.`, or a specific unavailable reason;
do not emit `Gate valutato senza reason code` when the native axis explains the
outcome.

- [ ] **Step 5: Run backend focused tests and verify GREEN**

Run:

```powershell
python -m unittest backend.tests.test_v3_product_output backend.tests.test_v3_retriever_binding -v
```

Confirm native bucket counts, gate order, provenance, and gate trace semantics
remain unchanged while the new presentation fields pass.

### Task 4: Add frontend types and claim/card rendering tests

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/V3EvidenceView.tsx`
- Modify: `frontend/src/components/V3EvidenceView.test.tsx`

**Interfaces:**
- Consumes enriched evidence records from Task 3.
- Produces readable card title, decision, comparison, gate reason and
  provenance rendering without raw semantic placeholders.

- [ ] **Step 1: Add failing frontend tests**

Add fixtures for: real claim text; complete triple; missing triple; score
eligible `108`; score ineligible `0`; null score; bucket with null
applicability; original/normalized/claim values; NOT_PROVIDED_BY_CASE versus
MISSING_IN_CLAIM; direction `sensitivity`, `resistance`, and `not_constrained`;
reason codes with gate labels; parent-only provenance; and CaseContext.

Assert that the card contains:

```text
Tripla strutturata non disponibile nel record sorgente
Non vincolata dal caso
Sensibilità
Resistenza
Non applicabile
Non disponibile
Il punteggio strutturale non è una probabilità clinica.
```

Assert that raw `not_constrained` is not used as the main title and that three
generic `non specificato` values are not rendered for a missing triple.

- [ ] **Step 2: Run Vitest and verify RED**

Run:

```powershell
npm test -- --run src/components/V3EvidenceView.test.tsx
```

Expected: the new assertions fail against the current card implementation.

- [ ] **Step 3: Extend TypeScript types**

Add nullable `V3ClaimProjection`, `V3Decision`, `V3CaseComparisonValue`, and
`V3CaseComparison` types. Make `applicability` nullable and preserve the
legacy `score` dictionary. Type reason-code gate provenance and comparison
values without changing existing response consumers.

- [ ] **Step 4: Implement data-first card helpers**

Implement `claimTitle`, `formatDirection`, `formatScore`,
`formatAvailability`, and comparison rows. Use the four-level title fallback,
show the explicit missing-triple notice beside the claim ID, keep bucket and
applicability as separate chips/rows, and use decision-level score fields for
display. Add a MUI `Tooltip` with the required structural-score statement.

- [ ] **Step 5: Render CaseContext, comparisons and all reasons**

Render original and normalized case context, each gate’s case/claim/result
values and not-applicable reason, one primary human reason, and an expandable
list of all code/gate pairs. Preserve parent/source/provenance values and
label absent source-unit data explicitly.

- [ ] **Step 6: Run focused frontend tests and verify GREEN**

Run the focused Vitest command again, then `npm run typecheck`.

### Task 5: Verify the four live cases and capture screenshots

**Files:**
- Create/update only: `docs/v3_pipeline_ui/v3_claim_contract_verification.md`
- Create/update only: `docs/v3_pipeline_ui/screenshots/*` if the existing screenshot convention permits it

**Interfaces:**
- Consumes `/api/v1/v3/retrieve` responses and the updated frontend.
- Produces a reproducible case table and screenshots; no corpus or experiment artifact is changed.

- [ ] **Step 1: Run the four direct V3 cases**

Run and save response extracts for:

```text
EGFR L858R without intervention
EGFR L858R + osimertinib
ALK G1202R + alectinib, resistance
RMI2 without intervention
```

- [ ] **Step 2: Record each required display field**

For each case record card title, claim text/fallback, triple, original and
normalized case values, claim values, comparison result, score, eligibility,
applicability, bucket, direction and provenance.

- [ ] **Step 3: Run backend and frontend verification**

Run:

```powershell
python -m unittest backend.tests.test_v3_product_output backend.tests.test_v3_retriever_binding -v
npm test -- --run
npm run typecheck
```

Run `git diff --check` and inspect the diff to confirm only adapter/API/type/UI
tests/docs changed, with no corpus, gold, ledger, experiment or retriever
semantic changes.

- [ ] **Step 4: Capture updated screenshots**

Start the local V3 product using the existing project script, open the four
cases in the UI, and capture the card view showing claim title, comparison,
score, eligibility, applicability, bucket, direction and provenance. Store only
the requested UI screenshots and verification notes.

- [ ] **Step 5: Record final invariants**

Write the six explicit invariant values in the verification document and
confirm `source_identifiers_invented=false` by checking all displayed source
identifiers against the repository/provenance fields.

