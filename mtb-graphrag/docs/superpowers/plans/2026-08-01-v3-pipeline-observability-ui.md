# V3 Pipeline Observability UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Expose the complete deterministic V3 evidence-retrieval path in one responsive MUI run console while preserving the existing V2/legacy flows and native V3 semantics.

**Architecture:** Extend only the V3 presentation adapter with a compact, read-only \`pipeline\` projection derived from the native \`RetrievalOutcome\`. Replace the current V3 action with an explicit \`V3RunForm\`, then render one \`V3EvidenceView\` with stable run summary and five coordinated tabs. Keep the legacy \`InputForm\` handlers and legacy views available through the existing application path.

**Tech Stack:** FastAPI, Pydantic, Python \`unittest\`, React 19, TypeScript, MUI 9, Vitest, Testing Library, Vite.

## Global Constraints

- Do not modify corpus, claims, gate semantics, scoring, official experiments, ledgers, gold or V2.
- V3 must call \`EvidenceRetrievalPipeline.run(..., retrieval_backend="qualified_claim_v3")\` directly.
- Do not add planner, agentic tool selection, PubMed live, OncoKB live or LLM classification to V3.
- Add only read-only presentation data; use \`null\` when a phase timing or value is not exposed.
- Preserve all existing top-level V3 response fields and legacy frontend flows.
- Show native structural score values unchanged; show \`non disponibile\` only for missing values.
- The implementation ends with one local commit: \`product: visualize the complete V3 evidence pipeline\`.

---

### Task 1: Lock the observability contract (backend) with tests

**Files:**
- Modify: \`backend/tests/test_v3_product_output.py\`
- Modify: \`backend/api/v3_schemas.py\`

**Interfaces:**
- Produces the response contract consumed by the presentation adapter and React types: \`pipeline.stages\`, \`pipeline.gate_summary\`, \`pipeline.bucket_summary\`, \`pipeline.provenance_summary\`, \`pipeline.dossier_summary\`.

- [ ] **Step 1: Write failing backend tests**

Add tests asserting that a direct endpoint response contains \`pipeline\`, that
its stage IDs are the real V3 stages, that \`case_normalization\` mirrors the
native normalized query, that stage latency is \`None\` when unavailable, and
that the existing \`summary\`, \`evidence\`, \`technical_records\` and metadata
fields are unchanged. Add assertions that a primary claim keeps native score
\`108\` and a missing score serializes as \`None\` rather than \`0\`.

Use the existing \`_query()\` fixture and add one direct EGFR fixture with
\`gene="EGFR"\`, \`alteration="L858R"\`,
\`disease="Non-Small Cell Lung Cancer"\`,
\`interventions=["osimertinib"]\`, and \`direction="sensitivity"\`.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

\`\`\`powershell
python -m unittest backend.tests.test_v3_product_output -v
\`\`\`

Expected: the existing seven tests may pass, while the new assertions fail with
missing \`pipeline\` data.

- [ ] **Step 3: Define minimal Pydantic response models**

Add typed models in \`backend/api/v3_schemas.py\` for \`PipelineStage\`,
\`GateSummary\`, \`BucketSummary\`, \`ProvenanceSummary\`, \`DossierSummary\`
and \`PipelineObservability\`. Keep detail fields as
\`dict[str, Any]\` so native data is not duplicated into a speculative schema.
Add \`pipeline\` to \`V3RetrieveResponse\` with a product projection generated
by the adapter.

- [ ] **Step 4: Run the focused tests again**

Run the same unittest command. Expected: failure remains limited to absent
adapter data, proving the schema accepts the intended shape.

---

### Task 2: Derive real pipeline and gate summaries in the presentation adapter

**Files:**
- Modify: \`backend/api/v3_presentation.py\`
- Modify: \`backend/tests/test_v3_product_output.py\`

**Interfaces:**
- Consumes: \`RetrievalOutcome.payload\`, native \`payload.query\`,
  \`payload.gate_decisions\`, \`payload.latency_ms\`,
  \`payload.all_results\` and existing technical/evidence projections.
- Produces: \`present_retrieval_outcome(outcome)["pipeline"]\` and enriched
  per-claim \`gate_trace\` rows.

- [ ] **Step 1: Add failing derivation tests**

Add assertions equivalent to:

\`\`\`python
pipeline = response["pipeline"]
assert pipeline["stages"][0]["id"] == "clinical_input"
assert pipeline["stages"][1]["id"] == "case_normalization"
assert pipeline["stages"][2]["details"]["repository_version"] == "qualified_claim_repository/1.4"
assert pipeline["stages"][2]["output_count"] == 311
assert pipeline["stages"][4]["details"]["buckets"]["primary"] == response["summary"]["primary"]
assert sum(item["count"] for item in pipeline["provenance_summary"].values()) == response["summary"]["claim_records"]
\`\`\`

Also assert that gate summary counts are computed from returned gate axes, that
the real native gate order is retained, and that no \`report\` field is added.

- [ ] **Step 2: Run tests and verify the new assertions fail**

Run \`python -m unittest backend.tests.test_v3_product_output -v\` and confirm
the new pipeline assertions fail before implementation.

- [ ] **Step 3: Implement focused adapter helpers**

Add these typed helpers in \`v3_presentation.py\`: \`_pipeline_stages(payload:
Any, evidence: Mapping[str, list[dict[str, Any]]], technical:
Mapping[str, list[dict[str, Any]]], summary: Mapping[str, int]) ->
list[dict[str, Any]]\`, \`_gate_summary(results: list[Any], gate_order:
list[str]) -> list[dict[str, Any]]\`, \`_bucket_summary(evidence:
Mapping[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]\`,
\`_provenance_summary(evidence: Mapping[str, list[dict[str, Any]]]) ->
dict[str, dict[str, Any]]\` and \`_dossier_summary(evidence:
Mapping[str, list[dict[str, Any]]], abstention: bool) -> dict[str, Any]\`.

Implement each helper from native payload data. Use
\`payload.latency_ms["normalization"]\`, \`gating\` and \`ranking\` only where
those native phase values exist. Set latency to \`None\` for repository
loading, per-gate execution, provenance construction, dossier projection and
rendering when no native measurement exists. Use
\`payload.gate_decisions["gate_execution_order"]\` for ordering and keep
aggregate stages visible with count fields set to \`None\` when they cannot be
measured per record.

Extend \`_gate_trace()\` with \`case_value\`, \`claim_value\`,
\`reason_code\` and \`message\` only when those values exist in the native axis
dictionaries. Never change native status or translate a fail to warning.
Improve reason-code display mapping for the codes observed in the four cases;
unknown codes remain visible with the generic Italian explanation.

- [ ] **Step 4: Run focused backend tests**

Run:

\`\`\`powershell
python -m unittest backend.tests.test_v3_product_output backend.tests.test_v3_retriever_binding -v
\`\`\`

Expected: all focused tests pass and native V3 bucket/score semantics remain
unchanged.

---

### Task 3: Build typed frontend data and a dedicated V3 request form

**Files:**
- Modify: \`frontend/src/types.ts\`
- Create: \`frontend/src/components/V3RunForm.tsx\`
- Create: \`frontend/src/components/V3RunForm.test.tsx\`
- Modify: \`frontend/src/components/V3EvidenceView.test.tsx\`

**Interfaces:**
- Produces \`V3RunForm\` props
  \`{ disabled: boolean; onSubmit: (payload: V3Request) => void }\` and typed
  \`V3RetrieveResponse.pipeline\` data.

- [ ] **Step 1: Write failing form tests**

Render the form, fill gene, alteration, disease, intervention, direction,
policy and limit, submit it, and assert the callback receives:

\`\`\`typescript
expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
  gene: 'EGFR',
  alteration: 'L858R',
  disease: 'Lung Adenocarcinoma',
  interventions: ['osimertinib'],
  direction: 'sensitivity',
  policy_mode: 'strict_verified',
  result_limit: 20,
}))
\`\`\`

Assert that no OncoKB control or generic “Genera Report GraphRAG” label is
rendered in the V3 form.

- [ ] **Step 2: Run the focused Vitest test and verify failure**

Run:

\`\`\`powershell
npm test -- --run src/components/V3RunForm.test.tsx
\`\`\`

Expected: module or component-not-found failure before implementation.

- [ ] **Step 3: Add exact TypeScript types**

Add \`V3Request\`, \`V3PipelineStage\`, \`V3GateSummary\`,
\`V3BucketSummary\`, \`V3ProvenanceSummary\`, \`V3DossierSummary\` and
\`V3PipelineObservability\` in \`types.ts\`. Keep
\`V3EvidenceRecord.score\` as \`Record<string, unknown>\` and make nullable
display fields explicit.

- [ ] **Step 4: Implement the MUI form**

Use controlled MUI fields for gene, alteration, biomarker, disease,
interventions (comma-separated input converted to a trimmed array), direction
(\`sensitivity\`, \`resistance\`, or an empty unconstrained value), intervention
class/formulation when supported, policy and limit. Submit only V3 request
fields accepted by \`V3RetrieveRequest\`.

- [ ] **Step 5: Run form tests**

Run the focused Vitest command again. Expected: passing form payload and OncoKB
isolation assertions.

---

### Task 4: Integrate V3 mode without changing legacy flows

**Files:**
- Modify: \`frontend/src/App.tsx\`
- Modify: \`frontend/src/components/InputForm.tsx\`
- Modify: \`frontend/src/App.css\`
- Modify: \`frontend/src/index.css\`
- Create: \`frontend/src/components/App.test.tsx\`

**Interfaces:**
- \`handleV3Retrieve(payload: V3Request)\` posts exactly to
  \`/api/v1/v3/retrieve\` and stores the typed response.
- Existing \`handleAnalyze\`, \`handleCompare\`, \`handleEnrich\`,
  \`handleJudge\` and \`ArchitectureComparison\` behavior remains available.

- [ ] **Step 1: Add an integration test seam**

Extract the V3 fetch function from \`App.tsx\` into an exported helper or
injectable callback and add a test asserting endpoint, method, JSON payload and
typed response handling. Keep legacy endpoint strings unchanged.

- [ ] **Step 2: Run the integration test and verify failure**

Run \`npm test -- --run src/components/App.test.tsx\`. Expected: missing
extracted helper or missing V3 form integration assertion.

- [ ] **Step 3: Implement mode separation**

Make V3 the explicit run surface with \`V3RunForm\`. Keep the current legacy
\`InputForm\` accessible through a visible Legacy control or section, with its
existing callbacks unchanged. Do not pass V3 requests through \`/analyze\`.

- [ ] **Step 4: Implement loading, error and empty states**

Show a loading progress state while the direct V3 request is active, an error
alert for non-2xx responses or fetch failures, and a first-run empty state that
explains that no run is selected. Preserve the V3 response when switching tabs.

- [ ] **Step 5: Run integration tests and TypeScript**

Run:

\`\`\`powershell
npm test -- --run src/components/App.test.tsx
npm run typecheck
\`\`\`

Expected: passing V3 integration tests and no type errors.

---

### Task 5: Implement the coordinated V3 inspection views

**Files:**
- Modify: \`frontend/src/components/V3EvidenceView.tsx\`
- Create: \`frontend/src/components/V3PipelineView.tsx\`
- Create: \`frontend/src/components/V3ProvenanceView.tsx\`
- Create: \`frontend/src/components/V3TechnicalRecords.tsx\`
- Create: \`frontend/src/components/V3ClaimCard.tsx\`
- Create: \`frontend/src/components/V3GateTrace.tsx\`
- Modify: \`frontend/src/components/V3EvidenceView.test.tsx\`

**Interfaces:**
- \`V3EvidenceView({ data: V3RetrieveResponse })\` owns tab state and run
  summary.
- Child views receive only the relevant typed \`data\` projection and do not
  fetch.

- [ ] **Step 1: Write failing component tests**

Extend the fixture with \`pipeline\` and assert:

- run summary says “311 record analizzati”, “148 claim cliniche” and “163 record tecnici”;
- all five tabs are visible and switch content;
- Pipeline shows the vertical stage spine and gate summary;
- claim cards render subject/relation/object separately when present and use the fallback chain otherwise;
- no literal \`?\` separator is rendered between claim ID, type, reasons or trace fields;
- score \`null\` renders “non disponibile”, while score \`0\` renders \`0\`;
- provenance shows parent/source-unit/source-locator nodes without creating links for missing IDs;
- technical categories are separate from clinical buckets;
- abstention and narration-not-executed messages are visible.

- [ ] **Step 2: Run the focused component tests and verify failure**

Run \`npm test -- --run src/components/V3EvidenceView.test.tsx\` and confirm
the new assertions fail against the current single-section view.

- [ ] **Step 3: Implement run summary and tab shell**

Use MUI \`Tabs\`, \`Tab\`, \`Card\`, \`Chip\` and \`Alert\` with responsive
\`Grid\`. Keep query ID, status, latency, versions, backend, policy and all
counts fixed above tab content. Do not display the aggregate phrase
“311 evidenze”.

- [ ] **Step 4: Implement pipeline and gate trace**

Use MUI vertical \`Stepper\` with expandable details. Render stage status,
input/output counts, details and only real latency values. Render gate status
badges using pass/fail/not applicable/warning without rewriting statuses.

- [ ] **Step 5: Implement cards, dossier, provenance and technical records**

Use separate typography elements for identifiers and labels. Add Italian
explanations beside reason codes. Build the deterministic dossier from the
classified evidence projection and state clearly that no generative narration
was used. Render provenance lineage and technical record accordions without
moving technical records into clinical buckets.

- [ ] **Step 6: Run focused component tests**

Run \`npm test -- --run src/components/V3EvidenceView.test.tsx\`. Expected: all
view, fallback, abstention, score, lineage and separation assertions pass.

---

### Task 6: Add responsive styling and frontend regression coverage

**Files:**
- Modify: \`frontend/src/components/V3EvidenceView.tsx\`
- Modify: \`frontend/src/components/V3PipelineView.tsx\`
- Modify: \`frontend/src/components/V3ClaimCard.tsx\`
- Modify: \`frontend/src/App.css\`
- Modify: \`frontend/src/index.css\`
- Create: \`frontend/src/components/V3Responsive.test.tsx\`

- [ ] **Step 1: Write responsive/accessibility tests**

Assert that tabs and the form remain reachable at a tablet viewport, buttons
have accessible names, expanded panels expose their content, and keyboard focus
can reach the run tabs and stage accordions.

- [ ] **Step 2: Run the test and verify failure**

Run \`npm test -- --run src/components/V3Responsive.test.tsx\`.

- [ ] **Step 3: Implement layout rules**

Keep the form narrow on desktop, allow the detail panel to scroll, stack form
above results under the tablet breakpoint, use \`overflow-wrap:anywhere\` for
technical identifiers and preserve visible focus styles. Do not add a charting
library or animation dependency.

- [ ] **Step 4: Run frontend quality checks**

Run:

\`\`\`powershell
npm test -- --run
npm run typecheck
npm run lint
npm run build
\`\`\`

If Vitest still fails with the existing Windows \`spawn EPERM\`, record the
exact failure and verify TypeScript, lint and build independently before
addressing only the test-runner environment/configuration issue.

---

### Task 7: Run backend compatibility, OpenAPI and case verification

**Files:**
- Modify: \`backend/tests/test_v3_product_output.py\`
- Create: \`backend/tests/test_v3_pipeline_observability.py\`
- Create: \`docs/v3_pipeline_ui/architecture_mapping.md\`
- Create: \`docs/v3_pipeline_ui/v3_ui_data_flow.md\`
- Create: \`docs/v3_pipeline_ui/frontend_before_after.md\`

- [ ] **Step 1: Add four-case and form-case verification tests**

Exercise the endpoint with exact payloads for FGFR2, ALK, EGFR manual, RMI2 and
the current form case. Assert payload fields, normalized query, summary, score
totals, bucket counts, provenance statuses and non-null total latency. Do not
modify corpus artifacts or test data to force agreement.

- [ ] **Step 2: Run backend suites**

Run:

\`\`\`powershell
python -m unittest backend.tests.test_v3_product_output backend.tests.test_v3_pipeline_observability -v
python -m compileall backend
\`\`\`

- [ ] **Step 3: Validate OpenAPI**

Start/import the FastAPI application and serialize \`app.openapi()\` to confirm
\`POST /api/v1/v3/retrieve\` documents the new pipeline shape and still
documents the existing request/response fields.

- [ ] **Step 4: Write the three requested reports**

Document the actual form-to-backend map, before/after payload and context, and
the frontend/backend data flow. Include the confirmed root causes and the
explicit statement that V3 planner and LLM classification are not used.

---

### Task 8: Start the stack, capture real screenshots, verify all requirements and commit

**Files:**
- Create: \`docs/v3_pipeline_ui/screenshot_dossier.png\`
- Create: \`docs/v3_pipeline_ui/screenshot_pipeline.png\`
- Create: \`docs/v3_pipeline_ui/screenshot_gate_trace.png\`
- Create: \`docs/v3_pipeline_ui/screenshot_provenance.png\`
- Create: \`docs/v3_pipeline_ui/screenshot_technical_records.png\`
- Create: \`docs/v3_pipeline_ui/screenshot_abstention.png\`

- [ ] **Step 1: Start the backend and frontend**

Run \`uvicorn backend.api.main:app --reload\` from \`mtb-graphrag\`, and
\`npm run dev\` from \`mtb-graphrag/frontend\`. Use the in-app browser or an
available screenshot-capable browser workflow to execute the real cases.

- [ ] **Step 2: Capture the six requested views**

Capture dossier, pipeline, gate trace, provenance, technical records and RMI2
abstention from real API responses. Do not use mocked or invented screenshot
data.

- [ ] **Step 3: Run the final verification matrix**

Run backend tests, V3 suite, frontend tests, typecheck, lint, Vite build,
OpenAPI validation and Python compilation. Check that only intended files are
modified and that corpus/gold/ledger/official experiment paths are unchanged.

- [ ] **Step 4: Review the diff and create the implementation commit**

Run \`git diff --check\`, inspect \`git status --short\`, then stage only the
implementation, tests, reports and screenshots. Create:

\`\`\`powershell
git commit -m "product: visualize the complete V3 evidence pipeline"
\`\`\`

Do not push or merge.
