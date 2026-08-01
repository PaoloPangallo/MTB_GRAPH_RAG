# G1.1 active-claim gold protocol

G1.1 supersedes G1.0 before annotation. It separates the clinical
applicability universe from lifecycle, provenance, and association audit
records without changing V3, its queries, or its frozen outputs.

The primary coverage mode is `exhaustive_active_claim_universe`. A primary
unit is exactly `(query_id, claim_id)` where the candidate is a claim, its
status is active, its ID is in the frozen qualified claim repository, and the
record conforms to the annotation schema. Deprecated claims, provenance
containers, unresolved associations, unsupported associations, malformed
records, and non-evaluable records remain in separate audit files and receive
no clinical bucket.

The expected active universe is derived from the corpus and output files, not
hardcoded: 148 active claims per query and 3,256 units total. Reviewers see
only the blind claim/query/source context. Predictions, scores, ranks, system
identities, run identities, reason codes and gate traces are prohibited.

G1.1 freezes the independent-review workflow but creates no gold labels.
