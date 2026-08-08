# Failure modes

- no authorized text: `DOCUMENT_UNAVAILABLE`, no Gemma call;
- parser/materialization failure: `PARSER_FAILED`;
- technical selector failure: `SOURCEUNIT_SELECTION_FAILED`;
- PMC unavailable with PubMed abstract: explicit `PMC_RESOLUTION_FAILED` degradation and abstract-only parsing;
- replay artifact missing: replay failure, never online recovery.

The selector does not decide support or status. An irrelevant or negative passage can still be selected and Gemma may correctly abstain.
