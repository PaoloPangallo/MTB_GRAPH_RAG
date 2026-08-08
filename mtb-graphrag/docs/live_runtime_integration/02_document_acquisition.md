# Document acquisition

The clinician supplies clinical text only. PMID, PMCID, and NCT values come from the GraphCandidateAssertion provenance.

Authorized sources are NCBI PubMed E-utilities, PMC OAI, and the existing ClinicalTrials.gov API adapter. Generic search, paper substitution, LLM browsing, and manual identifier input are outside the runtime contract.

Each resolved document carries the requested identifier, actual resolved identifier, source, retrieval mode, timestamp, raw payload hash, payload size, relative cache path, resolver version, and degradation reason where applicable.
