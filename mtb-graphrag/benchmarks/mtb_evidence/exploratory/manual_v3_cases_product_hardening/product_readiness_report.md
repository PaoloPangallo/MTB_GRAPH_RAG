# V3 product output hardening report

## Scope

This is an application hardening change based on four exploratory V3 runs. It does not modify the V1.6 protocol, the promoted corpus, the structural gates, official outputs, gold, or official ledgers.

## Endpoint

`POST /api/v1/v3/retrieve` invokes `EvidenceRetrievalPipeline.run(..., retrieval_backend="qualified_claim_v3")` directly. It does not use the planner, LLM, `/api/v1/analyze`, web search, PubMed live, OncoKB, or V2.

## Product projection

The response keeps all 311 native records but exposes only claim records in the four clinical sections. Provenance containers, unresolved/unsupported associations, and deprecated claims are listed under `technical_records`. No record is deleted or reclassified in the retriever.

The four cases contain 148 claim records and 163 technical records. The 147-item audit bucket in cases 1, 2 and 4 is therefore shown as provenance containers, not as clinical evidence. Case 3 additionally retains one active claim in audit.

## Provenance

The adapter reports `VERIFIED_LOCATOR`, `ALTERNATIVE_SOURCE_AVAILABLE`, `PARENT_ONLY`, or `SOURCE_IDENTIFIER_MISSING` based only on native source IDs, source-unit IDs and locators. It never copies identifiers between claims.

## Gate trace and reason codes

The native gate order is retained. Each claim exposes ordered gate steps, original reason codes and a stable human message. Unknown codes remain visible with a generic message rather than being dropped.

## Score

The score is the native structural ranking score, not a probability or percentage. Its native implementation uses weighted feature contributions (biomarker 40, direction 8, disease 30, formulation 15, intervention identity 15 in the exact-match example) and reports a total of 108. It is comparable only within the configured V3 ranking contract and should be shown as a breakdown/detail, not as a clinical confidence.

## Warning diagnosis

The warning bucket was not changed. Static inspection shows it is reachable but only when the final composed bucket is warning. Audit/rejected object invariants take precedence, which explains why the limitation case produced audit/rejected rather than warning.

## Frontend

The frontend now has a dedicated ?Recupera evidenze V3 strutturate? action and a V3 view with separate sections for primary, warning, audit, rejected, and collapsible technical provenance records. Empty primary/warning results show an explicit abstention message.

## Remaining issues

- The current product form does not yet expose a dedicated intervention input for the V3 action; it sends an empty intervention list.
- Native V3 results do not contain a complete subject/relation/object tuple, so the UI shows null and preserves the original claim text instead of inventing a tuple.
- Source completeness remains a corpus/application issue: many claims lack verifiable locators.
