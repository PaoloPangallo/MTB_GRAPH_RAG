# LIVE / REPLAY separation

The LIVE adapter is selected only when execution mode is LIVE. The replay provider remains the explicit selection function for REPLAY.

REPLAY has no `DocumentRuntime`; it constructs document/source-unit views from frozen artifacts and does not consult network-capable resolvers. LIVE uses provenance descriptors and never uses frozen source-unit IDs for selection.
