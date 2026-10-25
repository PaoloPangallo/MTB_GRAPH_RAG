# Frozen selector evaluation

The selector version was `deterministic-sourceunit-selector/1.0`, copied unchanged from the evaluation base commit `632cf2ff392e22d19c6110d296163f7b4073e5f4`.

No weight, tokenizer, BM25 parameter, section prior, threshold, normalization or top-K logic was changed after gold freeze. The evaluator passes only the candidate feature fields, document ID and fresh SourceUnits. Gold is loaded by the outer metric layer after the ranking is produced.

The selector beat first-K and BM25 on the primary direct-relevance HitRate@5 and Recall@5. This is evidence for automatic document-to-evidence routing, not evidence of semantic support.
