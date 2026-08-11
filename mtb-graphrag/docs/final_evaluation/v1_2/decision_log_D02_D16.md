# Decision log D02–D16

This file is explanatory only. The JSON pointer in each row is the normative
source; this Markdown must not be used to resolve a conflict.

| Decision | Normative JSON pointer | Resolution |
|---|---|---|
| D02 | `metric_registry.json#/RQ1` | Separate candidate, path, 16-field, identity, and negative denominators. |
| D03 | `metric_registry.json#/RQ2` | Positive N=9 primary, overall N=20 companion, zero-direct N=11, K=5. |
| D04 | `metric_registry.json#/RQ2/gold_context_contract` | Full GOLD context, no truncation, not equal-budget. |
| D05 | `ablation_contract.json#/A` | Remove stages 3 and 3b through harness bypass. |
| D06 | `ablation_contract.json#/C` | Retain transport/schema; identity semantic validator for valid QUOTE. |
| D07 | `ablation_contract.json#/D` | Narrator runs; Narrative Verifier is not called; canonical dossier unchanged. |
| D08 | `reliability_contract.json` | Two strata, exact cache/network contracts, separate reporting. |
| D09 | `execution_contract.json#/retry_policy` | Separate scientific repetition from infrastructure attempts; reconcile orphan reservations. |
| D10 | `statistical_plan.json` | Wilson and paired percentile bootstrap; p-values planned false. |
| D11 | `latency_contract.json#/stage_model` | Sixteen stage records, including 3b. |
| D12 | `latency_contract.json#/same_document_cache_latency_pair` | Fixed GCA/document pair, no replacement after outcome. |
| D13 | `execution_contract.json#/identifiers` | Canonical JSON hash identities, outcome-independent attempts. |
| D14 | `dataset_registry.json#/dataset_hashes` | Map of universal and testbed-specific hashes. |
| D15 | `execution_contract.json#/raw_lifecycle` | Append-only ledger, immutable raw, reconciliation recovery. |
| D16 | `lineage.json#/freeze_precedence` | Structured freeze records and commits supersede stale prose. |
