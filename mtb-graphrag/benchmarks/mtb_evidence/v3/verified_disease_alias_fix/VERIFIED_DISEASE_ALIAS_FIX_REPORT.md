# Verified disease alias matching correction

## Scope

This correction changes only the native disease match used by
`QualifiedEvidenceRetriever`. It does not change the qualification corpus,
scoring configuration, conjunctive biomarker matcher, multi-intervention
adapter, or any frozen evaluation output.

The comparison is no-gold. The external bundle was authenticated by its frozen
SHA-256 inventory but its records were not loaded.

## Demonstrated gap

The previous candidate generator compared the normalized statement label with
`QualifiedRetrievalQuery.disease_keys()`. That query method placed the primary
disease and every query alias in one undifferentiated set.

This caused two opposite errors:

1. `Advanced/metastatic NSCLC` did not match the locally verified vocabulary
   form `Lung Non-small Cell Carcinoma`.
2. `Lung Adenocarcinoma` was admitted because it appeared in the query alias
   list, even though the local disease model classifies it as an explicit child
   of NSCLC rather than an equivalent alias.

## Implemented contract

`DiseaseMatchResult` records raw and normalized labels, available canonical
identifiers, canonical disease key, match category, hard-match permission,
alias or relation source, matcher version, warning code, and explanation code.

Only these categories satisfy the hard native disease constraint:

- `exact_string`
- `normalized_exact`
- `verified_alias`

These categories remain visible for audit and do not satisfy the hard
constraint:

- `explicit_parent`
- `explicit_child`
- `explicit_sibling`
- `pan_cancer_or_unspecified`
- `unresolved`
- `incompatible`

The verified alias source is the pre-existing local table
`benchmarks/mtb_evidence/pilot/audit_lib/disease.py::_SYNONYM_GROUPS`, versioned
by the retriever as `verified-local-disease-aliases/1.0`. No synonym was added.
In particular, `Lung NSCLC` is not present in that frozen table and was not
promoted by this change.

## Candidate-set diff

| Query | Before | After | Added | Removed | Preserved | Unexpected |
|---|---:|---:|---:|---:|---:|---:|
| ALK-G1202R | 9 | 9 | 0 | 0 | 9 | 0 |
| EGFR-L858R | 10 | 32 | 32 | 10 | 0 | 0 |
| FGFR2-iCCA | 1 | 1 | 0 | 0 | 1 | 0 |
| RMI2 | 0 | 0 | 0 | 0 | 0 | 0 |

The EGFR change is not a net-only expansion. The 10 prior statements were
`Lung Adenocarcinoma` child-disease records and are now correctly withheld by
the strict alias-only policy. The 32 added statements are the independently
derived alias-safe set from the frozen disease review. All 32 use
`verified_alias`; all 10 removals are expected hierarchy-not-applied outcomes.

Unexpected candidate additions: **0**.

Unexpected candidate removals: **0**.

## Required evidence records

- `evidence:11219`: biomarker L858R compatible; disease is a verified NSCLC
  alias; now in the primary candidate set.
- `evidence:11598`: disease alias compatible; T790M plus exon 19 deletion does
  not satisfy the L858R query; first failure remains biomarker.
- `evidence:11599`: disease alias compatible; compound L858R plus T790M does
  not equal single L858R; first failure remains biomarker.
- `evidence:1867`: disease alias compatible; T790M does not satisfy L858R;
  first failure remains biomarker.
- `evidence:8173`: FGFR2 fusion compatible; disease is the explicit sibling
  `Cholangiolocellular Carcinoma`; it remains outside the primary candidate
  set and is audit-visible.

The exclusion audit exposes
`BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS` as a supplemental explanation
without replacing the alteration-specific first-failure code.

## Hierarchy deliberately not applied

`Lung Adenocarcinoma` remains `explicit_child`, `Cholangiocarcinoma` remains
`explicit_parent`, and `Cholangiolocellular Carcinoma` remains
`explicit_sibling`. These relations are represented and explained, but none is
used as a hard match.

No ontology-aware inclusion, broad-soft retrieval, hybrid V2/V3 retrieval,
fallback disease matching, cross-disease expansion, or hierarchy scoring was
implemented.

## Integrity and determinism

- qualification corpus aggregate:
  `bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827`
- qualification corpus fingerprint:
  `99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd`
- frozen KG fingerprint:
  `ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae`
- scoring config file SHA-256:
  `57d76d377029ba5c92cf4785d8143e2d06d02b6dc0e0c1d7ef57ea118e553fd4`
- scoring config canonical hash:
  `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`
- local disease normalizer file SHA-256:
  `7e3ab30006ba9c7ccdc80b1d2a4bd544159b3fa0044aee87e3501847986593b7`
- canonical disease alias/hierarchy tables SHA-256:
  `6372a0b0f4b24e505266bd061d3997e75aee9cde4a01558ea57e9c3755c9abd4`
- gold bundle aggregate:
  `05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133`
- second-review packet count: 70
- unexpected changes: 0

Rows are sorted by query ID and statement ID. Reversing query input order
produces byte-identical JSON artifacts. Outputs contain no machine-specific
paths.

## Remaining boundaries

The multi-intervention adapter remains unresolved. Disease hierarchy remains a
separate architectural policy decision. Therefore this correction is ready
for a read-only multi-intervention review, but not for a full exploratory
rerun.
