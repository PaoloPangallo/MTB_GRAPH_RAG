# Final Evaluation Protocol 1.3

This is a minimal execution/model-identity revision of frozen Protocol 1.2.
Protocol 1.2 remains historical and immutable. Protocol 1.3 does not change
RQ definitions, datasets, metrics, denominators, success criteria, GOLD,
ablations, reliability, retries, statistics, latency, held-out data, A01, or
S01.

Status: `DRAFT_FOR_HUMAN_REVIEW`  
Frozen: `false`  
Final results observed before 1.3: `false`

The prescribed effective model is `gemma4:31b-cloud` at the Ollama Cloud
OpenAI-compatible endpoint. The historical runtime default `gemma4:cloud` is
not accepted as the final effective model. Client-side generation parameters
and prompt identities are locked in the JSON contracts.

The provider metadata probe is metadata-only. It does not establish immutable
provider weights. Pre- and post-execution snapshots are required; drift
preserves all raw results and requires human review rather than automatic
promotion.

The exact provider-side digest cannot be pinned for generation. Claims of
bitwise or cryptographically pinned model reproducibility are prohibited.
Only client configuration, alias, prompts, observable metadata, and snapshots
are reproducible claims.
