# Failure analysis

The frozen run contains 11 cases with zero directly relevant units under the independent annotation protocol. These include provenance/document pairs where the paper does not express the GCA-specific alteration in usable evidence language. They are retained as negative cases rather than converted into forced positives.

The current failure artifact classifies selector misses at top five without changing the selector. The main observed risk is lexical dilution in long PMC documents and generic alterations such as `Fusion`, `Amplification`, or `Mutation`. Drug aliases and table-only evidence were not sufficiently represented in this corpus.

A selected unit is never invented: every selected ID belongs to the freshly parsed document. The selector does not determine whether the paper supports the GCA.
