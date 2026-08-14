# Final Evaluation Protocol 1.7 provenance

The Final Evaluation was executed from the local experimental commit
`1174135d0bf86728f2e25593b0afbaed18a5dc6f`. That commit remains the experimental
identity recorded by the sealed evaluation artifacts.

The original Git ancestry is not published because it contains oversized
historical artifacts. The public repository therefore provides the evaluated
source through the GitHub-safe snapshot `3ff6c10cf6c609ba4e5f71ea897eb548cab5b666`.
This is a content-verified public provenance snapshot, not the original Git
commit and not Git ancestry equivalence.

The public source files relevant to the evaluated runtime, Protocol 1.7 and
Final Evaluation Harness are verified file-by-file. The canonical v2 graph
candidate repository is a required external frozen data artifact because it is
a large runtime input rather than source code:

- file: `graph_candidate_repository_v2_candidates.jsonl`
- runtime path: `mtb-graphrag/benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/2.0/candidates.jsonl`
- size: `72,495,662` bytes
- SHA-256: `d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d`
- encoding: strict UTF-8
- canonical and required: yes

The v3 candidate corpus is a non-canonical research/shadow artifact and is not
required or published for this Final Evaluation.

## Restoring the Final Evaluation data dependency

1. Checkout the public Protocol 1.7 source branch.
2. Run the pinned fetcher from the repository root:

   `python evaluation/final_results/protocol_v1_7/provenance/fetch_canonical_v2_corpus.py`

   It downloads only the fixed release tag
   `final-evaluation-protocol-v1.7-artifacts` and the fixed asset name
   `graph_candidate_repository_v2_candidates.jsonl`.
3. Alternatively, for an already downloaded asset, run:

   `python evaluation/final_results/protocol_v1_7/provenance/restore_canonical_v2_corpus.py <downloaded-file>`

4. The fetch and restore scripts validate the filename, strict UTF-8, exact
   byte size (through the SHA-pinned content) and exact SHA-256 before
   installing the file at the canonical runtime path. It exits non-zero on any
   mismatch and never falls back to v3 or another version.

See `FINAL_EVALUATION_PROVENANCE.json`, `CANONICAL_DATA_ARTIFACT.json`, and
`SCIENTIFIC_TREE_EQUIVALENCE.csv` for the machine-readable mapping.
