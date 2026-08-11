# Protocol 1.3 change log

## INHERITED_UNCHANGED

D02–D16 are inherited unchanged from Protocol 1.2. Their source of truth is
the frozen 1.2 protocol SHA; no formulas, denominators, datasets, or result
interpretations are duplicated here.

## NEW_IN_1_3

- E01 — effective model identity: `gemma4:31b-cloud`.
- E02 — generation configuration and environment lock.
- E03 — provider metadata pre/post snapshots and drift guard.
- E04 — explicit remote-provider reproducibility limitation.

## SUPERSEDED_BY_1_3

Only the 1.2 assumption that runtime model identity alone was sufficient for
final execution reproducibility is superseded. Protocol 1.2 itself is not
rewritten and remains valid historical protocol.
