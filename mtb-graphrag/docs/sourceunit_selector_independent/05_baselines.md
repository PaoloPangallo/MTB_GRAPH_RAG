# Baselines

Baseline A is the first K parser units. Baseline B is BM25-only with a query built from GCA features. The proposed method is the existing deterministic feature-aware selector with section prior and clinical feature bonuses.

All three rankings use the same fresh SourceUnits and the same frozen GCA. No baseline was changed after inspecting the independent gold. Metrics are reported at K=1, 3, 5 and 10 in the JSON artifacts.
