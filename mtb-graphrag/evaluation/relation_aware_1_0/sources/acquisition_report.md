# Source snapshot acquisition report

Acquisition was performed only for the frozen 16 PAPER_EVIDENCE and 10 CLINICAL_TRIAL entries. The 10 KG_ONLY entries made zero resolver calls. No parser LLM, Reader, Writer, or support checker was invoked.

PAPER_TOTAL=16
PAPER_PMC_FULLTEXT=5
PAPER_ABSTRACT_ONLY=11
PAPER_UNAVAILABLE=0
PAPER_PARSER_FAILED=0

TRIAL_TOTAL=10
TRIAL_RESOLVED=10
TRIAL_UNAVAILABLE=0
TRIAL_PARSE_FAILED=0

KG_ONLY_TOTAL=10
KG_ONLY_FETCH_ATTEMPTS=0

TOTAL_EXTERNAL_REQUESTS=47
HTTP_FAILURES={}

The canonical paper rule was fixed before acquisition: PMC full text when available, otherwise PubMed abstract. No source was substituted after failure. SourceUnit parsing was deterministic and produced all units available from each canonical document; no selection or scientific interpretation was performed.

Request count note: the resolver's successful PMC return record did not retain the preceding PubMed attempt list; counts above were reconstructed offline from the successful resolver path and the persisted PubMed/PMC payload files. No new request was made.

Request count note: the resolver's successful PMC return record did not retain the preceding PubMed attempt list; counts above were reconstructed offline from the successful resolver path and the persisted PubMed/PMC payload files. No new request was made.
