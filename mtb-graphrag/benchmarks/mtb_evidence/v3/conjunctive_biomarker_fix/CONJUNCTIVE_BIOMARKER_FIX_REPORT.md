# Conjunctive biomarker matching correction

## Scope

This is a technical, no-gold correction of native biomarker candidate
generation. It does not change the qualification corpus, disease
normalization, intervention adaptation, terminology mappings, scoring weights,
thresholds, or frozen evaluation outputs.

The frozen source state is
`7d4c623709c01ee69467c8ec615841de745f279e`. The production correction is
commit `acba844`.

## Demonstrated defect

The previous production path flattened gene and alteration into
`query.biomarker_keys()` and accepted a statement when **any** key occurred in
one concatenated biomarker string. For the frozen ALK-G1202R query this meant
that an `ALK` match compensated for a different or absent alteration.

The frozen audit contained 32 V3 candidates:

- 9 statements contained the requested G1202R alteration;
- 23 statements matched ALK only;
- all 23 gene-only statements were already classified as
  `normalization_overreach`.

No gold record was used to establish the defect or decide the correction.

## Corrected contract

- A query containing only a gene uses `gene_level` matching.
- A query containing a gene and an alteration defaults to
  `alteration_specific`.
- Alteration-specific matching requires `gene_match AND alteration_match`.
- A matching gene cannot compensate for a different or missing alteration.
- A matching alteration cannot compensate for a different gene.
- Multiple query biomarkers retain their gene-alteration pairing; dimensions
  from different markers cannot cross-match.
- Protein-variant sets and their `single`, `compound`, or `deletion` shape must
  agree, so a shared token cannot collapse structurally different alterations.
- Gene prefixes are removed symmetrically for literal generic alterations such
  as `EGFR exon 19 deletion`; this is syntactic parsing, not synonym expansion.
- There is no automatic fallback from `alteration_specific` to `gene_level`.
- Pending terminology mappings are not consulted by candidate generation and
  therefore cannot become exact matches.

Normalization is syntactic only. Protein-change tokens such as `G1202R` are
compared exactly after case/space normalization. Parenthetical granularity
text does not change that token. A slash in the query, as in
`Fusion/Rearrangement`, is treated as two alternatives explicitly written in
the query; it does not introduce a synonym.

## Candidate-set diff

| Query | Before | After | Removed | Preserved | Added |
|---|---:|---:|---:|---:|---:|
| ALK-G1202R | 32 | 9 | 23 | 9 | 0 |
| EGFR-L858R | 17 | 10 | 7 | 10 | 0 |
| FGFR2-iCCA | 1 | 1 | 0 | 1 | 0 |
| RMI2 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **50** | **20** | **30** | **20** | **0** |

Every removed record has the reason code
`ALTERATION_MISMATCH_WITH_MATCHING_GENE` and records query gene, query
alteration, statement gene, and statement alteration. A missing statement
alteration is serialized explicitly as `<missing>`.

### ALK-G1202R

The 23 previously audited gene-only matches were removed. The nine statements
with native G1202R tokens were preserved:

`ES-V2-evidence-100000`, `ES-V2-evidence-100001`,
`ES-V2-evidence-100002`, `ES-V2-evidence-100003`,
`ES-V2-evidence-100004`, `ES-V2-evidence-100005`,
`ES-V2-evidence-1345`, `ES-V2-evidence-1352`, and
`ES-V2-evidence-441`.

A review pass additionally verified that multi-biomarker pairs cannot mix, and
that single, compound, and deletion forms remain distinct even when they share
a protein-change token.

Candidate validity and ranking policy were not changed: for example, a
preserved G1202R statement can still be audit-only for an independent
qualification reason.

### EGFR-L858R

Seven statements with EGFR but without L858R were removed by the same technical
rule. Ten statements with L858R were preserved. This is the only non-ALK
candidate-set change and is an expected application of the same contract.

### FGFR2-iCCA and RMI2

FGFR2 remains 1 because the frozen query explicitly declares
`Fusion/Rearrangement` and the statement carries the native `fusion` type.
RMI2 remains 0. Neither query has an unexpected change.

## Pending terminology mappings

The matcher does not read the terminology mapping index. `copy-number gain`
does not become exact `amplification`, and pending development-code mappings do
not participate in native biomarker identity.

## Integrity and determinism

The manifest authenticates:

- qualification corpus aggregate
  `bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827`;
- scoring config canonical hash
  `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`;
- 70 second-review packets aggregate
  `6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6`;
- prior exploratory results aggregate
  `f0ca36d81024170a5fe51b32763333468091a1d3b3a15f822bf57694c7f711cd`;
- prior candidate audit aggregate
  `43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273`;
- gold bundle identity
  `05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133`.

Two generations, including reversed query input, produce byte-identical
artifacts. Ordering is by query ID and statement ID. No local path, timestamp,
network call, Neo4j query, LLM call, tuning, or random value enters the output.

## Deliberately unresolved

Disease normalization differences for EGFR and FGFR2 remain open and were not
changed. The multi-intervention adapter decision, including broader V2
traversal behavior, also remains open. These questions require separate
read-only review before a full exploratory rerun.
