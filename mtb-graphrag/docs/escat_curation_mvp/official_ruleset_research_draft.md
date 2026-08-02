# ESCAT ruleset research draft

This branch formalises a traceable research artifact from the local source
`../Mateo.pdf`. It is deliberately classified as `RESEARCH_DRAFT`; it is not a
clinically validated production ruleset and it does not curate any claim.

## Source boundary

- Source: `C:\Users\paolo\Desktop\IspezioneDatasetTesi\Mateo.pdf`
- SHA-256: `56660fd9c3d929a3f2e2744ca3b53687cff0954f609e65d267c1bb3b94c3c910`
- Size: 155821 bytes
- PDF pages: 8
- Journal pages: 1895–1902
- Citation: Mateo et al., *Annals of Oncology* 29:1895–1902 (2018)
- DOI: `10.1093/annonc/mdy263`
- Copying: the PDF is not copied into the repository.

The primary extraction locator is Table 2 on PDF page 4 / journal page 1898.
Narrative locators are retained where the paper explains the same tier in more
detail. The source contains no pertinent figure; all rule locators therefore
use `figure: null`.

## Formalised rules

The JSON contains the 11 categories explicitly described by the paper:

`ESCAT-I-A`, `ESCAT-I-B`, `ESCAT-I-C`, `ESCAT-II-A`, `ESCAT-II-B`,
`ESCAT-III-A`, `ESCAT-III-B`, `ESCAT-IV-A`, `ESCAT-IV-B`, `ESCAT-V`, and
`ESCAT-X`.

Each rule stores atomic evidence requirements. Every condition is marked
`manual_interpretation_required: true` because Mateo et al. do not provide an
operational threshold for the relevant qualitative language. No numeric
threshold, study-count threshold, response-rate threshold, effect-size
threshold, or surrogate criterion was added.

The separate `ambiguities.json` registry records phrases such as “clinically
meaningful benefit”, “similar benefit”, and “objective responses”. These remain
manual curation obligations and are not converted into executable thresholds.

## Read-only comparison

`draft_comparison_read_only.json` contains 15 entries. For every entry it
preserves the source status, tier, and subtier, reports the existing missing
requirements, and records:

- `selected_rule_ids: []`;
- `assigned_tier: null`;
- `assigned_subtier: null`;
- `candidate_rule_status: HUMAN_REVIEW_REQUIRED`.

This is a comparison snapshot, not a curation operation. It does not append
assessment events and does not modify `pilot_drafts.jsonl`.

## Separation from validation and runtime

The existing `TEST_FIXTURE_ONLY` ruleset remains the only fixture used to test
validator mechanics. It is not imported into this document and no fixture tier
is represented as a scientific evaluation.

The research draft is not exposed through the V3 endpoint and is not wired into
runtime scoring, gates, buckets, ordering, the qualified-claim repository,
knowledge graph, or official ledgers. A future clinical ruleset would require
independent review, version approval, and explicit promotion before any runtime
consumer could use it.
