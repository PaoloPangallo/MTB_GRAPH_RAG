# Research-pipeline test perimeter (pre-freeze)

`CURRENT_RUNTIME_TESTS`: `test_pre_freeze_*.py`,
`test_orchestrated_pre_freeze_matrix.py`, `test_retrieval_v4_redesign.py`,
`test_runtime_v4_migration.py`, `test_case_parser_v4_contract.py`,
`test_kg_only_relation_aware_report.py`, `test_sourceunit_selector.py`,
`test_relation_support_contract_v5.py`, `test_dossier_aggregation_redesign.py`,
`test_deterministic_report.py`, and the current-GCA4 cases in
`test_canonical_runtime_invariants.py`, plus the current-GCA4 case in
`test_runtime_relation_aware_report.py` and `test_trial_relation_aware_report.py`.
These exercise the v4 loader and/or
deterministic runtime contracts. Mocked Reader output is not a live model test.

`LEGACY_TESTS`: `test_v3_runtime_admission.py`, historical replay/bundle tests,
the strict-xfail frozen-replay case in `test_runtime_relation_aware_report.py`,
and tests asserting GCA v2/v3 repository defaults. They remain useful for
historical behavior but are not evidence that the current GCA4 runtime works.

`EVALUATION_TESTS`: tests and scripts under `evaluation/`, including final
evaluation units. They are outside the pre-freeze regression suite and must
not be executed by this hardening work.

Tests using `tmp_path` can fail at fixture setup in the managed Windows
sandbox with `PermissionError`; report these as environmental, not as passes.
