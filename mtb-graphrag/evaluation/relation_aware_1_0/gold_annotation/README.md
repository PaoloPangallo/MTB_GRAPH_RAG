# Human gold annotation pack

This pack contains the 16 frozen PAPER_EVIDENCE candidates and their frozen source documents/SourceUnits. It is an empty annotation instrument: no gold decision, support result, Reader output, selector output, or previous evaluation result is included.

## Annotation question

For each candidate, answer: **does the associated document really support the relation represented by the KG, and with what specificity?** Read the candidate and all SourceUnits before filling the form.

## Overall labels

- `FULL_SUPPORT`: all necessary candidate elements are supported with sufficient specificity.
- `PARTIAL_SUPPORT`: the source supports a more general relation or only part of the candidate.
- `NO_SUPPORT`: the source does not support the candidate relation.
- `CONTRADICTORY`: the source states something incompatible with the candidate.
- `UNVERIFIABLE`: the frozen document does not allow a reasoned decision.

## Field labels

For disease/context, gene, alteration, drug, direction, and evidence type, use `YES`, `NO`, or `NOT_APPLICABLE` only after annotation. `NOT_APPLICABLE` is not `NO`: for example, a diagnostic candidate with no drug may have `drug_supported=NOT_APPLICABLE`.

- Disease/context: is the requested disease or context covered?
- Gene: is the gene explicitly supported?
- Alteration: is the specific variant/alteration supported, not merely the gene?
- Drug: is the requested drug or regimen supported?
- Direction: does sensitivity, resistance, non-support, or another direction match?
- Evidence type: does the source document the predictive, diagnostic, prognostic, or other nature represented by the candidate?

## Quotes

Record a short literal quote from the frozen SourceUnits and the corresponding `source_unit_id` values. The quote must be present verbatim in the displayed SourceUnits; multiple units may be used when one is insufficient.

## Independent review

Complete `annotation_primary.json` and `annotation_review.json` independently. The reviewer must not see the primary annotation before completing the review. Do not create a final gold file in this phase. Disagreements will be adjudicated separately.

## Order

The stable sample IDs remain unchanged. The independent annotation order is stored in `annotation_index.json` and was generated with `ANNOTATION_ORDER_SEED=20260825`.

## Provenance

- Candidate sample SHA256: `d168027b5e4994109c9cf1975a8d27bddcd214ae7d46a077a0aa4af594cc3233`
- Source snapshot manifest SHA256: `15760611300ce0a1e605e7323265209db7da1870f7f0ecb58847e78907ebb942`
- No external calls were made while preparing this pack.
