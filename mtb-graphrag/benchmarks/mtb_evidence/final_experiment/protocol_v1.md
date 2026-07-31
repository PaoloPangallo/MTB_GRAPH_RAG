schema_version: mtb-final-protocol-markdown/1.0
generated_at: 2026-07-31T17:00:00+02:00
base_commit: 84bcecaafdee60206799fd0a245cb78f816b257e
corpus_version: qualified_claim_repository/1.4
corpus_hash: 31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa
gate_version: qualified_claim_structural_gate/1.3
retriever_version: qualified_claim_retriever/1.0
generator_version: final_experiment_generator/1.0
content_sha256: b7e788135e9ca1c9b6e2dc4fa27cb3cc1fa5b8e60ee1b31da42d8817911f4be4

# Final comparative evaluation protocol v1

The structured primary experiment compares S1, S2 and S3 on the 8-query fair subset; all 21 queries run on S3. The primary endpoint is paired claim-level primary precision. H1-H6 and all query, model, metric, timeout, retry, missing-data and failure rules are frozen in `protocol_v1.json`.

No gold payload has been opened. No official run is authorized. The protocol remains readiness-blocked because the robustness model is unavailable and Neo4j is offline.

After gold opening, gate, scoring, mappings, queries, primary prompts, models, metrics, and evaluation code are immutable for the primary analysis. The opening timestamp and bundle digest must be recorded. Any later correction is versioned and labelled post_hoc and is excluded from the primary result.
