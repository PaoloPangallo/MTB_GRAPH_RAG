# Final decision

## Decision

`SOURCEUNIT_SELECTOR_GENERALIZES_WITH_LIMITATIONS`

The frozen selector generalizes to 20 unseen real GCA/document pairs with zero pilot overlap, zero selector gold access, zero invented SourceUnits, deterministic ranking drift zero under equivalent-input tests, and retrieval improvements over first-K and BM25 at the primary K=5/10 comparisons. It also reaches long PMC documents without a retrieval collapse.

It is not `SOURCEUNIT_SELECTOR_READY_FOR_LIVE_INTEGRATION` because independent Gemma/validator comparison was unavailable and the relevance annotation requires independent adjudication. The next step is to repeat the downstream sample with provider credentials and strengthen the annotation/corpus before designing runtime integration.
