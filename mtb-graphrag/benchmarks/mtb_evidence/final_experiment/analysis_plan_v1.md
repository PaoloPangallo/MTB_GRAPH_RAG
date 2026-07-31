schema_version: mtb-final-analysis-plan/1.0
generated_at: 2026-07-31T17:00:00+02:00
base_commit: 84bcecaafdee60206799fd0a245cb78f816b257e
corpus_version: qualified_claim_repository/1.4
corpus_hash: 31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa
gate_version: qualified_claim_structural_gate/1.3
retriever_version: qualified_claim_retriever/1.0
generator_version: final_experiment_generator/1.0
content_sha256: 5452a2bc2b9358ab129cf4a9da8e3ee6cf3c41de45105444e5d20586772aab5d

# Analysis plan

Use query-paired differences and query-level percentile bootstrap 95% intervals. Report effect size and raw numerator/denominator for every metric. For S2 report mean, sample standard deviation, minimum and maximum over five runs. Keep candidate-generation, retrieval, qualification, ranking and LLM-rendering failures separate. nDCG remains disabled unless graded gold is valid. All conclusions are exploratory and are not general clinical validation.
