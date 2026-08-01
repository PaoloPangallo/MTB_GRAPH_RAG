# Gold annotation protocol G1.0

G1.0 is a blinded, independent annotation protocol for the frozen V3
candidate universe. It creates no labels automatically and is frozen before
reviewer labeling begins.

## Scope and unit

The unit is exactly `(query_id, claim_id)`. Reviewer packets contain claim
and query context only. System prediction, score, rank, reason code, gate
trace, run identity, system identity, and semantic hashes are excluded.

Active corpus claims are packetized for every frozen query. Provenance
containers, unresolved/unsupported association records, and out-of-corpus
records remain in the audit file but are excluded from the primary annotation
universe.

## Buckets

- **primary:** directly compatible with domain, biomarker logic, disease
  scope, intervention/formulation, direction, regimen/separability and the
  required qualifiers.
- **warning:** pertinent but explicitly limited by scope, population,
  formulation, regimen, aggregate result, preclinical setting, or conditional
  applicability.
- **audit:** useful for traceability or review but not suitable for the
  primary result because mapping, relation, separability, qualification, or
  applicability is insufficient.
- **rejected:** incompatible with one or more structural query requirements
  and must not be promoted.

`unknown`, `unresolved`, `not_applicable`, `not_separable`, `source_missing`,
and `provenance_incomplete` are dimensions or rationale states, not automatic
bucket substitutions. In particular, missing source does not automatically
mean rejected.

## Required reviewer response

Each response must validate against `annotation_schema_g1_0.json`. A reviewer
must provide evaluable, bucket (or null when not evaluable), source checks,
dimension statuses, uncertainty, rationale codes, and protocol version.

## Independence and adjudication

Reviewer A and Reviewer B work independently and do not see predictions or
each other's work. Adjudicator C receives only the unit, both annotations,
the source context, and this rubric. Agreement is reported after both
reviews; it never changes this protocol retrospectively.

The four pilot cases are calibration-only and are excluded from G1.0 units.
