# Independent corpus

Candidates come from the real `graph_candidate_repository/2.0` and are selected from provenance PMIDs. Duplicate PMIDs are removed; pilot candidate IDs and pilot document identifiers are excluded programmatically. When a paper has several GCA materializations, an intervention-bearing assertion is preferred before fetching.

The final corpus has 20 candidate/document pairs: 12 PubMed abstract parses and 8 PMC full-text parses. The longest document has 407 SourceUnits. Fourteen candidate assertions include an intervention; three are `Does Not Support`. All 20 were fetched into an ephemeral independent cache and parsed with the existing canonical parsers. The committed inventories contain identifiers, hashes, counts, parser versions and unit types only.

`live_fetch_cases.json` records 20/20 successful fresh fetches. The canonical document cache was not used as the text source and was not modified.
