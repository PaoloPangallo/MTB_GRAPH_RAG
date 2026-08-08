# Selector versus bundle policy

The evaluated ADR recommends: LIVE uses the deterministic selector; REPLAY continues to use the frozen bundle. This preserves replay reproducibility while removing the hidden bundle dependency from new live documents. Option B (bundle if present, selector otherwise) retains an implicit historical-path dependency. No policy was implemented in this phase.
