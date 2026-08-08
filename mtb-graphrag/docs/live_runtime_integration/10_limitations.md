# Limitations

The independent selector corpus contains 20 pairs, with 9 positive cases and a small number of positive PMC cases. The gold was annotated by one reviewer; no real second human annotation was available. The selector always returns top-k when units exist and has no learned rejection threshold. Gemma may abstain even when relevant units are present. API availability can affect cache misses, and raw PMC payload hashes can vary while parsed SourceUnit identity remains the downstream invariant.
