# Architecture of the evaluated Protocol 1.7 runtime

This document is the canonical architecture description for the runtime that
was evaluated. It does not describe a second user-selectable replay mode.

## Operational path

```text
clinical text
  -> LLM CaseContext Parser
  -> deterministic CaseContext verification and eligibility
  -> GCA retrieval (maximum 3 associations per case)
  -> provenance/document identifiers
  -> cache-first DocumentRuntime.open()
  -> authorized acquisition on cache miss
  -> persisted document snapshot
  -> deterministic document parser
  -> SourceUnits
  -> LIVE document-aware SourceUnit selection per resolved document
  -> bounded document set (maximum 2 documents per association)
  -> bounded SourceUnit context (selector top-K = 5 per document)
  -> LLM Paper Context Enricher (QUOTE or ABSTAIN)
  -> deterministic literal quote validation
  -> accepted validated AuthorContext
  -> deterministic gates
       [verified query_intent + GCA + validated AuthorContext]
  -> canonical structured dossier
  -> deterministic NarratorInput
  -> LLM Dossier Narrator
  -> deterministic Narrative Verifier
  -> verified narrative or structured fallback
```

The runtime entry point is `RunStore.start()`, which opens
`DocumentRuntime.open()` and invokes the modern orchestrator. `pipeline.run_case`
is retained as a legacy/reference pilot and is not the canonical API route.

## Selection semantics

The LIVE code does not expose an independent paper selector followed by a
separate global passage selector. It resolves document associations, selects
SourceUnits for each resolved document, discards documents with no usable
selected units, and then applies the bounded document set. Ordering is
deterministic: full text is preferred, then document and bundle identifiers;
the implementation caps the selected documents at two and calls the
deterministic SourceUnit selector with `top_k=5`.

The research/regression replay harness is separate. It may use frozen recorded
artifacts, but it is not an operational fallback and is not silently reachable
from the LIVE API.

## Typed gate boundary

The gate boundary is:

```text
verified query_intent + GCA candidate + accepted validated AuthorContext
  -> deterministic gate status
```

Free-form LLM output never mutates canonical state directly. A literal quote
can be documentarily valid while still lacking sufficient decision-level
semantic support. Accordingly, the conservative runtime distinguishes
`AMBIGUOUS` when no validated enrichment reaches the gate from `PARTIAL` when
validated evidence is insufficient or carries a warning. Documentary validity
and decision-level evidentiary classification are different properties.

## LLM roles and deterministic controls

The three LLM roles are limited to:

- **UNDERSTAND** — CaseContext Parser;
- **EXTRACT** — Paper Context Enricher;
- **COMMUNICATE** — Dossier Narrator.

The document resolver, parser, SourceUnit selector, quote validator, gates,
eligibility and Narrative Verifier are deterministic control or verification
components, not additional LLM stages.

This positioning is authority-separated evidence orchestration: LLMs perform
linguistic tasks, while provenance, state transitions, evidence admission and
presentation boundaries remain explicit and deterministic. The evaluation
measures bounded evidence selection and canonical-state controls; it does not
claim an independent LIVE paper selector, perfect reliability, or a safety
guarantee from the Narrative Verifier.
