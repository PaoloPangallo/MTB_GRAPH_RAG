# Current research API contract

Namespace: `/api/v1/research/pipeline`.
Feature flag: `VERIFIABLE_PIPELINE_RESEARCH_ENABLED`, disabled by default.
Disabled research routes return 404. Existing product/legacy routes are separate.

The executable public schema is `backend/research_pipeline/public_schemas.py`.
`frontend/src/research/contracts.generated.ts` derives from it; regenerate with
`python scripts/generate_research_contracts.py`. The API preserves producer
extension fields and legacy field absence (`response_model_exclude_unset=True`).

## Endpoints

| Method | Path | Result |
|---|---|---|
| POST | `/runs` | Admit bounded asynchronous canonical execution |
| GET | `/runs?limit=50&offset=0` | Lightweight persisted history, maximum 200 rows |
| GET | `/runs/{run_id}?compact=true` | Run snapshot; compact omits heavy stage artifacts |
| GET | `/runs/{run_id}/events?after_sequence=0&limit=200&compact=true` | Event page, maximum 500 rows |
| GET | `/runs/{run_id}/stages/{stage_id}` | Stage artifact and associated events |
| GET | `/runs/{run_id}/dossier` | Canonical dossier plus verified presentation |
| GET | `/runs/{run_id}/provenance` | Case/candidate/source/quote provenance |
| GET | `/runs/{run_id}/metrics` | Backend accounting, missing measurements stay null |
| GET | `/runs/{run_id}/stream?compact=true` | Resumable SSE, see sse_contract.md |
| GET | `/cases` | Synthetic available cases, no fabricated execution outputs |
| GET | `/config` | Public runtime configuration |

## Admission

A free-text request requires `clinical_text` (1..100000 characters) and `case_id`.
A request with `demo_case_key` executes that predefined synthetic case.
Extra request fields are forbidden; `query_intent` and `execution_mode` cannot
be imposed by the client. The Parser determines intent from the supplied text.

The 201 response includes `run_id`, `case_id`, current `status`, `execution_mode`,
`stream_url` and `research_notice`. Execution may already have advanced at response
serialization; clients use the returned run ID to inspect authoritative state.
Invalid requests return 422, missing cases/runs return 404. Missing model provider
configuration returns 503. Full worker/queue capacity returns 503 with
`Retry-After: 5`; no run is admitted by this overload branch.

Admission is durable before document/provider work. Unexpected execution failure
creates a sanitized terminal event; source documents and credentials do not
appear in error payloads. Completed run access survives process restart and
memory-cache eviction.

## Snapshot and dossier

Run lifecycle states: CREATED, RUNNING, COMPLETED, PARTIAL, FAILED, STOPPED.
The canonical dossier has an independent domain status and can represent
INSUFFICIENT_CASE_CONTEXT, NEEDS_CLARIFICATION or NO_RELEVANT_KG_EVIDENCE.
A clean stop is distinct from provider failure. Empty canonical dossiers can be
available before the dossier stage executes; the dossier route returns 409 only
when no canonical/legacy dossier is available.

Paper, trial and KG-only collections keep their own provenance/support semantics.
Narrative presentation is separate from the canonical dossier. Only verified
presentation is displayed; rejected model output retains its audit separately.
Full source-unit context is projected to digests/length at the public boundary,
including historical snapshots/events. Literal authorized excerpts remain visible.

## Event page

Response: `run_id`, `append_only`, `hash_chain_valid`, `events`,
`next_after_sequence`, `has_more`. Cursor/offset must be nonnegative; bounds are
validated before store access. Sequence is per-run, never cross-run chronology.
A page reads at most limit+1 SQLite rows and returns at most limit events.

Integrity verification checks every row using the sealed ledger's original
preimage, retaining one raw row at a time. It does not materialize/decode all event
payloads. CPU audit cost remains linear in total run events. No audit result is
cached across mutations. SSE does not repeat this complete audit per poll.

Compact event payloads retain lifecycle/progress fields and omit heavy artifacts.
Full event pages retain public producer artifacts. `payload_json` is not exposed.
The persisted ledger is never rewritten to match a compact projection.
