# ESCAT Curation MVP Compliance Design

## Scope

Correct the offline ESCAT curation MVP on a branch based on `fe01fd1`.
The pilot remains the real 15 therapeutic `PARTIALLY_ASSIGNABLE` claims: no
diagnostic draft is added, no official ESCAT rule is authored, and no
production runtime or V3 scoring path is changed.

## Design

The workbench keeps `EscatAssessmentRecord` as the current materialized state
and stores every mutation in an append-only JSONL event log. Field mutations
are exposed through explicit CLI commands and validated before persistence.
Supersession creates a new assessment record and marks the predecessor
`SUPERSEDED`; the predecessor JSON remains unchanged.

Assessment status transitions are enforced separately from serialization.
`export_dossier()` copies the record status verbatim, including
`NOT_APPLICABLE`, `CONFLICTING_EVIDENCE`, `REJECTED`, and `SUPERSEDED`.

Rule-set validation is structural only. A JSON rule set must identify its
framework/version, rules, rule sources, required fields, required conditions,
exclusion conditions, and alternative conditions. A synthetic fixture marked
`TEST_FIXTURE_ONLY` and `NOT_AN_OFFICIAL_ESCAT_RULESET` exercises this code;
it is never copied into pilot data or dossier output.

## Verification boundary

Unittest is the only test runner used. The final checks compare the commit
diff against the production paths and snapshot the pre-existing untracked
path list before implementation; those paths are not edited or staged.
