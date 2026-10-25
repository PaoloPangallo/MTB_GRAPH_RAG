# V3 claim data-contract audit — CLM-e565f65d73cb1d4aa67b

## Scope and method

This audit records the current end-to-end path for the pilot claim
`CLM-e565f65d73cb1d4aa67b`:

```text
qualified claim repository
  → QualifiedClaimQuery / AtomicInterventionClaim
  → QualifiedClaimRetrievalResult / QualifiedClaimResult
  → present_retrieval_outcome
  → /api/v1/v3/retrieve JSON
  → frontend V3EvidenceRecord
  → V3EvidenceView / EvidenceCard
```

The trace was executed against the working tree at commit `fdd257b` on
`feat/v3-pipeline-observability-ui`, using this direct V3 query:

```json
{
  "query_id": "AUDIT-PILOT-EGFR-NO-INTERVENTION",
  "claim_domain": "therapeutic",
  "gene": "EGFR",
  "alteration": "L858R",
  "disease": "Lung Adenocarcinoma",
  "interventions": [],
  "direction": "",
  "policy_mode": "strict_verified",
  "include_warning": true,
  "include_audit": true,
  "include_rejected": true,
  "result_limit": 500
}
```

The retrieval result for the pilot is a primary claim with native bucket
`primary_ranked_results`, native score `total=0.0`, and
`structural_score_eligible=false`. The zero is therefore not a clinical score
and must not be presented as an ordinary score.

## Source record: qualified claim repository

Source file:
`backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/evidence_claims.jsonl`
and the mirrored therapeutic view
`backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4/therapeutic_claims.jsonl`.

The record contains:

```json
{
  "claim_id": "CLM-e565f65d73cb1d4aa67b",
  "claim_type": "atomic_intervention_claim",
  "biomarker": "EGFR L858R",
  "disease_scope": "Lung Adenocarcinoma",
  "intervention": "gefitinib",
  "canonical_intervention": "gefitinib",
  "direction": "sensitivity",
  "polarity": "supports",
  "parent_id": "GEP-5f6e4a0e89277128ca53",
  "graph_evidence_id": "evidence:2624",
  "source_unit_ids": [],
  "locators": [],
  "provenance": {
    "identity_source_unit_token": "LEGACY-NO-REVIEWED-SOURCE-UNIT:ES-V2-evidence-2624",
    "graph_record_ids": ["evidence:2624"],
    "legacy_statement_id": "ES-V2-evidence-2624"
  }
}
```

The record does not contain `claim_text`, `subject`, `relation`, or `object`.
It does not contain a separate `applicability` field or a structural score.
`source_unit_ids` and `locators` are empty. The identity token is provenance
metadata, not a source-unit identifier and is not promoted to one.

## Internal retriever model

The repository row is rehydrated as `AtomicInterventionClaim` by
`backend/pipeline/evidence/retrieval/v3_objects.py`.

Present and preserved in the internal model:

| Field | Value |
|---|---|
| `claim_text` | absent from the model |
| `subject` / `relation` / `object` | absent from the model |
| `biomarker` | `EGFR L858R` |
| `disease` (`disease_scope`) | `Lung Adenocarcinoma` |
| `intervention` | `gefitinib` |
| `direction` | `sensitivity` |
| `evidence_type` (`claim_type`) | `atomic_intervention_claim` |
| `applicability` | absent; no domain field exists |
| `bucket` | absent; assigned only after gate evaluation |
| `structural_score` | absent; assigned only after gate evaluation |
| `structural_score_eligible` | absent; assigned only after gate evaluation |
| `reason_codes` | absent on the source object; produced by gates |
| `gate_trace` | absent; produced by the integrated gate |
| parent record | `parent_id=GEP-5f6e4a0e89277128ca53`, `graph_evidence_id=evidence:2624` |
| source unit | `source_unit_ids=[]` |
| provenance | preserved from the repository record |

No claim sentence or structured subject–relation–object triple can be
recovered from this model without inventing data. The direction is real at this
stage and is the first field that is later lost by the retrieval-result
projection.

## Native `EvidenceRetrievalPipeline` result

The pipeline returns `RetrievalOutcome.payload` as a native
`QualifiedClaimRetrievalResult`. For the pilot result:

| Field | Native value | Contract observation |
|---|---|---|
| `claim_text` | absent | not carried by `QualifiedClaimResult` |
| `subject` / `relation` / `object` | absent | not carried by `QualifiedClaimResult` |
| `biomarker` | `EGFR L858R` | preserved |
| `disease` | `Lung Adenocarcinoma` | preserved as `disease_scope` |
| `intervention` | `gefitinib` | preserved as `canonical_intervention` |
| `direction` | absent as a result attribute | claim direction is not copied by `_result_for`; gate axis only exposes `direction_match_type` |
| `evidence_type` | `atomic_intervention_claim` | preserved as `claim_type` |
| `applicability` | absent | not a native result field |
| `bucket` | `primary_ranked_results` | preserved |
| `structural_score` | `score.total=0.0` | native zero because score is not eligible in this query |
| `structural_score_eligible` | `score.eligibility.structural_score_eligible=false` and `gate.structural_score_eligible=false` | preserved in native score/gate dictionaries |
| `reason_codes` | `BIOMARKER_EXACT_LITERAL_MATCH`, `DISEASE_EXACT_MATCH` | preserved |
| `gate_trace` | native axis trace dictionary | preserved as `gate_trace` |
| original query | `payload.query.original` | preserved |
| normalized query | `payload.query.normalized` | preserved |
| claim values | biomarker/disease/intervention appear in gate axes; direction claim value does not | direction axis exposes only the comparison result `not_constrained` |
| parent record | `parent_id=GEP-5f6e4a0e89277128ca53`, `graph_evidence_id=evidence:2624` | preserved |
| source unit | `source_unit_ids=[]` in provenance | preserved as empty |
| provenance | native provenance dictionary | preserved |

The native gate data for the pilot includes:

```json
{
  "intervention_match_result": {
    "query_interventions": [],
    "claim_interventions": ["gefitinib"],
    "match_type": "no_intervention_constraint",
    "compatible": true
  },
  "direction_match_result": {
    "direction_match_type": "not_constrained",
    "polarity_match_type": "not_constrained",
    "compatible": true
  },
  "score_eligibility": {
    "structural_score_eligible": false
  }
}
```

`not_constrained` is the direction-gate result for an unconstrained case; it is
not the claim's direction. The source claim direction remains `sensitivity`,
but is unavailable at this pipeline-result boundary.

## Presentation adapter before the correction: `v3_presentation.py`

Current behavior in `_claim_record()`:

| Field | Adapter value | Status |
|---|---|---|
| `claim_text` | `null` | correct: source does not provide it |
| `subject` / `relation` / `object` | `null` | correct: source/model do not provide them |
| `biomarker` | `EGFR L858R` | preserved |
| `disease` | `Lung Adenocarcinoma` | preserved |
| `intervention` | `gefitinib` | preserved |
| `direction` | `not_constrained` | incorrect mapping: gate result replaces claim direction |
| `evidence_type` | `atomic_intervention_claim` | preserved |
| `applicability` | `primary` | incorrect mapping: `_BUCKETS[result.bucket]` is used as fallback/value |
| `bucket` | `primary` | correct projection of native bucket |
| `score` | native score dictionary, including `total=0.0` and nested eligibility | value preserved but no explicit top-level display contract |
| `structural_score` | absent as a dedicated field | response/UI must derive from native score without changing it |
| `structural_score_eligible` | absent as a dedicated field | response/UI must expose native eligibility explicitly |
| `reason_codes` | code plus human message | codes preserved; only code-independent gate messages are generic |
| `gate_trace` | list of seven rows | current row values mix normalized gate query with gate outcome; original query is not carried per row |
| original query | present under `case_context.original` | preserved at response-level, not as explicit comparison objects |
| normalized query | present in `case_context` and `gate_query` | preserved, but not separated from original in claim cards |
| claim values | biomarker/disease/intervention values present; direction is `not_constrained` | direction claim value is unavailable here |
| parent record | `parent_graph_evidence_record.parent_id=GEP-5f6e4a0e89277128ca53` | preserved |
| source unit | `null` | correct: source-unit list is empty |
| provenance | `PARENT_ONLY`, parent ID, empty source IDs/locators | preserved semantically |

For the pilot the adapter currently emits `applicability="primary"` and
`direction="not_constrained"`; these are the two user-visible semantic bugs.
It also emits gate rows such as `Gate valutato senza reason code` for gates
whose real result can be described from native fields.

## `/api/v1/v3/retrieve` response JSON before the correction

The response model currently keeps the legacy top-level shape:

```json
{
  "case_context": {
    "original": {
      "biomarker": "",
      "gene": "EGFR",
      "alteration": "L858R",
      "disease": "Lung Adenocarcinoma",
      "interventions": [],
      "direction": ""
    },
    "normalized_biomarker": "EGFR L858R",
    "normalized_disease": "Lung Adenocarcinoma",
    "normalized_interventions": [],
    "intervention_form": "absent"
  },
  "evidence": {
    "primary": [
      {
        "claim_id": "CLM-e565f65d73cb1d4aa67b",
        "claim_text": null,
        "subject": null,
        "relation": null,
        "object": null,
        "biomarker": "EGFR L858R",
        "disease": "Lung Adenocarcinoma",
        "intervention": "gefitinib",
        "direction": "not_constrained",
        "evidence_type": "atomic_intervention_claim",
        "applicability": "primary",
        "bucket": "primary",
        "score": {"total": 0.0, "eligibility": {"structural_score_eligible": false}}
      }
    ]
  }
}
```

The current response has no explicit `claim`, `decision`, or
`case_comparison` object. The existing optional `pipeline` projection exposes
the query forms and native gate order, but not a per-gate distinction between
original query value, normalized query value, claim value, comparison result,
and not-applicable reason.

## TypeScript and `V3EvidenceView` before the correction

`frontend/src/types.ts` currently defines `V3EvidenceRecord` with nullable
`claim_text`, tuple fields, and the ambiguous `direction`, `applicability`,
`bucket`, and `score` fields. It does not define:

- a structured `claim` object with `structured_tuple_complete`;
- a `decision` object with separate bucket/applicability/score eligibility;
- a `case_comparison` object with original/normalized/claim/result/reason;
- typed reason-code provenance (`gate` per reason code);
- typed parent/source/provenance lineage fields.

`V3EvidenceView.tsx` currently:

- uses `claim_text`, then tuple, then biomarker/direction/intervention, then ID;
- displays the raw `direction` value, so `not_constrained` appears without explanation;
- displays `applicability` and `bucket` independently but receives the same value;
- displays `score.total` directly, so the pilot shows `Punteggio strutturale: 0`;
- shows only the first reason code as the main reason and does not associate all codes with gates;
- shows gate trace `case_value` and `claim_value`, but has no original/normalized/comparison/not-applicable fields;
- shows parent/provenance fields but not an explicit source-unit availability state.

The correct claim-title fallback cannot produce a structured triple for this
record. The UI must therefore show the real biomarker/direction/intervention
fallback when available, and only show the explicit message
`Tripla strutturata non disponibile nel record sorgente` alongside the claim ID;
it must not render three repeated “non specificato” values as a fabricated
triple.

## Loss and availability summary

| Field | Repository | Internal model | Pipeline result | Adapter/JSON | Current UI |
|---|---|---|---|---|---|
| `claim_text` | absent | absent | absent | `null` | fallback logic; no explicit source warning |
| `subject` | absent | absent | absent | `null` | repeated generic fallback in detail grid |
| `relation` | absent | absent | absent | `null` | repeated generic fallback in detail grid |
| `object` | absent | absent | absent | `null` | repeated generic fallback in detail grid |
| `biomarker` | present | present | present | present | present |
| `disease` | present as `disease_scope` | present | present | present | present |
| `intervention` | present | present | present | present | present |
| `direction` | `sensitivity` | `sensitivity` | lost; only gate result exists | wrong `not_constrained` | wrong raw label |
| `evidence_type` | present as `claim_type` | present | present | present | present |
| `applicability` | absent | absent | absent | wrong bucket fallback | wrong `primary` |
| `bucket` | absent | absent | `primary_ranked_results` | `primary` | present |
| `structural_score` | absent | absent | `score.total=0.0` | nested only | shown as normal zero |
| `structural_score_eligible` | absent | absent | native `false` | nested only | ignored |
| `reason_codes` | absent | absent | native gate codes | present with messages | first code only as main reason |
| `gate_trace` | absent | absent until gate evaluation | native dictionary | list projection | visible but incomplete comparison |
| original query | n/a | `original` input | `query.original` | `case_context.original` | flattened context only |
| normalized query | n/a | derived | `query.normalized` | `case_context` | flattened context only |
| parent record | parent ID | parent ID | parent ID + graph ID | explicit parent object | parent ID only in card |
| source unit | empty | empty | empty | `null` | generic missing value |
| provenance | present | preserved | preserved | `PARENT_ONLY` mapping | partial display |

## Invariants for the correction

The implementation must preserve these facts and must not infer missing values:

```text
core_gate_semantics_modified = false
scoring_semantics_modified = false
bucket_semantics_modified = false
corpus_modified = false
source_identifiers_invented = false
official_experiment_modified = false
```

The correction is therefore limited to a read-only presentation contract and
frontend rendering. Where the native result no longer exposes a source value,
the response must use `null` and identify the field as unavailable rather than
reconstructing it from a different semantic field.

## Post-correction contract check

The implemented adapter keeps the legacy top-level fields and adds three
explicit, nullable projections:

```json
{
  "claim": {
    "claim_text": null,
    "subject": null,
    "relation": null,
    "object": null,
    "biomarker": "EGFR L858R",
    "disease": "Lung Adenocarcinoma",
    "intervention": "gefitinib",
    "direction": "sensitivity",
    "structured_tuple_complete": false
  },
  "decision": {
    "bucket": "primary",
    "applicability": null,
    "structural_score": 0.0,
    "structural_score_eligible": false
  },
  "case_comparison": {
    "biomarker": {
      "query_value_original": "L858R",
      "query_value_normalized": "EGFR L858R",
      "claim_value": "EGFR L858R",
      "comparison_result": "exact",
      "not_applicable_reason": null,
      "availability": "AVAILABLE"
    },
    "intervention": {
      "query_value_original": [],
      "query_value_normalized": [],
      "claim_value": "gefitinib",
      "comparison_result": "no_intervention_constraint",
      "not_applicable_reason": "NOT_PROVIDED_BY_CASE",
      "availability": "NOT_PROVIDED_BY_CASE"
    }
  }
}
```

For the pilot, `claim_text` and the structured tuple remain `null` because
the repository does not provide them. The adapter reads the source repository
again only to project already-existing fields that the native result dropped;
it does not alter retrieval, gates, scoring, bucket assignment, corpus,
provenance identifiers, or experiment artifacts. `direction` is restored from
the source record as `sensitivity`, while the direction gate remains separately
exposed as `comparison_result=not_constrained`.

## Manual parity checks before commit

The previous manual EGFR/osimertinib run was replayed with its exact original
payload, not with the earlier exploratory variant:

```json
{
  "query_id": "manual-03-egfr-limitation",
  "gene": "EGFR",
  "alteration": "L858R",
  "biomarker": "",
  "disease": "Non-Small Cell Lung Cancer",
  "interventions": ["osimertinib"],
  "direction": "sensitivity",
  "result_limit": 50
}
```

The current response is exactly equivalent on retrieval semantics:

| Check | Previous manual | Current replay |
|---|---:|---:|
| Primary | 3 | 3 |
| Warning | 0 | 0 |
| Audit claims | 1 | 1 |
| Rejected claims | 144 | 144 |
| Primary scores | 108, 108, 108 | 108, 108, 108 |
| Primary claim IDs | `CLM-382985ec558808784e70`, `CLM-d4bee44e07efb6ccca9f`, `CLM-1ee5f9a16a678cebf993` | identical |
| CaseContext | original and normalized values identical | identical |

Therefore the warning card observed in an earlier check was not an additional
claim or a regression. That check used `disease="Lung Adenocarcinoma"`, which
is not the manual payload and legitimately produces a different result.

For the exact RMI2 payload, the response has zero primary claims, zero warning
claims, `abstention=true`, and all 148 claim records are rejected. The V3
Dossier renders the abstention notice before the excluded-candidate section;
different-biomarker claims are therefore candidates in `rejected`, never
clinical primary results.
