# Recommended document model

Proposta non implementata nel runtime. La regola principale è separare il
collegamento a una pubblicazione dal supporto della claim.

```json
{
  "PublicationRecord": {
    "publication_id": "PMID:30420614",
    "pmid": "30420614",
    "doi": null,
    "title": "...",
    "year": 2019,
    "journal": "British journal of cancer",
    "publication_type": ["Clinical Trial, Phase II", "Journal Article"],
    "metadata_origin": "local_source_metadata_cache",
    "abstract": {"text": "...", "sha256": "...", "origin": "local_source_abstract_cache"}
  },
  "EvidencePassage": {
    "passage_id": "EP-...",
    "publication_id": "PMID:30420614",
    "text": "...",
    "locator": {"type": "ABSTRACT", "section": "CONCLUSION"},
    "origin": "abstract",
    "exact_text": true
  },
  "ClaimDocumentLink": {
    "claim_id": "CLM-...",
    "publication_id": "PMID:30420614",
    "publication_link_status": "parent_candidate",
    "source_unit_id": null,
    "link_origin": "parent_source_ids"
  },
  "ClaimSourceAssessment": {
    "claim_id": "CLM-...",
    "passage_id": "EP-...",
    "support": "partial",
    "supported_fields": ["biomarker", "disease", "direction"],
    "unsupported_fields": ["intervention_canonicalization"],
    "applicability": "candidate_only",
    "deterministic_result": "PARTIAL_SUPPORT",
    "llm_result": null
  }
}
```

## Stati consigliati

- `publication_link_status`: `claim_linked | parent_candidate`;
- `support`: `direct | partial | context | contradicted | none`;
- `locator.type`: `ABSTRACT | FULL_TEXT_OFFSET | SOURCE_UNIT_LOCATOR`;
- `origin`: `abstract | full_text | source_unit`.

`ClaimDocumentLink` non deve scrivere automaticamente `ClaimSourceAssessment`.
L'assessment richiede un passaggio reale e conserva gli elementi supportati e
non supportati. Un futuro verifier può aggiungere un risultato LLM strutturato,
ma deve mantenere il risultato deterministico e il testo/prompt/output separati;
qui non è stato necessario usarlo.
