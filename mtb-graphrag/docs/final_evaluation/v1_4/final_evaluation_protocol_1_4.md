# Final Evaluation Protocol 1.4

Status: `ACCEPTED` / frozen after human review on 2026-08-11.

Protocol 1.4 is a minimal runtime-identity amendment of Protocol 1.3. It
inherits D02–D16 and E01–E04 unchanged. F01 records the runtime interface
exposure required to execute the already-frozen D05 Ablation A: optional
`match_verifier_fn` and `eligibility_gate_fn` injection points in the
orchestrator. With no overrides, the canonical path remains unchanged. D05
still removes only stages 3 and 3b; parser output, retrieval input, and all
downstream stages remain canonical. No synthetic MATCH, eligibility, positive
reason code, or clinical state is permitted.

The runtime identity changes from `3d2251f82a586535f79f3d0b3725c16330c365ba`
to `79867435acd59b830dae1d0fbab272c2bea2427b`. Scientific units remain
1/80/5/70/25/9/30/2 (222 total), with the inherited scientific projection
SHA `76bcb6f395aa4b8053ac19305d7404713aa6d0d53c6bce21a1f0f7b3e4971497`.

The permitted equivalence claim is
`CANONICAL_SEMANTIC_EQUIVALENCE_UNDER_DEFAULT_INJECTION`; it does not claim
bit-level equivalence for provider executions.
