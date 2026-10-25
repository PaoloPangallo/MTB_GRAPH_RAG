# Backend/frontend release

This branch publishes the current backend, frontend and their imported Python support modules on top of origin/main without importing the local experiment-output history. It does not publish the frozen ablation study or its raw runs.

The backend and frontend trees match local commit 4df9b328df6935f0a6805084caaf84a693d76da8. Pre-existing staged legacy removals were not applied because the API still imports some compatibility modules.

Validation: canonical research pipeline 2335 passed, 19 skipped, 59 subtests; frontend 319 passed; production build and ESLint passed. The two optional-archive guards were also checked with archives installed (14 passed) and missing.

## Runtime prerequisites

Runtime assets are provisioned separately; cloning this branch alone does not install the knowledge base or enable model services. The existing defaults require these four files under mtb-graphrag:

- data/terminology/1.2/manifest.json
- data/terminology/1.2/registry.json
- data/terminology/1.2/gca_overlay.json
- benchmarks/mtb_evidence/document_grounded_claims/graph_candidate_repository/4.0/candidates.jsonl

RESEARCH_PIPELINE_DATA_ROOT selects the external data root; RESEARCH_PIPELINE_TERMINOLOGY_MANIFEST selects the terminology manifest. The loader verifies the configured asset digests. These data dependencies were already present before this release.

Configure the model endpoint and API key locally. The document cache and MedCPT checkpoints are not included. If MedCPT is unavailable, the runtime records the explicit BM25 fallback. Historical research tests may require separately installed frozen archives; their results are not reproduced by cloning source code alone.
