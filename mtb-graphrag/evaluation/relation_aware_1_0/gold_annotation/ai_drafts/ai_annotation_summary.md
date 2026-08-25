# AI-assisted paper pre-annotation summary

These are AI_DRAFT annotations made only from the frozen candidate and source pack. They are not final gold and require author review.

| sample_id | candidate_id | disease | gene | alteration | drug | direction | evidence_type | overall_draft | uncertainty |
|---|---|---|---|---|---|---|---|---|---|
| PAPER-01 | GCA-eed9f53846f3cc651e23a469 | YES | NOT_APPLICABLE | NO | NOT_APPLICABLE | NO | NO | NO_SUPPORT | MEDIUM |
| PAPER-02 | GCA-ffe78f2cb067426d4baf225d | YES | NOT_APPLICABLE | NO | NOT_APPLICABLE | YES | YES | PARTIAL_SUPPORT | MEDIUM |
| PAPER-03 | GCA-ffb6a639dda7e2af9dc154e0 | YES | NOT_APPLICABLE | NO | NOT_APPLICABLE | YES | YES | PARTIAL_SUPPORT | MEDIUM |
| PAPER-04 | GCA-ffd2ba40df921cebf9d31e1a | NO | NOT_APPLICABLE | NO | NOT_APPLICABLE | NO | NO | NO_SUPPORT | LOW |
| PAPER-05 | GCA-ffc4f3959a383c945a0f1cc5 | YES | NOT_APPLICABLE | YES | NOT_APPLICABLE | YES | YES | PARTIAL_SUPPORT | HIGH |
| PAPER-06 | GCA-ffcd72c534472ec5090eea1f | YES | NOT_APPLICABLE | NO | NOT_APPLICABLE | YES | YES | PARTIAL_SUPPORT | MEDIUM |
| PAPER-07 | GCA-ffd6d386640e05d3b78a3031 | YES | NOT_APPLICABLE | NO | NO | NO | NO | NO_SUPPORT | LOW |
| PAPER-08 | GCA-ffdedde41ece1506673a5c0e | YES | NOT_APPLICABLE | YES | NOT_APPLICABLE | YES | YES | PARTIAL_SUPPORT | HIGH |
| PAPER-09 | GCA-ffe5c124fb0b3bb1335a4014 | YES | NOT_APPLICABLE | YES | NO | NO | YES | PARTIAL_SUPPORT | MEDIUM |
| PAPER-10 | GCA-fff42a22261e97c1160749e9 | YES | NOT_APPLICABLE | YES | NOT_APPLICABLE | YES | YES | FULL_SUPPORT | LOW |
| PAPER-11 | GCA-ff6bdc720cc1fcd9134bf399 | YES | NOT_APPLICABLE | YES | NOT_APPLICABLE | YES | YES | FULL_SUPPORT | LOW |
| PAPER-12 | GCA-ffbb1b3be5bd7e74024e8a2f | NO | NOT_APPLICABLE | NO | NOT_APPLICABLE | NO | NO | UNVERIFIABLE | HIGH |
| PAPER-13 | GCA-e7edb50600fc5996b63b35e4 | YES | NOT_APPLICABLE | YES | YES | YES | YES | FULL_SUPPORT | MEDIUM |
| PAPER-14 | GCA-fc343592a215c4ac9c9a1c43 | NOT_APPLICABLE | NOT_APPLICABLE | NO | YES | YES | YES | UNVERIFIABLE | HIGH |
| PAPER-15 | GCA-ff97755cefae20a730170d54 | YES | NOT_APPLICABLE | YES | YES | YES | YES | PARTIAL_SUPPORT | MEDIUM |
| PAPER-16 | GCA-fff906074758e0ee48366a8d | NO | NOT_APPLICABLE | YES | YES | YES | YES | PARTIAL_SUPPORT | MEDIUM |

## High-uncertainty cases

- **PAPER-05** — The source documents a predictive/aggressiveness context in lethal prostate cancer and describes molecular upregulation, but the candidate subject is only the unspecific label Overexpression and does not identify the molecular entity. The candidate has no explicit gene field.
- **PAPER-08** — The source supports a high/low biomarker-based predictive relation in the stated disease context, but the candidate subject is the unqualified label High and does not identify the measured biomarker. The candidate has no explicit gene field.
- **PAPER-12** — The frozen SourceUnit bundle contains only the title and a supplementary-material label. It does not provide enough frozen document content to make a motivated judgement about R238W, childhood ALL, or a prognostic relation. The candidate has no explicit gene field.
- **PAPER-14** — The frozen SourceUnit bundle contains only the title. It names a broad fluorouracil-toxicity topic but cannot establish the candidate DPYD*13 homozygosity, cancer context, or the required specificity. The candidate has no explicit gene field.

## Draft distribution

- FULL_SUPPORT: 3
- PARTIAL_SUPPORT: 8
- NO_SUPPORT: 3
- CONTRADICTORY: 0
- UNVERIFIABLE: 2
