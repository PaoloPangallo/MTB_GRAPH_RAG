# Deprecated claim policy

Deprecated claim-shaped records are `candidate_kind=claim` but
`claim_status=deprecated`; they are not primary gold units. Their sealed
system bucket/status-gate fields may be retained in the audit for deterministic
promotion-rate analysis, but are never shown to reviewers and never become a
clinical gold label.
