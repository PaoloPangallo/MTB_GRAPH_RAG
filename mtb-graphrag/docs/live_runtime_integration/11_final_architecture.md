# Final architecture

```text
clinical text
  -> CaseContext Parser
  -> deterministic eligibility and KG retrieval
  -> GraphCandidateAssertion provenance
  -> DocumentRuntime
       -> cache hit
       -> authorized API miss, persist snapshot
  -> canonical parser
  -> SourceUnits
  -> frozen deterministic SourceUnit Selector (K=5)
  -> Paper Context Enricher V2 / Gemma
  -> deterministic quote validator
  -> canonical gates/status
  -> dossier
  -> narrator and narrative verifier
```

REPLAY branches before acquisition and uses frozen document/bundle artifacts.
