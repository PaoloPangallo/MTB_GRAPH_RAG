# Candidate universe policy G1.1

The primary universe is the intersection of candidate_kind=claim, active
claim status, frozen repository membership, and schema evaluability. It is
derived independently for every query. Deprecated claim-shaped records are
not silently treated as non-claims: they are retained in the deprecated audit
and excluded from the clinical gold. Containers and unresolved/unsupported
associations are likewise retained in their dedicated audits.

The exhaustive claim criterion is satisfied only when all active repository
claim IDs occur once per query and no active claim ID is extra or missing.
