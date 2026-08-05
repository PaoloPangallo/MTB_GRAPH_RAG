# V3 claim contract correction design

**Status:** approved by the user on 2026-08-01.

## Goal

Make the V3 response and card presentation faithful to source claim data and
native gate/scoring data, especially for `CLM-e565f65d73cb1d4aa67b`, without
changing retrieval semantics.

## Design

The presentation adapter remains the semantic boundary. It will read the
already-promoted source record through the existing read-only corpus loader
only to recover optional source fields that were lost before the native result
(`direction`, and any future real `claim_text` or structured tuple fields).
The adapter will copy fields only when they exist; it will never derive a
claim sentence, triple, applicability, score, bucket, or source identifier.

The response keeps all existing top-level fields and adds explicit nullable
objects:

```json
{
  "claim": {
    "claim_text": null,
    "subject": null,
    "relation": null,
    "object": null,
    "structured_tuple_complete": false
  },
  "decision": {
    "bucket": "primary",
    "applicability": null,
    "structural_score": 0,
    "structural_score_eligible": false
  },
  "case_comparison": {
    "biomarker": {
      "query_value_original": "L858R",
      "query_value_normalized": "EGFR L858R",
      "claim_value": "EGFR L858R",
      "comparison_result": "exact",
      "not_applicable_reason": null
    }
  }
}
```

The legacy `score` and `gate_trace` fields remain unchanged for compatibility;
the new objects are projections around them. Applicability is `null` when the
native result does not evaluate it separately. A bucket value is never used as
its fallback.

Each comparison row distinguishes `NOT_PROVIDED_BY_CASE`, `MISSING_IN_CLAIM`,
`NOT_APPLICABLE`, `NOT_EXPOSED_BY_GATE`, and `AVAILABLE`. Direction has three
separate values: case request, source claim direction, and gate comparison.
`not_constrained` is rendered as “Non vincolata dal caso” and cannot become the
card title.

Score display reads the native `score.total` and native eligibility separately:
eligible scores show the real value, ineligible scores show “Non applicabile”,
and a null score shows “Non disponibile”. A tooltip states that the structural
score is not a clinical probability.

Claim title fallback is source claim text, complete source triple,
biomarker/direction/intervention, then claim ID plus
“Tripla strutturata non disponibile nel record sorgente”.

## Testing and verification

Backend tests will exercise source recovery, null preservation, comparison
states, score eligibility, applicability/bucket distinction, and preservation
of native provenance and gate trace. Frontend tests will exercise the card
fallback hierarchy, explicit case context, comparison labels, translated
direction, score states, reason-code gate provenance, and absence of the raw
`not_constrained` title.

The four requested direct queries will be run against the live local endpoint
after the tests, and screenshots will be captured from the updated V3 view.
No corpus, retriever gate, scoring, bucket, ledger, gold, or official
experiment file is in scope for modification.

