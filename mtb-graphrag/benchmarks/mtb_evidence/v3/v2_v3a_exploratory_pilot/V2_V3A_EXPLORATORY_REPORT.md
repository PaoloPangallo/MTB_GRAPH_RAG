# V2 versus V3-A exploratory pilot

## Scope and freeze

This is a four-query exploratory comparison, not a final clinical evaluation.
Retrieval was completed and hashed before the read-only gold bundle was opened.
No tuning, network access, graph query, language model, or inferential test was
used.

- Historical V2 baseline:
  `benchmarks/mtb_evidence/pilot/audit/*/normalized_records.jsonl`
- V2 baseline hash: `900a2c6afb61be728cfbebfa5784aeeb87b6478a1bd4153cd044c7f89775f981`
- Corpus fingerprint: `99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd`
- Scoring hash: `ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00`
- Gold bundle hash: `05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133`

The historical V2 rows are frozen graph records in serialized order and have no
comparable numeric V3 score. `v2_compatibility` is therefore a technical
control, not a substitute for the historical baseline.

## Results by query

The ranking unit is a gold-claim projection matched on biomarker, intervention, direction, assertion polarity, and source. Disease, mandatory clinical qualifiers, applicability, and NCT identity are not part of this projection and are evaluated separately where supported. The gold does not assign
EvidenceStatement IDs, so statement-level precision and recall are not
computed.

| Query | Mode | Candidates | P@3 | R@3 | P@10 | R@10 | MRR |
|---|---|---:|---:|---:|---:|---:|---:|
| ALK G1202R | historical V2 | 13 | 0 | 0 | 0.10 | 0.333 | 0.125 |
| ALK G1202R | native_only | 32 | 0 | 0 | 0 | 0 | 0.059 |
| ALK G1202R | qualified_soft | 32 | 0.333 | 0.333 | 0.10 | 0.333 | 0.500 |
| EGFR L858R | historical V2 | 81 | 0 | 0 | 0 | 0 | 0.021 |
| EGFR L858R | native_only | 17 | 0 | 0 | 0 | 0 | 0 |
| EGFR L858R | qualified_soft | 17 | 0 | 0 | 0 | 0 | 0 |
| FGFR2 fusion | historical V2 | 28 | 0 | 0 | 0 | 0 | 0.043 |
| FGFR2 fusion | native_only | 1 | 0 | 0 | 0 | 0 | 0 |
| FGFR2 fusion | qualified_soft | 1 | 0 | 0 | 0 | 0 | 0 |
| RMI2 snapshot | all modes | 0 | 0 | n/a | 0 | n/a | 0 |

Across eight supported gold claims, micro R@10 is 0.125 for historical V2,
0 for `native_only`, and 0.125 for `qualified_soft`. Macro MRR is 0.0474,
0.0147, and 0.125 respectively. These values are descriptive and have very
small denominators.

At source level, micro PMID R@10 is 0.25 for historical V2, 0.125 for
`native_only`, and 0.125 for `qualified_soft`. At therapy level, micro R@10 is
0.75, 0.50, and 0.50. Source and therapy metrics are intentionally separate.

## Coverage and representation

V3-A does not preserve the historical V2 candidate coverage in this snapshot:
graph-evidence overlap is 9/13 for ALK, 17/81 for EGFR, 1/28 for FGFR2, and
0/0 for RMI2. The causes are representation and native matching differences;
the result is not repaired with synonyms or query expansion in this phase.

V3-A does improve explicit representation. Every retained result has
provenance; negative evidence stays negative; invalid evidence is audit-only;
profile units distinguish clinical, preclinical, and unresolved panels; and
pending terminology mappings never become exact.

## Qualifier effect

`native_only` and `qualified_soft` have the same complete native candidate
sets. Qualification changes 31 ranks and 19 unique query-candidate top-k memberships; 18 warned
results keep their rank. The frozen rule classifies this as substantial ranking
impact. However, only one gold-claim projection receives a qualifier
contribution. The apparent magnitude is driven largely by unresolved,
conflicting, partial, abstract-only, and not-separable penalties across
non-gold candidates, not by broad positive clinical qualification coverage.

## Structural checks

- PMID 31358542: `ES-V2-evidence-100003`/brigatinib is audit-only,
  `ES-V2-evidence-100004` is partial with warning, and the active corpus has no
  false preclinical unit for the source.
- PMID 22235099: clinical and preclinical profile units remain distinct; the
  H3122/KRAS experiment remains `does_not_support`; CUTO-1 non-inheritance is
  verified; no case-level or named-patient frequency is inferred.
- PMID 23344087: the preclinical panel remains not-separable and abstract-only;
  less-sensitive is not exact complete resistance, copy-number gain is not
  exact amplification, and the EGFR L858R confounder remains visible.
- PMID 22277784: clinical and Ba/F3 units remain distinct, clinical population
  non-propagation is verified, CH5424802/alectinib remains pending, and no
  complete-resistance claim is introduced.
## Interpretation

The pilot demonstrates deterministic, traceable soft qualification and one
clear relevant promotion in the ALK query. It does not demonstrate preserved
historical retrieval coverage or clinical effectiveness. Expanded evaluation
should wait for a separately reviewed coverage/normalization phase; final
evaluation remains unavailable.
