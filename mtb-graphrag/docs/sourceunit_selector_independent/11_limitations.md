# Limitations

The corpus has 20 pairs rather than a larger 25–30 pair set. It has no TABLE_CELL or TABLE_CAPTION units and no `Does Not Support` candidate with an intervention. Gemma was unavailable, so downstream fidelity cannot be assessed here.

The relevance gold is a single protocol pass and is not double-adjudicated. The selector retains duplicate IDs as separate input rows; permutation behavior is stable, but duplicate semantics deserve a later explicit policy. Generic alteration labels and drug aliases remain under-tested.

No tuning was performed after gold freeze. The result should not be converted into a production threshold or runtime change.
