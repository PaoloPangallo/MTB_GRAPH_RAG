# Architectural decision

Retrieval generalization is supported conditionally: on positive independent cases the selector is 9/9 at K=5 and beats first-K and BM25 HitRate@5. The independent 20-pair Gemma comparison shows identical GOLD and SELECTOR decisions, identical validated quote rate (4/20), identical abstain rate (16/20), and no validator safety regression. The zero-direct behavior is not a support decision and has no abstention threshold. LIVE integration remains blocked only by annotation uncertainty: the second annotation was protocol-based rather than a second human reviewer.
