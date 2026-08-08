# Architectural decision

Retrieval generalization is supported conditionally: on positive independent cases the selector is 9/9 at K=5 and beats first-K and BM25 HitRate@5. The zero-direct behavior is not a support decision and has no abstention threshold. LIVE integration is not approved yet because independent Gemma/validator downstream behavior was not measured and the second annotation was protocol-based rather than human.
