# ESCAT extraction log

## Method

The extraction was performed offline from the single local PDF source. The
source hash was verified before loading the JSON artifact. Text extraction was
checked page by page with the PDF text tools; the PDF layout was also rendered
for page-level inspection. No web source, legacy interpreter, LLM output, or
unstated domain knowledge was used.

## Locator convention

All locators are one-based and preserve both numbering systems:

| Field | Meaning |
|---|---|
| `page_pdf` | physical page number in `Mateo.pdf` |
| `page_journal` | printed Annals of Oncology page number |
| `section` | visible paper section or subsection |
| `table` | table identifier when applicable |
| `figure` | figure identifier, or `null` when absent |

Table 2 is at PDF page 4 / journal page 1898. The narrative descriptions for
Tier I are at PDF page 2 / journal page 1896; Tier III is discussed on PDF
pages 5–6 / journal pages 1899–1900; Tier IV, V and X are discussed on PDF page
6 / journal page 1900.

## Ambiguity policy

The paper uses qualitative expressions that are not operationalised in the
source. Each such condition is represented as an atomic requirement with
`manual_interpretation_required: true`. The separate `ambiguities.json` file
records the phrase, locator and handling rule. This extraction intentionally
does not manufacture thresholds or translate those phrases into executable
boolean tests.

## Output inventory

- `ruleset.json`: versioned `RESEARCH_DRAFT` ruleset.
- `source_verification.json`: hash and source verification record.
- `ambiguities.json`: separate ambiguity registry.
- `draft_comparison_read_only.json`: non-mutating comparison with the 15 pilot drafts.
