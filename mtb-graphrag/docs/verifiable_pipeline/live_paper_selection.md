# LIVE document-aware bounded evidence selection

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

The LIVE runtime does not implement an independent `Paper Selection` stage
followed by a separate global passage selector. The actual sequence is:

```text
resolved document associations
  -> SourceUnit selection for each resolved document
  -> discard documents with no usable selected SourceUnits
  -> retain at most 2 documents per association
  -> pass selector top-K (5) SourceUnits per retained document
```

The implementation is `retrieval/live_sourceunit_selection.py` and is called
from the modern orchestrator. It does not read frozen
`available_bundles[*].source_unit_ids` in LIVE mode.

## Deterministic bounds

| Bound | Value | Implementation |
|---|---:|---|
| associations per case | 3 | `retrieval/kg_retrieval.py` |
| documents per association | 2 | `MAX_PAPERS_PER_ASSOCIATION` |
| SourceUnits selected per document | 5 | `LIVE_SELECTOR_TOP_K` |
| SourceUnits exposed upstream per document | 4 where the retrieval bundle is materialized | `MAX_SOURCE_UNITS_PER_DOCUMENT` |

The last two bounds apply at different boundaries: the LIVE selector ranks the
parsed units of each resolved document with `top_k=5`, while the retrieval
bundle representation has its own upstream cap. They must not be described as
one global `top-K` operation.

## Ordering and exclusions

Resolved records are ordered deterministically by full-text availability,
document identifier and bundle identifier. Duplicate document identifiers,
documents without usable text, selector failures and documents beyond the
two-document bound are retained as explicit exclusion records with reason
codes. No gold label is used to choose the context.

The bounded mechanism is therefore the object evaluated by the final protocol:
document-aware bounded evidence selection, not two independent LIVE selectors.

## LLM boundary

Selection completes before the Paper Context Enricher is called. The Enricher
receives only the bounded SourceUnit context and can return `QUOTE` or
`ABSTAIN`; it cannot request additional documents or units.
