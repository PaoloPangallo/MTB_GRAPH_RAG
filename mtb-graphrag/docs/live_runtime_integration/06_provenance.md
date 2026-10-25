# Provenance and ledger

Observable events now distinguish document cache hit/miss, fetch start/success/failure, abstract degradation, parsed SourceUnits, selector start/completion, Gemma enrichment, and quote validation.

The evidence chain is reconstructible as:

`candidate -> requested document identifier -> acquisition event -> snapshot -> parser/source units -> selector hashes and IDs -> Gemma output -> validator result -> canonical state`.

Event payloads contain identifiers and hashes, not full document text.
